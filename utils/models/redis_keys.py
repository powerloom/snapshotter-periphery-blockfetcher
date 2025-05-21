def get_preloader_config_key() -> str:
    """Get the preloader config key."""
    return "preloader_config"

def block_cache_key(namespace: str) -> str:
    """Key for sorted set storing cached block details."""
    return f'block_cache:{namespace}'

def block_tx_htable_key(namespace: str, block_number: int) -> str:
    return f'block_txs:{block_number}:{namespace}'

def event_detector_last_processed_block(namespace: str) -> str:
    return f'SystemEventDetector:lastProcessedBlock:{namespace}'

def block_number_to_timestamp_key(namespace: str) -> str:
    return f'blockNumberToTimestamp:{namespace}'

def timestamp_to_block_number_key(namespace: str) -> str:
    return f'timestampToBlockNumber:{namespace}'
