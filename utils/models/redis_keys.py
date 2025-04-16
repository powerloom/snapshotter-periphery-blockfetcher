def get_preloader_config_key() -> str:
    """Get the preloader config key."""
    return "preloader_config"

def block_cache_key(namespace: str) -> str:
    """Key for sorted set storing cached block details."""
    return f'block_cache:{namespace}'

