import json
from typing import Dict, Any
from .base import PreloaderHook
from utils.redis.redis_conn import RedisPool

class BlockDetailsDumper(PreloaderHook):
    """Dumps block details to Redis."""
    
    async def process_block(self, block_data: Dict[str, Any], namespace: str) -> None:
        redis = await RedisPool.get_pool()
        block_num = int(block_data['number'], 16)
        await redis.zadd(
            f'block_cache:{namespace}',
            {json.dumps(block_data): block_num}
        )
