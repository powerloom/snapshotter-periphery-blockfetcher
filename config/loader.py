import os
import json
from functools import lru_cache
from pathlib import Path
from utils.models.settings_model import Settings, PreloaderConfig
from utils.logging import logger

_logger = logger.bind(module='ConfigLoader')

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')
PRELOADER_CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'preloaders.json')

@lru_cache()
def get_core_config() -> Settings:
    """Load settings from the settings.json file."""
    _logger.info(f"📖 Loading settings from: {SETTINGS_FILE}")
    if not os.path.exists(SETTINGS_FILE):
        _logger.error(f"❌ Settings file not found at {SETTINGS_FILE}")
        raise RuntimeError(f"Settings file not found at {SETTINGS_FILE}. Ensure the entrypoint script has run.")
    try:
        with open(SETTINGS_FILE, 'r') as f:
            settings_dict = json.load(f)
        settings = Settings(**settings_dict)
        _logger.success("✅ Successfully loaded settings")
        return settings
    except json.JSONDecodeError as e:
        _logger.error(f"❌ Error decoding settings file: {e}")
        raise RuntimeError(f"Error decoding settings file ({SETTINGS_FILE}): {str(e)}")
    except Exception as e:
        _logger.error(f"❌ Error loading settings: {e}")
        raise RuntimeError(f"Error loading settings from {SETTINGS_FILE}: {str(e)}")

@lru_cache()
def get_preloader_config() -> PreloaderConfig:
    """Load preloader configuration from the preloaders.json file."""
    _logger.info(f"📖 Loading preloader config from: {PRELOADER_CONFIG_FILE}")
    if not os.path.exists(PRELOADER_CONFIG_FILE):
        _logger.error(f"❌ Preloader config file not found")
        raise RuntimeError(f"Preloader config file not found at {PRELOADER_CONFIG_FILE}.")
    try:
        with open(PRELOADER_CONFIG_FILE, 'r') as f:
            config_dict = json.load(f)
        config = PreloaderConfig(**config_dict)
        _logger.success(f"✅ Successfully loaded {len(config.preloaders)} preloader configurations")
        return config
    except json.JSONDecodeError as e:
        _logger.error(f"❌ Error decoding preloader config: {e}")
        raise RuntimeError(f"Error decoding preloader config file ({PRELOADER_CONFIG_FILE}): {str(e)}")
    except Exception as e:
        _logger.error(f"❌ Error loading preloader config: {e}")
        raise RuntimeError(f"Error loading preloader config from {PRELOADER_CONFIG_FILE}: {str(e)}")

