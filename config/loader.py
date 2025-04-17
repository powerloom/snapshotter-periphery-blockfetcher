import json
from functools import lru_cache
from pathlib import Path
from utils.models.settings_model import Settings, PreloaderConfig

@lru_cache()
def get_core_config() -> Settings:
    """Load core configuration."""
    config_path = Path(__file__).parent / 'settings.json'
    with open(config_path) as f:
        return Settings.model_validate(json.load(f))

@lru_cache()
def get_preloader_config() -> PreloaderConfig:
    """Load preloader configuration."""
    config_path = Path(__file__).parent / 'preloaders.json'
    with open(config_path) as f:
        return PreloaderConfig.model_validate(json.load(f))

