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
        self._block_cleanup_interval = max(10, self.retention_config.max_blocks // 10)
        self._last_cleanup_timestamp = 0
        # Cleanup interval is 10% of max_timestamps, but at least 10 timestamps
        self._timestamp_cleanup_interval = max(10, self.retention_config.max_timestamps // 10)
        self._logger.info(
            f"Initialized RedisDataManager: "
            f"max_blocks={retention_config.max_blocks}, block_cleanup_interval={self._block_cleanup_interval}, "
            f"max_timestamps={retention_config.max_timestamps}, timestamp_cleanup_interval={self._timestamp_cleanup_interval}"
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

    async def _add_to_zset_with_cleanup(
        self, 
        key: str, 
        value: str, 
        score: float, 
        last_cleanup_score: float, 
        cleanup_interval: int, 
        max_items: int
    ) -> float:
        """Helper to add to zset and maintain size limit, returns new last_cleanup_score."""
        if not self._redis:
            return

        # Add the new value
        await self._redis.zadd(key, {value: score})

        if score - last_cleanup_score >= cleanup_interval:
            min_score_to_keep = score - max_items
            removed_count = await self._redis.zremrangebyscore(key, '-inf', min_score_to_keep)
            self._logger.debug(
                f"Cleaned up {removed_count} items older than score {min_score_to_keep} from ZSET '{key}'"
            )
            return score  # Update last_cleanup_score
        return last_cleanup_score

    async def add_block_data_to_zset(self, key: str, value: str, score: float):
        """Add block data to zset and maintain size limit based on max_blocks."""
        self._last_cleanup_block = await self._add_to_zset_with_cleanup(
            key=key,
            value=value,
            score=score,
            last_cleanup_score=self._last_cleanup_block,
            cleanup_interval=self._block_cleanup_interval,
            max_items=self.retention_config.max_blocks
        )

    async def add_timestamp_data_to_zset(self, key: str, value: str, score: float):
        """Add timestamp data to zset and maintain size limit based on max_timestamps."""
        self._last_cleanup_timestamp = await self._add_to_zset_with_cleanup(
            key=key,
            value=value,
            score=score,
            last_cleanup_score=self._last_cleanup_timestamp,
            cleanup_interval=self._timestamp_cleanup_interval,
            max_items=self.retention_config.max_timestamps
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