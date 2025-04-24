from pydantic import BaseModel
from typing import List, Optional, Union

class HTTPXConfig(BaseModel):
    """HTTPX client configuration model."""
    pool_timeout: int
    connect_timeout: int
    read_timeout: int
    write_timeout: int

class RateLimitConfig(BaseModel):
    """RPC Rate limit configuration model."""
    requests_per_second: int


class Timeouts(BaseModel):
    """Timeout configuration model."""
    basic: int
    archival: int
    connection_init: int


class QueueConfig(BaseModel):
    """Queue configuration model."""
    num_instances: int


class ReportingConfig(BaseModel):
    """Reporting configuration model."""
    slack_url: str
    service_url: str
    telegram_url: str
    telegram_chat_id: str
    min_reporting_interval: int


class RedisDataRetentionConfig(BaseModel):
    """Redis data retention configuration model."""
    max_blocks: int  # Maximum number of blocks to keep in zsets
    ttl_seconds: int  # Default TTL for key-value pairs (24 hours)


class Redis(BaseModel):
    """Redis configuration model."""
    host: str
    port: int
    db: int
    password: Union[str, None] = None
    ssl: bool = False
    cluster_mode: bool = False
    data_retention: RedisDataRetentionConfig


class RPCNodeConfig(BaseModel):
    """RPC node configuration model."""
    url: str
    rate_limit: RateLimitConfig


class ConnectionLimits(BaseModel):
    """Connection limits configuration model."""
    max_connections: int = 100
    max_keepalive_connections: int = 50
    keepalive_expiry: int = 300


class RPCConfigBase(BaseModel):
    """Base RPC configuration model."""
    full_nodes: List[RPCNodeConfig]
    archive_nodes: Optional[List[RPCNodeConfig]]
    force_archive_blocks: Optional[int]
    retry: int
    request_time_out: int
    connection_limits: ConnectionLimits

class RPCConfigFull(RPCConfigBase):
    """Full RPC configuration model."""
    polling_interval: float
    semaphore_value: int = 20

class Preloader(BaseModel):
    """Preloader configuration model."""
    task_type: str
    module: str
    class_name: str

class PreloaderConfig(BaseModel):
    """Preloader configuration model."""
    preloaders: List[Preloader]

class Logs(BaseModel):
    """Logging configuration model."""
    debug_mode: bool
    write_to_files: bool


class Settings(BaseModel):
    """Main settings configuration model."""
    namespace: str
    source_rpc: RPCConfigFull
    httpx: HTTPXConfig
    reporting: ReportingConfig
    redis: Redis
    logs: Logs