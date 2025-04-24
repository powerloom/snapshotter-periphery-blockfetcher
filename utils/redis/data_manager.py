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
        self._last_cleanup_block = 0
        # Cleanup interval is 10% of max_blocks, but at least 10 blocks
        self._cleanup_interval = max(10, self.retention_config.max_blocks // 10)
        self._logger.info(
            f"Initialized RedisDataManager with max_blocks={retention_config.max_blocks}, "
            f"cleanup_interval={self._cleanup_interval}"
        )

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
        
        # Only cleanup periodically based on block number
        if score - self._last_cleanup_block >= self._cleanup_interval:
            # Remove blocks older than max_blocks blocks ago
            min_block = score - self.retention_config.max_blocks
            removed = await self._redis.zremrangebyscore(key, '-inf', min_block)
            self._last_cleanup_block = score
            self._logger.debug(
                f"Cleaned up {removed} blocks older than {min_block} from {key}"
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