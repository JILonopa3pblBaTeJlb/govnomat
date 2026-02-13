import os

os.environ["TQDM_DISABLE"] = "1"

# ФАЙЛЫ
PROMPT_CAPTION_FILE = "prompt_caption.txt"
PROMPT_LYRICS_FILE = "prompt_lyrics.txt"
DENIALS_FILE = "denials.txt"
PROVIDERS_FILE = "providers_list.txt"
INACTIVE_FILE = "inactive_providers.json"
SUNG_HISTORY_FILE = "sung_songs.json"
COLLECTED_LYRICS_FILE = "collected_lyrics.txt"
MONSTER_STATE_FILE = "monster_state.json"
ALBUM_META_FILE = "current_metadata.json"

# ПАПКИ
ALBUMS_DIR = "completed_albums"
BASE_TEMP_DIR = "all_segments_history"

# ПАРАМЕТРЫ СЕРВЕРА
ACE_API_URL = "http://127.0.0.1:7860/"
MODEL_CONFIG = "acestep-v15-turbo"
LM_MODEL = "acestep-5Hz-lm-1.7B"

# ПАРАМЕТРЫ ГЕНЕРАЦИИ
TARGET_TOTAL_SECONDS = 60 * 60
TRACK_DURATION = 90
CROSSFADE_DURATION = 15
ALBUMS_TO_GENERATE = 325
MONSTER_COOLDOWN = 24 * 60 * 60 

MUSIC_KEYS = ["Am", "A#m", "Bm", "Cm", "C#m", "Dm", "D#m", "Em", "Fm", "F#m", "Gm", "G#m"]

# TELEGRAM
API_ID = апиайди
API_HASH = 'апихэш'
CHANNEL_ID = -100ченелайди
