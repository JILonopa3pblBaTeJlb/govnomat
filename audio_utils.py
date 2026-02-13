import os
import subprocess
import shutil
import logging
from config import *

logger = logging.getLogger(__name__)

def apply_pitch_rise(input_path, output_path, total_duration, crossfade_duration):
    try:
        start_time = 0
        end_time = total_duration - crossfade_duration
        if end_time <= 5:
            shutil.copy(input_path, output_path)
            return True

        bend_duration = end_time
        logger.info(f"📈 Pitch Rise: {bend_duration:.1f}с")
        cmd = ['sox', input_path, output_path, 'bend', f'0,-100,{bend_duration}', 'trim', '0', str(total_duration)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return os.path.exists(output_path) and os.path.getsize(output_path) > 1000
    except Exception as e:
        logger.error(f"❌ SoX error: {e}")
        return False

def concat_segments(all_files, output_path):
    """Склейка через FFmpeg acrossfade"""
    if len(all_files) < 2: return
    logger.info(f"🧵 Склеиваем {len(all_files)} файлов...")
    filter_complex = ""
    current_label = "[0:a]"
    for i in range(1, len(all_files)):
        next_in = f"[{i}:a]"
        new_label = f"[v{i}]"
        filter_complex += f"{current_label}{next_in}acrossfade=d={CROSSFADE_DURATION}:c1=tri:c2=tri"
        if i < len(all_files) - 1:
            filter_complex += f"{new_label}; "
            current_label = new_label
    
    cmd = [
        'ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        *sum([['-i', f] for f in all_files], []),
        '-filter_complex', filter_complex,
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', '-ac', '2', output_path
    ]
    subprocess.run(cmd, check=True)
