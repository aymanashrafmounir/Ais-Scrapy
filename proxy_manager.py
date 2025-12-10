"""
Proxy Manager Module
Coordinates proxy fetching and rotation
"""
import logging
import random
from typing import Optional
from database import DatabaseHandler
from proxy_fetcher import ProxyFetcher
from models import Proxy

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy lifecycle: fetching, rotation, cleanup"""
    
    def __init__(self, db: DatabaseHandler, telegram_notifier, min_proxy_count: int = 10,
                 test_url: str = "http://httpbin.org/ip"):
        """
        Initialize proxy manager
        
        Args:
            db: Database handler instance
            telegram_notifier: TelegramNotifier instance for user communication
            min_proxy_count: Minimum number of valid proxies to maintain
            test_url: URL for proxy validation (unused, kept for compatibility)
        """
        self.db = db
        self.min_proxy_count = min_proxy_count
        self.fetcher = ProxyFetcher(telegram_notifier)
        self.current_proxy_index = 0
    
    async def check_and_refill_proxies(self) -> int:
        """
        Check if proxies are low and fetch new ones if needed
        This will BLOCK and wait for user to send proxies via Telegram if needed
        
        Returns:
            Number of new proxies added
        """
        stats = self.db.get_proxy_count()
        valid_count = stats['valid']
        
        logger.info(f"Proxy count: {valid_count} valid, {stats['failed']} failed, {stats['total']} total")
        
        if valid_count >= self.min_proxy_count:
            logger.info(f"Sufficient proxies available ({valid_count} >= {self.min_proxy_count})")
            return 0
        
        logger.info(f"Low on proxies ({valid_count} < {self.min_proxy_count}), requesting from user via Telegram...")
        
        # Fetch proxies from Telegram user (BLOCKS HERE)
        proxies = await self.fetcher.fetch_proxies()
        
        if not proxies:
            logger.error("No proxies received from user")
            return 0
        
        # Add all proxies directly to database (no validation)
        added_count = 0
        for proxy in proxies:
            if self.db.save_proxy(
                ip=proxy.ip,
                port=proxy.port,
                protocol=proxy.protocol,
                country=proxy.country,
                anonymity=proxy.anonymity,
                latency=None,  # No latency since we're not testing
                username=proxy.username,
                password=proxy.password
            ):
                added_count += 1
        
        logger.info(f"Added {added_count} proxies to database (no validation)")
        return added_count
    
    def get_next_proxy(self) -> Optional[dict]:
        """
        Get next available proxy (rotation logic)
        Excludes proxies with retry_count >= 10
        
        Returns:
            Proxy dictionary for requests library, or None if no proxies available
        """
        proxies = self.db.get_valid_proxies()
        
        if not proxies:
            logger.warning("No valid proxies available")
            return None
        
        # Random selection for better distribution
        proxy_row = random.choice(proxies)
        
        # Extract proxy data from database row
        # Columns: id, ip, port, protocol, country, anonymity, latency, is_valid, retry_count, last_checked, created_at, last_used
        proxy_id = proxy_row[0]
        ip = proxy_row[1]
        port = proxy_row[2]
        protocol = proxy_row[3]
        
        # Mark proxy as used
        self.db.mark_proxy_used(proxy_id)
        
        # Create proxy dictionary for requests
        proxy_url = f"{protocol}://{ip}:{port}"
        proxy_dict = {
            'http': proxy_url,
            'https': proxy_url,
            '_proxy_id': proxy_id  # Store ID for retry tracking
        }
        
        logger.debug(f"Selected proxy: {proxy_url} (ID: {proxy_id})")
        return proxy_dict
    
    def increment_proxy_retry(self, proxy_dict: dict) -> None:
        """
        Increment retry count for a proxy when it fails
        
        Args:
            proxy_dict: Proxy dictionary containing _proxy_id
        """
        proxy_id = proxy_dict.get('_proxy_id')
        if proxy_id:
            self.db.increment_proxy_retry(proxy_id)
    
    def cleanup_cycle(self) -> int:
        """
        Clean up proxies with retry_count >= 10
        Called after each scraping cycle
        
        Returns:
            Number of proxies removed
        """
        deleted_count = self.db.cleanup_failed_proxies()
        
        if deleted_count > 0:
            # Check if we need to refill after cleanup
            self.check_and_refill_proxies()
        
        return deleted_count
    
    def get_stats(self) -> dict:
        """
        Get proxy statistics
        
        Returns:
            Dictionary with proxy counts
        """
        return self.db.get_proxy_count()
