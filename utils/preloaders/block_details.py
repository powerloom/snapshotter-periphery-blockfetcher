import json
from typing import Dict, Any
from .base import PreloaderHook
from utils.redis.data_manager import RedisDataManager
from utils.models.redis_keys import block_cache_key, block_number_to_timestamp_key
from config.loader import get_core_config

class BlockDetailsDumper(PreloaderHook):
    """Dumps block details to Redis with data retention."""
    
    def __init__(self):
        self.settings = get_core_config()
        self.data_manager = RedisDataManager(self.settings.redis.data_retention)
    
    async def init(self):
        """Initialize the data manager."""
        await self.data_manager.init()
    
    async def process_block(self, block_data: Dict[str, Any], namespace: str) -> None:
        block_num = int(block_data['number'], 16)
        timestamp = int(block_data['timestamp'], 16) if block_data.get('timestamp') else None
        await self.data_manager.add_block_data_to_zset(
            block_cache_key(namespace),
            json.dumps(block_data),
            block_num
        )
        if timestamp is not None:
            await self.data_manager.add_timestamp_data_to_zset(
                block_number_to_timestamp_key(namespace),
                json.dumps(timestamp),
                block_num
            )
        else:
            self._logger.warning(f"Timestamp not found in block_data for block {block_num}, not adding to timestamp ZSET.")
    
    async def close(self):
        """Cleanup resources."""
        await self.data_manager.close()
