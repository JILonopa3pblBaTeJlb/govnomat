import os
import json
import random
import re
import time
import logging
import asyncio
import g4f
from config import *

logger = logging.getLogger(__name__)

RE_END_OF_THOUGHT = re.compile(r"(?s).*?End of Thought\s*\(\*?\d+(?:\.\d+)?s?\)\s*", flags=re.IGNORECASE)
RE_THINK = re.compile(r"<think>.*?</think>", flags=re.DOTALL | re.IGNORECASE)
INACTIVE_SECONDS = 10 * 60

def super_clean(text):
    if not text: return ""
    
    # Сначала удаляем стандартные теги <think>...</think>
    text = RE_THINK.sub("", text)
    
    # Затем удаляем всё, что ведет к "End of Thought"
    # (захватывает весь бред нейросети в начале)
    text = RE_END_OF_THOUGHT.sub("", text)
    
    # Убираем блоки кода ```markdown ... ```
    text = re.sub(r"```[a-zA-Z]*\n?(.*?)\n?```", r"\1", text, flags=re.DOTALL)
    
    # Базовая очистка символов
    text = text.strip().strip('"').strip('«').strip('»').strip("'")
    
    # Очистка мусорных префиксов (теперь и с учетом переноса строк)
    prefixes = ["Prompt:", "Lyrics:", "Response:", "Here is", "Sure,", "I will", "Название песни:"]
    for prefix in prefixes:
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip().strip(":").strip()
            
    return text
def load_prompt(file_path, default):
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f: return f.read().strip()
    return default

def load_denials():
    d_list = ["as an ai", "i cannot", "unauthorized", "explicit", "offensive", "policy"]
    if os.path.exists(DENIALS_FILE):
        with open(DENIALS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                p = line.strip().lower()
                if p and not p.startswith("#"): d_list.append(p)
    return list(set(d_list))

def load_providers():
    providers = []
    if os.path.exists(PROVIDERS_FILE):
        with open(PROVIDERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    try:
                        p_name, models = line.split(":", 1)
                        providers.append({"provider": p_name.strip(), "models": [m.strip() for m in models.split(",")]})
                    except: continue
    return providers

def load_inactive():
    if not os.path.exists(INACTIVE_FILE): return {}
    try:
        with open(INACTIVE_FILE, "r") as f: return json.load(f)
    except: return {}

def save_inactive(data):
    with open(INACTIVE_FILE, "w") as f: json.dump(data, f)

def is_provider_active(p_name, inactive_map):
    until = inactive_map.get(p_name)
    if not until or time.time() > until: return True
    return False

def mark_inactive(p_name):
    m = load_inactive()
    m[p_name] = time.time() + INACTIVE_SECONDS
    save_inactive(m)
    print(f"🚫 Провайдер {p_name} забанен на 10 мин.")

def parse_lyrics_database():
    if not os.path.exists(COLLECTED_LYRICS_FILE): return []
    with open(COLLECTED_LYRICS_FILE, "r", encoding="utf-8") as f: content = f.read()
    pattern = re.compile(r"ID:\s*(.*?)\nADDED:.*?\n={30,}\n\n(.*?)(?=\n={30,}|$)", re.DOTALL)
    return [{"id": m[0].strip(), "lyrics": m[1].strip()} for m in pattern.findall(content)]

def get_synthetic_example(db, num_lines=24):
    if not db: return "No lyrics found in database."
    all_lines = []
    for song in db:
        lines = [l.strip() for l in song['lyrics'].split('\n') if l.strip() and not (l.startswith('[') and l.endswith(']'))]
        all_lines.extend(lines)
    if not all_lines: return "Database empty."
    sample = random.sample(all_lines, min(num_lines, len(all_lines)))
    return "\n".join(sample)

async def get_text_from_llm(system, task, tag):
    providers_info = load_providers()
    denials = load_denials()
    
    for attempt in range(50):
        inactive_map = load_inactive()
        active = [p for p in providers_info if is_provider_active(p["provider"], inactive_map)]
        
        if not active:
            print("🔄 Все провайдеры в бане, сбрасываю...")
            save_inactive({})
            await asyncio.sleep(1)
            continue

        p_info = random.choice(active)
        p_name, model = p_info["provider"], random.choice(p_info["models"])
        p_class = getattr(g4f.Provider, p_name, None)

        if not p_class:
            mark_inactive(p_name)
            continue

        try:
            print(f"\n📡 [ATTEMPT {attempt+1}] [{tag}] Запрос к {p_name}...")
            
            resp = await asyncio.to_thread(
                g4f.ChatCompletion.create,
                model=model, provider=p_class,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": task}],
                stream=False
            )

            if not resp:
                mark_inactive(p_name)
                continue

            print(f"📩 [{tag}] ОТВЕТ: {str(resp)}...")
            text = super_clean(str(resp))
            
            if any(d in text.lower() for d in denials):
                print(f"🚫 [{tag}] Отказ от {p_name}. Пробую другого.")
                if len(active) <= 1: save_inactive({})
                continue

            if len(text) < 15:
                mark_inactive(p_name)
                continue

            if tag == "LYRICS":
                text = f"{text}\n\n[Refrain]\nПиськи сиськи пёзды залупки"
                print("🎸 Рефрен прихардкожен.")

            return text

        except Exception as e:
            print(f"❌ Ошибка {p_name}: {e}")
            mark_inactive(p_name)
            await asyncio.sleep(0.5)
    return None

# Заглушки для совместимости
def load_sung_history():
    if not os.path.exists(SUNG_HISTORY_FILE):
        return []
    try:
        with open(SUNG_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception as e:
        print(f"⚠️ Ошибка чтения истории спетых песен: {e}")
        return []

def save_sung_history(history):
    try:
        with open(SUNG_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Не удалось сохранить историю: {e}")
        
async def run_lyrics_monster(): return True
