from abc import ABC, abstractmethod
from typing import Dict, Any

class PreloaderHook(ABC):
    """Base class for preloader hooks."""
    
    async def init(self) -> None:
        """Initialize the preloader hook."""
        pass
    
    @abstractmethod
    async def process_block(self, block_data: Dict[str, Any], namespace: str) -> None:
        """Process a block."""
        pass
    
    async def close(self) -> None:
        """Cleanup resources."""
        pass
