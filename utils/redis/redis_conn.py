import redis.exceptions
from redis import asyncio as aioredis
from redis.asyncio.connection import ConnectionPool
from utils.logging import logger
from config.loader import get_core_config
from typing import Optional

class RedisPool:
    """Singleton Redis connection pool manager."""
    
    _instance: Optional['RedisPool'] = None
    _pool: Optional[aioredis.Redis] = None
    _logger = logger.bind(module='RedisPool')

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):
            self.settings = get_core_config()
            self.initialized = True

    @classmethod
    def get_pool(cls) -> aioredis.Redis:
        """Get or create Redis connection pool."""
        if cls._pool is None:
            instance = cls()
            redis_settings = instance.settings.redis
            
            # Construct Redis URL with credentials if present
            url = f"redis://"
            if redis_settings.password:
                url += f":{redis_settings.password}@"
            url += f"{redis_settings.host}:{redis_settings.port}/{redis_settings.db}"
            
            # Create connection pool with retry on ReadOnlyError
            pool = ConnectionPool.from_url(
                url=url,
                max_connections=100,  # Reasonable default for most use cases
                decode_responses=False,  # Keep raw bytes for blockchain data
                retry_on_error=[redis.exceptions.ReadOnlyError]
            )
            
            cls._pool = aioredis.Redis(
                connection_pool=pool,
                ssl=redis_settings.ssl
            )
            instance._logger.info("Redis connection pool initialized")
        
        return cls._pool

    @classmethod
    async def close(cls):
        """Close the Redis connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            cls._instance._logger.info("Redis connection pool closed")

# For backwards compatibility, provide the old function name
# but use the new pool implementation internally
async def get_aioredis_pool(pool_size: int = 100) -> aioredis.Redis:
    """Legacy function for getting a Redis pool. Uses the new RedisPool implementation.
    
    Args:
        pool_size (int): Maximum number of connections (default: 100)
    
    Returns:
        aioredis.Redis: Redis client instance with connection pooling
    """
    return await RedisPool.get_pool()
