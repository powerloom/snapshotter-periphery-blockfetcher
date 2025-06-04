from typing import Optional, Any, Union
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
        
        self._last_cleanup_block_data: int = 0
        self._last_cleanup_ts_bnt: int = 0 # For block_number_to_timestamp_key
        self._last_cleanup_ts_tnb: int = 0 # For timestamp_to_block_number_key
        
        # Cleanup intervals
        self._block_cleanup_interval = max(10, self.retention_config.max_blocks // 10)
        self._timestamp_cleanup_interval = max(10, self.retention_config.max_timestamps // 10)

        self._logger.info(
            f"Initialized RedisDataManager: "
            f"max_blocks={retention_config.max_blocks}, block_cleanup_interval={self._block_cleanup_interval}, "
            f"max_timestamps={retention_config.max_timestamps}, timestamp_cleanup_interval={self._timestamp_cleanup_interval}"
        )

    async def init(self):
        """Initialize Redis connection."""
        if not self._redis:
            self._redis = await RedisPool.get_pool()

    async def get_connection(self) -> Optional[aioredis.Redis]:
        """Returns the Redis connection, initializing if necessary."""
        if not self._redis:
            await self.init()
        return self._redis

    async def get_pipeline(self) -> Optional[aioredis.client.Pipeline]:
        """Returns a Redis pipeline, initializing connection if necessary."""
        conn = await self.get_connection()
        return conn.pipeline() if conn else None

    async def set_with_ttl(self, key: str, value: Any, ttl: Optional[int] = None, pipeline: Optional[aioredis.client.Pipeline] = None):
        """Set a key with TTL, optionally using a provided pipeline."""
        conn_or_pipe = pipeline if pipeline is not None else await self.get_connection()
        if not conn_or_pipe:
            self._logger.warning("Redis connection not available for set_with_ttl.")
            return

        ttl = ttl or self.retention_config.ttl_seconds
        await conn_or_pipe.set(key, value, ex=ttl)

    async def _add_to_zset_with_cleanup(
        self, 
        key: str, 
        value: str, 
        score: int, 
        last_cleanup_score: int, 
        cleanup_interval: int, 
        max_items: int,
        connection_or_pipeline: Union[aioredis.Redis, aioredis.client.Pipeline]
    ) -> int:
        """Helper to add to zset and maintain size limit, returns new last_cleanup_score."""
        # Add the new value
        await connection_or_pipeline.zadd(key, {value: score})
        
        new_last_cleanup_score = last_cleanup_score
        if score - last_cleanup_score >= cleanup_interval:
            min_score_to_keep = score - max_items 
            await connection_or_pipeline.zremrangebyscore(key, '-inf', min_score_to_keep)
            self._logger.debug(
                f"Cleanup for ZSET '{key}': zremrangebyscore '-inf' to {min_score_to_keep}. "
                f"Current score: {score}, last cleanup: {last_cleanup_score}, interval: {cleanup_interval}."
            )
            new_last_cleanup_score = score  # Update last_cleanup_score because cleanup happened
        return new_last_cleanup_score

    async def add_block_data_to_zset(self, key: str, value: str, score: int, pipeline: Optional[aioredis.client.Pipeline] = None) -> int:
        """Add block data to zset and maintain size limit based on max_blocks."""
        conn_or_pipe = pipeline if pipeline is not None else await self.get_connection()
        if not conn_or_pipe:
            self._logger.warning(f"Redis connection not available for add_block_data_to_zset on key {key}.")
            return self._last_cleanup_block_data 

        new_cleanup_score = await self._add_to_zset_with_cleanup(
            key=key,
            value=value,
            score=score,
            last_cleanup_score=self._last_cleanup_block_data,
            cleanup_interval=self._block_cleanup_interval,
            max_items=self.retention_config.max_blocks,
            connection_or_pipeline=conn_or_pipe
        )
        if pipeline is None: # Executed immediately
            self._last_cleanup_block_data = new_cleanup_score
        return new_cleanup_score

    async def add_timestamp_by_block_num_zset(self, key: str, value: str, score: int, pipeline: Optional[aioredis.client.Pipeline] = None) -> int:
        """Add to ZSET where score is block number, value is timestamp info. Uses max_timestamps config."""
        conn_or_pipe = pipeline if pipeline is not None else await self.get_connection()
        if not conn_or_pipe:
            self._logger.warning(f"Redis connection not available for add_timestamp_by_block_num_zset on key {key}.")
            return self._last_cleanup_ts_bnt

        new_cleanup_score = await self._add_to_zset_with_cleanup(
            key=key,
            value=value,
            score=score,
            last_cleanup_score=self._last_cleanup_ts_bnt,
            cleanup_interval=self._timestamp_cleanup_interval, # Using timestamp interval
            max_items=self.retention_config.max_timestamps,    # Using max_timestamps
            connection_or_pipeline=conn_or_pipe
        )
        if pipeline is None: # Executed immediately
            self._last_cleanup_ts_bnt = new_cleanup_score
        return new_cleanup_score

    async def add_block_num_by_timestamp_zset(self, key: str, value: str, score: int, pipeline: Optional[aioredis.client.Pipeline] = None) -> int:
        """Add to ZSET where score is timestamp, value is block number info. Uses max_timestamps config."""
        conn_or_pipe = pipeline if pipeline is not None else await self.get_connection()
        if not conn_or_pipe:
            self._logger.warning(f"Redis connection not available for add_block_num_by_timestamp_zset on key {key}.")
            return self._last_cleanup_ts_tnb
            
        new_cleanup_score = await self._add_to_zset_with_cleanup(
            key=key,
            value=value,
            score=score, # Timestamp is the score
            last_cleanup_score=self._last_cleanup_ts_tnb,
            cleanup_interval=self._timestamp_cleanup_interval, # Using timestamp interval
            max_items=self.retention_config.max_timestamps,    # Using max_timestamps
            connection_or_pipeline=conn_or_pipe
        )
        if pipeline is None: # Executed immediately
            self._last_cleanup_ts_tnb = new_cleanup_score
        return new_cleanup_score
        
    async def update_last_cleanup_scores(self, 
                                       block_data_score: Optional[int] = None, 
                                       ts_bnt_score: Optional[int] = None, 
                                       ts_tnb_score: Optional[int] = None):
        """Updates the internal last cleanup scores. Call after successful pipeline execution."""
        if block_data_score is not None:
            self._last_cleanup_block_data = block_data_score
        if ts_bnt_score is not None:
            self._last_cleanup_ts_bnt = ts_bnt_score
        if ts_tnb_score is not None:
            self._last_cleanup_ts_tnb = ts_tnb_score
        self._logger.debug(
            f"Updated last cleanup scores: block_data={self._last_cleanup_block_data}, "
            f"ts_bnt={self._last_cleanup_ts_bnt}, ts_tnb={self._last_cleanup_ts_tnb}"
        )

    async def get_zset_size(self, key: str) -> int:
        """Get the current size of a zset."""
        conn = await self.get_connection()
        if not conn: return 0
        return await conn.zcard(key)

    async def get_zset_range(self, key: str, start: int = 0, end: int = -1) -> list:
        """Get a range of values from a zset."""
        conn = await self.get_connection()
        if not conn: return []
        return await conn.zrange(key, start, end)

    async def close(self):
        """Cleanup resources. RedisPool handles actual connection closing."""
        self._logger.info("RedisDataManager close called. No explicit connection closing needed here as RedisPool manages it.")
        pass 