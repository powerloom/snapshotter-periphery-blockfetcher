import json

def generate_template():
    """Generate template settings.json with placeholder values"""
    template = {
        "namespace": "${NAMESPACE}",
        "source_rpc": {
            "full_nodes": [
                {
                    "url": "${SOURCE_RPC_URL}",
                    "rate_limit": {
                        "requests_per_second": "${SOURCE_RPC_RATE_LIMIT}"
                    }
                }
            ],
            "archive_nodes": None,
            "force_archive_blocks": None,
            "retry": "${SOURCE_RPC_RETRY}",
            "request_time_out": "${SOURCE_RPC_TIMEOUT}",
            "connection_limits": {
                "max_connections": 100,
                "max_keepalive_connections": 50,
                "keepalive_expiry": 300
            },
            "polling_interval": "${SOURCE_RPC_POLLING_INTERVAL}",
            "semaphore_value": 20
        },
        "redis": {
            "host": "${REDIS_HOST}",
            "port": "${REDIS_PORT}",
            "db": "${REDIS_DB}",
            "password": "${REDIS_PASSWORD}",
            "ssl": "${REDIS_SSL}",
            "cluster_mode": "${REDIS_CLUSTER}",
            "data_retention": {
                "max_blocks": "${REDIS_MAX_BLOCKS}",
                "ttl_seconds": "${REDIS_TTL_SECONDS}",
                "max_timestamps": "${REDIS_MAX_TIMESTAMPS}"
            }
        },
        "logs": {
            "debug_mode": "${LOG_DEBUG}",
            "write_to_files": "${LOG_TO_FILES}",
            "level": "${LOG_LEVEL}"
        },
        "httpx": {
            "pool_timeout": "${HTTPX_POOL_TIMEOUT}",
            "connect_timeout": "${HTTPX_CONNECT_TIMEOUT}",
            "read_timeout": "${HTTPX_READ_TIMEOUT}",
            "write_timeout": "${HTTPX_WRITE_TIMEOUT}"
        },
        "reporting": {
            "slack_url": "${REPORTING_SLACK_URL}",
            "service_url": "${REPORTING_SERVICE_URL}",
            "telegram_url": "${REPORTING_TELEGRAM_URL}",
            "telegram_chat_id": "${REPORTING_TELEGRAM_CHAT_ID}",
            "min_reporting_interval": "${REPORTING_MIN_INTERVAL}"
        }
    }
    
    with open('config/settings.template.json', 'w') as f:
        json.dump(template, f, indent=2)

if __name__ == "__main__":
    generate_template()
