import json
from functools import lru_cache
from utils.models.settings_model import Settings

@lru_cache
def get_core_config() -> Settings:
    """Load settings from the settings.json file."""
    try:
        with open('config/settings.json', 'r') as f:
            settings_dict = json.load(f)
        return Settings(**settings_dict)
    except FileNotFoundError:
        raise RuntimeError("Settings file not found. Ensure the entrypoint script has run.")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Error decoding settings file: {str(e)}")

