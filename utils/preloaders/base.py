from abc import ABC, abstractmethod
from typing import Dict, Any

class PreloaderHook(ABC):
    """Base class for preloader hooks."""
    
    @abstractmethod
    async def process_block(self, block_data: Dict[str, Any], namespace: str) -> None:
        """Process a block after it's fetched.
        
        Args:
            block_data: The raw block data from the RPC
            namespace: The current service namespace
        """
        pass
