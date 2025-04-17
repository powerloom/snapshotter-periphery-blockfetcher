import importlib
from typing import List, Type
from utils.models.settings_model import PreloaderConfig, Preloader
from utils.logging import logger
from .base import PreloaderHook

class PreloaderManager:
    """Manages preloader hook initialization and loading."""
    _logger = logger.bind(module='PreloaderManager')

    @classmethod
    def load_hook(cls, preloader_config: Preloader) -> PreloaderHook:
        """Load a single preloader hook."""
        cls._logger.info(f"📥 Loading preloader hook: {preloader_config.class_name}")
        try:
            module = importlib.import_module(preloader_config.module)
            hook_class = getattr(module, preloader_config.class_name)
            hook = hook_class()
            cls._logger.success(f"✅ Successfully loaded {preloader_config.class_name}")
            return hook
        except Exception as e:
            cls._logger.error(f"❌ Failed to load {preloader_config.class_name}: {e}")
            raise ValueError(f"Failed to load preloader hook {preloader_config.class_name}: {e}")

    @classmethod
    def load_hooks(cls, config: PreloaderConfig) -> List[PreloaderHook]:
        """Load all configured preloader hooks."""
        cls._logger.info(f"📦 Loading {len(config.preloaders)} preloader hooks")
        hooks = []
        for preloader in config.preloaders:
            hook = cls.load_hook(preloader)
            hooks.append(hook)
        return hooks
