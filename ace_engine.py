

import os
import time
import asyncio
import requests
import subprocess
import logging
import glob
from gradio_client import Client
from config import *

logger = logging.getLogger(__name__)

async def is_ace_alive():
    try:
        # Используем to_thread, чтобы сетевой запрос не вешал весь скрипт
        resp = await asyncio.to_thread(requests.get, f"{ACE_API_URL}/", timeout=2)
        return resp.status_code == 200
    except:
        return False

async def stop_ace_server():
    print("🛑 Остановка старых процессов ACE...")
    if os.path.exists("ace_server.pid"):
        try:
            with open("ace_server.pid") as f: pid = int(f.read().strip())
            os.kill(pid, 15)
            await asyncio.sleep(2)
            os.kill(pid, 9)
        except: pass
        finally:
            if os.path.exists("ace_server.pid"): os.remove("ace_server.pid")
    subprocess.run(["pkill", "-f", "acestep"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "ace_wrapper.py"], stderr=subprocess.DEVNULL)

async def start_ace_server_process():
    print("🚀 Запускаю ace_wrapper.py...")
    try:
        # shell=True нужен, чтобы подхватить алиасы и пути
        subprocess.Popen(f"python3 ace_wrapper.py --device cpu", shell=True)
        print("⏳ Процесс запущен. Ждем 60 секунд на загрузку весов модели...")
        # Модель тяжелая, ей нужно время просто чтобы "встать"
        for i in range(1, 7):
            await asyncio.sleep(10)
            print(f"   ...загрузка идет уже {i*10} сек...")
    except Exception as e:
        print(f"❌ Ошибка при попытке запустить процесс: {e}")

async def initialize_ace_model():
    print("⚙️  Инициализация модели в Gradio...")
    try:
        client = Client(ACE_API_URL)
        checkpoint_response = client.predict(api_name="/lambda")
        path = checkpoint_response['choices'][0] if isinstance(checkpoint_response, dict) else checkpoint_response
        client.predict(path, MODEL_CONFIG, "cpu", False, LM_MODEL, "vllm", False, True, True, True, True, api_name="/lambda_1")
        print("✨ Модель успешно инициализирована!")
        return True
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        return False

async def wait_for_ace_server(force_restart=False):
    # Если мы уже в режиме перезапуска
    if force_restart:
        await stop_ace_server()
        await start_ace_server_process()
        await initialize_ace_model()
    
    print(f"📡 Проверка связи с ACE (URL: {ACE_API_URL})...")
    
    # Проверяем всего 3 раза. Если сервера нет — запускаем!
    max_checks = 3 if not force_restart else 20
    for i in range(max_checks):
        if await is_ace_alive():
            print("✅ ACE STEP готов к работе!")
            return True
        
        # Если это первичная проверка и сервер не ответил — не ждем 15 раз!
        if not force_restart and i >= 2:
            print("⚠️ Сервер не отвечает. Похоже, он выключен.")
            break
            
        print(f"😴 Ожидание ответа сервера (попытка {i+1}/{max_checks})...")
        await asyncio.sleep(5)
    
    # Если за 3 попытки не ожил — запускаем сами
    if not force_restart:
        print("🚀 Начинаю процедуру автоматического запуска ACE STEP...")
        return await wait_for_ace_server(force_restart=True)
    
    print("❌ Не удалось запустить ACE STEP. Проверь ace_stderr.log")
    return False


def extract_audio_path(result):
    if not result: return None
    def recurse(obj):
        if isinstance(obj, str) and obj.endswith(('.flac', '.wav', '.mp3')) and os.path.isfile(obj): return obj
        if isinstance(obj, dict):
            for k in ['path', 'name', 'filename']:
                if isinstance(obj.get(k), str) and os.path.isfile(obj[k]): return obj[k]
            for v in obj.values():
                res = recurse(v)
                if res: return res
        if isinstance(obj, (list, tuple)):
            for i in obj:
                res = recurse(i)
                if res: return res
        return None
    return recurse(result)

# В ace_engine.py

def format_time(seconds):
    """Вспомогательная функция для превращения секунд в 00:00"""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"

def generate_audio_segment(caption, lyrics, bpm, key, track_idx=0, total_tracks=0, total_duration_done=0):
    """
    Генерация одного сегмента аудио через ACE.
    track_idx: номер текущего трека
    total_tracks: примерное общее кол-во треков
    total_duration_done: сколько секунд уже в альбоме
    """
    try:
        # Вспомогательная функция форматирования времени
        mins = int(total_duration_done // 60)
        secs = int(total_duration_done % 60)
        time_str = f"{mins:02d}:{secs:02d}"

        # КРАСИВЫЙ ВЫВОД В КОНСОЛЬ
        print(f"\n" + "💿" * 15)
        print(f"🎵 ГЕНЕРАЦИЯ: ТРЕК {track_idx} ИЗ ~{total_tracks}")
        print(f"⏱️  УЖЕ СОБРАНО: {time_str}")
        print(f"🎹 НАСТРОЙКИ: {bpm} BPM | {key}")
        print(f"⚙️  ПРОМПТ: {caption[:70]}...")
        print("💿" * 15 + "\n")

        client = Client(ACE_API_URL)
        
        # Замер времени генерации
        start_time = time.time()

        result = client.predict(
            caption, lyrics, int(bpm), key, "", "unknown", 8, 7.0, True, "-1", None,
            int(TRACK_DURATION), 1, None, "", 0.0, -1.0, "Fill the audio semantic mask...",
            1.0, "text2music", False, 0.0, 1.0, 3.0, "ode", "", "flac", 0.85, True,
            2.0, 0, 0.9, "NO USER INPUT", True, True, True, False, True, False, False, 0.5, 8, "vocals", [], False,
            api_name="/generation_wrapper"
        )
        
        path = extract_audio_path(result)
        
        if path:
            elapsed = time.time() - start_time
            print(f"✅ Трек {track_idx} сгенерирован за {int(elapsed)} сек.")
            return path
        
        # Резервный поиск файла в папках Gradio
        time.sleep(1.5)
        candidates = glob.glob("/tmp/gradio/**/*.flac", recursive=True) + \
                     glob.glob("/private/var/folders/*/*/T/gradio/**/*.flac", recursive=True)
        
        if candidates:
            final_path = max(candidates, key=os.path.getmtime)
            print(f"✅ Трек {track_idx} найден в кэше Gradio.")
            return final_path
            
        return None

    except Exception as e:
        logger.error(f"❌ Ошибка в generate_audio_segment: {e}")
        return None
