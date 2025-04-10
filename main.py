import asyncio
import signal
from config.loader import get_core_config
from utils.block_fetcher import BlockFetcher
from utils.logging import logger

class BlockProcessor:
    def __init__(self):
        self.settings = get_core_config()
        self.block_fetcher = BlockFetcher()
        self.shutdown_event = asyncio.Event()
        self._logger = logger.bind(module='BlockProcessor')
        
    async def process_blocks(self):
        """Main processing loop for blocks."""
        try:
            await self.block_fetcher.start_continuous_processing(
                poll_interval=self.settings.source_rpc.polling_interval
            )
        except Exception as e:
            self._logger.error(f"Error in block processing: {str(e)}")
            self.shutdown_event.set()

    def handle_shutdown(self, signum, frame):
        """Handle shutdown signals gracefully."""
        self._logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.shutdown_event.set()

async def main():
    processor = BlockProcessor()
    
    # Set up signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, processor.handle_shutdown)
    
    # Start the block processing
    try:
        await processor.process_blocks()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        logger.info("Shutdown complete.")

if __name__ == "__main__":
    asyncio.run(main())

