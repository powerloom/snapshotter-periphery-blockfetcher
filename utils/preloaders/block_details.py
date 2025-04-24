import json
from typing import Dict, Any
from .base import PreloaderHook
from utils.redis.data_manager import RedisDataManager
from utils.models.redis_keys import block_cache_key
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
        await self.data_manager.add_to_zset(
            block_cache_key(namespace),
            json.dumps(block_data),
            block_num
        )
    
    async def close(self):
        """Cleanup resources."""
        await self.data_manager.close()
