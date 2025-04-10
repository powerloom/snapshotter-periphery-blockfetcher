from typing import List, Dict
import asyncio
import json
import os
import redis.asyncio as aioredis
from datetime import datetime
from config.loader import get_core_config
from utils.rpc import RpcHelper
from utils.logging import logger
from utils.redis.redis_conn import RedisPool

class BlockFetcher:
    MAX_BLOCK_DIFFERENCE = 10  # Maximum allowed difference from head
    TX_QUEUE_KEY = 'pending_transactions'
    _redis: aioredis.Redis

    def __init__(self):
        self.settings = get_core_config()
        self.rpc_helper = RpcHelper(self.settings.source_rpc)
        self.state_file = "block_fetcher_state.json"
        self.last_processed_block = self._load_state()
        self._logger = logger.bind(module='BlockFetcher')
        
    def _load_state(self) -> int:
        """Load the last processed block number from state file."""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    return state.get('last_processed_block', 0)
        except Exception as e:
            self._logger.error(f"Error loading state: {str(e)}")
        return 0

    def _save_state(self, block_number: int):
        """Save the last processed block number to state file."""
        try:
            state = {
                'last_processed_block': block_number,
                'last_updated': datetime.utcnow().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            self._logger.error(f"Error saving state: {str(e)}")

    def extract_transaction_hashes(self, block: Dict) -> List[str]:
        """Extract transaction hashes from a block."""
        if not block or 'transactions' not in block:
            return []
        return block['transactions']

    async def fetch_blocks_range(self, start_block: int, end_block: int) -> List[tuple[int, List[str]]]:
        """Fetch a range of blocks and extract their transaction hashes."""
        try:
            blocks = await self.rpc_helper.batch_eth_get_block(start_block, end_block)
            if not blocks:
                return []
                
            results = []
            for i, block in enumerate(blocks):
                if block and 'result' in block:
                    tx_hashes = self.extract_transaction_hashes(block['result'])
                    results.append((start_block + i, tx_hashes))
            
            return results
        except Exception as e:
            self._logger.error(f"Error fetching blocks range {start_block}-{end_block}: {str(e)}")
            return []

    async def _init(self):
        """Initialize RPC and Redis connections."""
        await self.rpc_helper.init()
        self._redis = RedisPool.get_pool()

    async def process_new_blocks(self) -> List[tuple[int, List[str]]]:
        """Process new blocks since last processed block."""
        try:
            await self._init()
            
            latest_block = await self.rpc_helper.get_current_block_number()
            
            # Check if we're too far behind
            block_difference = latest_block - self.last_processed_block
            if block_difference > self.MAX_BLOCK_DIFFERENCE:
                self._logger.warning(
                    f"🚨 Too far behind head. Last processed: {self.last_processed_block}, "
                    f"Current head: {latest_block}, Difference: {block_difference}. "
                    f"Starting from {latest_block - self.MAX_BLOCK_DIFFERENCE}"
                )
                self._logger.info(
                    f"⏭️ Skipping blocks {self.last_processed_block + 1} to "
                    f"{latest_block - self.MAX_BLOCK_DIFFERENCE - 1}"
                )
                self.last_processed_block = latest_block - self.MAX_BLOCK_DIFFERENCE
                self._save_state(self.last_processed_block)

            if latest_block <= self.last_processed_block:
                self._logger.debug(
                    f"⏸️ No new blocks to process. Last processed: {self.last_processed_block}, "
                    f"Current head: {latest_block}"
                )
                return []

            # Process all blocks up to latest
            results = await self.fetch_blocks_range(self.last_processed_block + 1, latest_block)
            if results:
                # Push tx hashes to Redis queue
                for (block_number, tx_hashes) in results:
                    if tx_hashes:
                        p = await self._redis.lpush(self.TX_QUEUE_KEY, *tx_hashes)
                        self._logger.info(f"📦 Pushed {p} tx hashes in block {block_number} to Redis queue for transaction processing")
                self.last_processed_block = latest_block
                self._save_state(self.last_processed_block)
            
            return results
        except Exception as e:
            self._logger.error(f"💥 Error processing new blocks: {str(e)}")
            return []

    async def start_continuous_processing(self, poll_interval: float = 0.1):
        """Continuously process new blocks."""
        await self.rpc_helper.init()
        
        while True:
            try:
                results = await self.process_new_blocks()
                for block_number, tx_hashes in results:
                    self._logger.info(f"⛏️ Processed block {block_number} with {len(tx_hashes)} transactions")
                
                await asyncio.sleep(poll_interval)
            except Exception as e:
                self._logger.error(f"🔥 Error in continuous processing: {str(e)}")
                await asyncio.sleep(poll_interval) 