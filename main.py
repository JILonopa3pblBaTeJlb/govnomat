import asyncio
import logging
import shutil
import os
import random
import json
from config import *
import lyrics_manager as lm
import audio_utils as au
import ace_engine as ace
import tg_handler as tg

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

async def text_provider_worker(queue, stop_event):
    print("🤖 Воркер текстов запущен.")
    
    # Загружаем историю один раз при старте
    history = lm.load_sung_history()
    # Множество для быстрого поиска и учета тех, что "в работе" прямо сейчас
    used_ids = set(history)

    while not stop_event.is_set():
        if queue.qsize() < 15:
            try:
                db = lm.parse_lyrics_database()
                
                # Ищем песню, которой нет в истории и которая не взята в этом сеансе
                ref_song = next((s for s in db if s["id"] not in used_ids), None)
                
                if not ref_song:
                    print("🎲 Новых песен в базе нет. Генерирую микс...")
                    lyr_task = f"Напиши новую песню, вдохновляясь этим набором фраз:\n\n{lm.get_synthetic_example(db)}"
                    is_synthetic = True
                else:
                    print(f"📖 Воркер выбрал песню: {ref_song['id']}")
                    # Сразу помечаем как использованную, чтобы следующая итерация цикла её не взяла
                    used_ids.add(ref_song["id"])
                    lyr_task = f"Напиши песню на основе этого текста:\n\n{ref_song['lyrics']}"
                    is_synthetic = False

                # Загружаем промпты
                sys_caption = lm.load_prompt(PROMPT_CAPTION_FILE, "Act as an RnB producer.")
                caption_task = lm.load_prompt("prompt_caption_task.txt", "Describe a professional house pop hit.")
                sys_lyrics = lm.load_prompt(PROMPT_LYRICS_FILE, "Act as a viral pop-star writer.")

                # Запросы к LLM (это долго)
                cap = await lm.get_text_from_llm(sys_caption, caption_task, "CAPTION")
                lyr = await lm.get_text_from_llm(sys_lyrics, lyr_task, "LYRICS")
                
                if cap and lyr:
                    if not is_synthetic and ref_song:
                        # Сохраняем в файл только при успешной генерации
                        current_history = lm.load_sung_history()
                        if ref_song["id"] not in current_history:
                            current_history.append(ref_song["id"])
                            lm.save_sung_history(current_history)
                    
                    await queue.put((cap, lyr))
                    print(f"✅ Текст готово. В очереди: {queue.qsize()}")
                else:
                    # Если LLM упала, а песня была не синтетическая — возвращаем ID в пул
                    if not is_synthetic and ref_song:
                        used_ids.remove(ref_song["id"])
                
            except Exception as e:
                print(f"❌ Ошибка воркера: {e}")
                
        await asyncio.sleep(1)

