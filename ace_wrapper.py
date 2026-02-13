#!/usr/bin/env python3
"""
ace_wrapper.py — ультра-надёжный запуск acestep без screen и без tqdm-ошибок
Запускай просто: python3 auto6.py
"""

import os
import sys
import subprocess
import shlex

# Отключаем tqdm полностью и навсегда
os.environ['TQDM_DISABLE'] = '1'
os.environ['PYTHONUNBUFFERED'] = '1'

# Патчим tqdm на всякий случай (если вдруг импортируется до нас)
try:
    import tqdm
    tqdm.tqdm = lambda *args, **kwargs: None
    tqdm.trange = lambda *args, **kwargs: range(*args)
    print("✅ tqdm полностью убит", file=sys.stderr)
except:
    pass

print("🚀 Запускаем acestep напрямую через subprocess...", file=sys.stderr)

# Основная команда — именно так ты запускаешь вручную
cmd = ["acestep"] + sys.argv[1:]

# Если хочешь явно указать device (на случай если в auto6.py не передаёшь)
if "--device" not in sys.argv:
    cmd += ["--device", "cpu"]

print(f"🎯 Команда: {' '.join(shlex.quote(c) for c in cmd)}", file=sys.stderr)

try:
    # Запускаем в фоне, но с правильным выводом логов
    process = subprocess.Popen(
        cmd,
        stdout=open("ace_stdout.log", "w", buffering=1),
        stderr=open("ace_stderr.log", "w", buffering=1),
        text=True
    )
    print(f"✅ acestep запущен в фоне! PID: {process.pid}", file=sys.stderr)
    print(f"📋 Логи: ace_stdout.log и ace_stderr.log", file=sys.stderr)
    print(f"⏳ Ждём 45–90 секунд пока модель загрузится...", file=sys.stderr)
    
    # Сохраняем PID, чтобы потом можно было убить если что
    with open("ace_server.pid", "w") as f:
        f.write(str(process.pid))
    
    # Держим wrapper живым, чтобы auto6.py не падал
    process.wait()
    
except FileNotFoundError:
    print("❌ Команда 'acestep' не найдена! Проверь установку:", file=sys.stderr)
    print("    pip install -e .  # из папки ACE-Step-1.5", file=sys.stderr)
    print("    или: uv tool install .", file=sys.stderr)
    sys.exit(1)
except KeyboardInterrupt:
    print("\n🛑 Получен Ctrl+C, убиваем acestep...", file=sys.stderr)
    process.terminate()
    try:
        process.wait(10)
    except:
        process.kill()
    sys.exit(0)
