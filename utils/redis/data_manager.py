from typing import Optional, Any
import redis.asyncio as aioredis
from utils.logging import logger
from utils.models.settings_model import RedisDataRetentionConfig
from utils.redis.redis_conn import RedisPool

class RedisDataManager:
    """Manages Redis data retention and cleanup."""
    
    def __init__(self, retention_config: RedisDataRetentionConfig):
        self.retention_config = retention_config
        self._redis: Optional[aioredis.Redis] = None
        self._logger = logger.bind(module='RedisDataManager')

    async def init(self):
        """Initialize Redis connection."""
        self._redis = await RedisPool.get_pool()

    async def set_with_ttl(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set a key with TTL."""
        if not self._redis:
            return

        ttl = ttl or self.retention_config.ttl_seconds
        await self._redis.set(key, value, ex=ttl)

    async def add_to_zset(self, key: str, value: str, score: float):
        """Add to zset and maintain size limit."""
        if not self._redis:
            return

        # Add the new value
        await self._redis.zadd(key, {value: score})
        
        # Remove old entries if we exceed the limit
        # We use zremrangebyrank to remove the oldest entries (lowest scores)
        # The -max_blocks-1 ensures we keep exactly max_blocks entries
        await self._redis.zremrangebyrank(
            key,
            0,
            -self.retention_config.max_blocks - 1
        )

    async def get_zset_size(self, key: str) -> int:
        """Get the current size of a zset."""
        if not self._redis:
            return 0
        return await self._redis.zcard(key)

    async def get_zset_range(self, key: str, start: int = 0, end: int = -1) -> list:
        """Get a range of values from a zset."""
        if not self._redis:
            return []
        return await self._redis.zrange(key, start, end)

    async def close(self):
        """Cleanup resources."""
        pass 