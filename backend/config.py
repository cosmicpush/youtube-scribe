import json
import os
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "soniox_api_key": "",
    "default_language": "en",
    "enable_speaker_diarization": False,
    "translation_mode": "none",  # none, to_english
}


def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        # Merge with defaults for any new keys
        return {**DEFAULT_CONFIG, **saved}
    return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    return config