async def create_album(text_queue):
    album_id = str(random.randint(10**15, 10**16 - 1))
    
    # 1. Пытаемся восстановить ID старого альбома из метаданных
    if os.path.exists(ALBUM_META_FILE):
        try:
            with open(ALBUM_META_FILE, "r") as f:
                data = json.load(f)
                album_id = data.get("id", album_id)
                print(f"🔄 ОБНАРУЖЕН НЕЗАВЕРШЕННЫЙ АЛЬБОМ: {album_id}")
        except: pass
    
    with open(ALBUM_META_FILE, "w") as f:
        json.dump({"id": album_id}, f)
    
    seg_dir = os.path.join(BASE_TEMP_DIR, f"segments_{album_id}")
    os.makedirs(seg_dir, exist_ok=True)
    
    # 2. Считаем существующие сегменты и восстанавливаем время (cur_dur)
    existing_files = sorted([f for f in os.listdir(seg_dir) if f.endswith(".flac")])
    files_count = len(existing_files)
    
    cur_dur = 0
    if files_count > 0:
        # Формула: Первый трек целиком + остальные с учетом кроссфейда
        cur_dur = TRACK_DURATION + (files_count - 1) * (TRACK_DURATION - CROSSFADE_DURATION)
    
    def fmt(s): return f"{int(s//60):02d}:{int(s%60):02d}"

    print(f"\n{'='*60}")
    print(f"🚀 ЗАПУСК ПРОЦЕССА СОЗДАНИЯ АЛЬБОМА")
    print(f"🆔 ID: {album_id}")
    print(f"⏱️  ПРОГРЕСС ПРИ СТАРТЕ: {fmt(cur_dur)} / {fmt(TARGET_TOTAL_SECONDS)}")
    print(f"📁 ПАПКА: {seg_dir}")
    print(f"{'='*60}\n")
    
    while cur_dur < TARGET_TOTAL_SECONDS:
        await ace.wait_for_ace_server()
        
        print(f"⏳ Ожидание текстов из очереди (сейчас в очереди: {text_queue.qsize()})...")
        cap, lyr = await text_queue.get()
        print(f"✅ Тексты получены!")
        bpm = random.randint(124, 130)
        key = MUSIC_KEYS[files_count % len(MUSIC_KEYS)]
        
        # Считаем примерное общее кол-во треков для визуализации
        total_tracks_est = int(TARGET_TOTAL_SECONDS // (TRACK_DURATION - CROSSFADE_DURATION))

        # ВЫЗОВ ГЕНЕРАТОРА С ПЕРЕДАЧЕЙ ПРОГРЕССА
        path = await asyncio.to_thread(
            ace.generate_audio_segment,
            cap,
            lyr,
            bpm,
            key,
            files_count + 1,    # Номер трека для лога (начиная с 1)
            total_tracks_est,   # Всего треков
            cur_dur             # Сколько секунд уже готово
        )
        
        if not path:
            print(f"⚠️ Ошибка генерации. Возвращаем текст в очередь и перезагружаем сервер...")
            await text_queue.put((cap, lyr))
            await ace.wait_for_ace_server(force_restart=True)
            continue
            
        target = os.path.join(seg_dir, f"segment_{files_count:03d}.flac")
        
        # 3. Склейка сегментов
        if files_count > 0:
            print(f"🔗 Стык сегмента {files_count} + {files_count+1} (Pitch Rise / Crossfade)...")
            await asyncio.to_thread(au.apply_pitch_rise, path, target, TRACK_DURATION, CROSSFADE_DURATION)
            cur_dur += (TRACK_DURATION - CROSSFADE_DURATION)
        else:
            print(f"💾 Сохранение начального сегмента...")
            shutil.copy(path, target)
            cur_dur += TRACK_DURATION
            
        files_count += 1
        text_queue.task_done()
        
        print(f"✅ УСПЕХ. Текущая длина альбома: {fmt(cur_dur)}")

    # 4. Финальная сборка альбома
    print(f"\n{'='*60}")
    print(f"🏁 ЦЕЛЬ ДОСТИГНУТА! НАЧИНАЮ ФИНАЛЬНЫЙ РЕНДЕР...")
    
    final_m4a = os.path.join(ALBUMS_DIR, f"{album_id}.m4a")
    all_files = sorted([os.path.join(seg_dir, f) for f in os.listdir(seg_dir) if f.endswith(".flac")])
    
    if all_files:
        au.concat_segments(all_files, final_m4a)
        print(f"📤 ОТПРАВКА В TELEGRAM: {final_m4a}")
        asyncio.create_task(tg.send_to_telegram(final_m4a, album_id))
    
    # Очистка метаданных (альбом закончен)
    if os.path.exists(ALBUM_META_FILE):
        os.remove(ALBUM_META_FILE)
        
    print(f"✨ ПРОЦЕСС ЗАВЕРШЕН. АЛЬБОМ ГОТОВ!")
    print(f"{'='*60}\n")

async def main():
    print("\n" + "!"*40)
    print("🚀 ПРОГРАММА ЗАПУЩЕНА")
    print("!"*40 + "\n")
    
    os.makedirs(ALBUMS_DIR, exist_ok=True)
    os.makedirs(BASE_TEMP_DIR, exist_ok=True)
    
    # Теперь эта функция будет писать "попытка 1, попытка 2..."
    status = await ace.wait_for_ace_server()
    if not status:
        print("🛑 КРИТИЧЕСКАЯ ОШИБКА: Не удалось достучаться до ACE. Выход.")
        return

    print("⏳ Подключение к Telegram...")
    await tg.client_tg.start()
    print("✅ Telegram подключен!")
    
    t_queue = asyncio.Queue()
    stop_ev = asyncio.Event()
    
    print("🤖 Запуск воркера текстов...")
    worker = asyncio.create_task(text_provider_worker(t_queue, stop_ev))
    
    # Даем воркеру время сделать первый запрос
    print("⏳ Ожидание наполнения очереди текстов...")
    while t_queue.empty():
        await asyncio.sleep(2)
        print(f"   ...в очереди пока {t_queue.qsize()} текстов")

    try:
        for i in range(ALBUMS_TO_GENERATE):
            await create_album(t_queue)
    finally:
        stop_ev.set()
        await tg.client_tg.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
