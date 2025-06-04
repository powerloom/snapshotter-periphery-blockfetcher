import json
from typing import Dict, Any
from .base import PreloaderHook
from utils.redis.data_manager import RedisDataManager
from utils.models.redis_keys import block_cache_key, block_number_to_timestamp_key, timestamp_to_block_number_key
from config.loader import get_core_config

class BlockDetailsDumper(PreloaderHook):
    """Dumps block details to Redis with data retention and pipelining."""
    
    def __init__(self):
        self.settings = get_core_config()
        self.data_manager = RedisDataManager(self.settings.redis.data_retention)
        # Bind logger after data_manager is initialized, if it has its own logger setup
        self._logger = self.data_manager._logger.bind(child_module='BlockDetailsDumper') 
    
    async def init(self):
        """Initialize the data manager."""
        await self.data_manager.init()
    
    async def process_block(self, block_data: Dict[str, Any], namespace: str) -> None:
        block_num = int(block_data['number'], 16)
        timestamp = int(block_data['timestamp'], 16) if block_data.get('timestamp') else None

        pipeline = await self.data_manager.get_pipeline()
        if not pipeline:
            self._logger.error("Failed to get Redis pipeline. Aborting block processing.")
            return

        potential_block_data_cleanup_score = None
        potential_ts_bnt_cleanup_score = None
        potential_ts_tnb_cleanup_score = None

        try:
            # Add full block data
            potential_block_data_cleanup_score = await self.data_manager.add_block_data_to_zset(
                block_cache_key(namespace),
                json.dumps(block_data),
                block_num,
                pipeline=pipeline
            )

            if timestamp is not None:
                # Add to block_number_to_timestamp_key ZSET (Score: block_num, Value: timestamp)
                potential_ts_bnt_cleanup_score = await self.data_manager.add_timestamp_by_block_num_zset(
                    block_number_to_timestamp_key(namespace),
                    json.dumps(timestamp),
                    block_num,
                    pipeline=pipeline
                )
                
                # Add to timestamp_to_block_number_key ZSET (Score: timestamp, Value: block_num)
                potential_ts_tnb_cleanup_score = await self.data_manager.add_block_num_by_timestamp_zset(
                    timestamp_to_block_number_key(namespace),
                    str(block_num),
                    timestamp,
                    pipeline=pipeline
                )
            else:
                self._logger.warning(f"Timestamp not found in block_data for block {block_num}. Only full block data ZSET updated.")

            await pipeline.execute()
            self._logger.debug(f"Successfully executed Redis pipeline for block {block_num}.")

            # Update last cleanup scores in the manager after successful execution
            await self.data_manager.update_last_cleanup_scores(
                block_data_score=potential_block_data_cleanup_score,
                ts_bnt_score=potential_ts_bnt_cleanup_score,
                ts_tnb_score=potential_ts_tnb_cleanup_score
            )

        except Exception as e:
            self._logger.error(f"Error during Redis pipeline execution or setup for block {block_num}: {e}", exc_info=True)

    
    async def close(self):
        """Cleanup resources."""
        await self.data_manager.close()
