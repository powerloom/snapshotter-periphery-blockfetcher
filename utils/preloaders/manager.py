import importlib
from typing import List, Type
from utils.models.settings_model import PreloaderConfig, Preloader
from .base import PreloaderHook

class PreloaderManager:
    """Manages preloader hook initialization and loading."""
    
    @staticmethod
    def load_hook(preloader_config: Preloader) -> PreloaderHook:
        """Load a single preloader hook from config."""
        try:
            module = importlib.import_module(preloader_config.module)
            hook_class = getattr(module, preloader_config.class_name)
            return hook_class()
        except Exception as e:
            raise ValueError(f"Failed to load preloader hook {preloader_config.class_name}: {e}")

    @classmethod
    def load_hooks(cls, config: PreloaderConfig) -> List[PreloaderHook]:
        """Load all configured preloader hooks."""
        hooks = []
        for preloader in config.preloaders:
            hook = cls.load_hook(preloader)
            hooks.append(hook)
        return hooks
