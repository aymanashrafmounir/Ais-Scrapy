"""
Proxy Fetcher Module
Fetches proxies from Telegram user input
"""
import logging
from typing import List, Optional
from models import Proxy
from telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class ProxyFetcher:
    """Fetch proxies from Telegram user input"""
    
    def __init__(self, telegram_notifier: TelegramNotifier):
        """
        Initialize proxy fetcher
        
        Args:
            telegram_notifier: TelegramNotifier instance for messaging
        """
        self.notifier = telegram_notifier
    
    async def fetch_proxies(self) -> List[Proxy]:
        """
        Request proxies from user via Telegram and wait for response
        This will BLOCK until user responds or timeout occurs
        
        Returns:
            List of Proxy objects parsed from user's message
        """
        try:
            logger.info("Requesting proxies from user via Telegram...")
            
            # Send request message
            if not await self.notifier.request_proxies_from_user():
                logger.error("Failed to send proxy request message")
                return []
            
            # Wait for user's response (BLOCKS HERE)
            proxy_text = await self.notifier.wait_for_proxy_response(timeout=3600)  # 1 hour timeout
            
            if not proxy_text:
                logger.error("No proxy response received from user (timeout or error)")
                return []
            
            # Parse proxies from text
            proxies = self._parse_proxies_from_text(proxy_text)
            logger.info(f"Successfully parsed {len(proxies)} proxies from Telegram message")
            
            return proxies
        
        except Exception as e:
            logger.error(f"Unexpected error fetching proxies from Telegram: {e}")
            return []
    
    def _parse_proxies_from_text(self, text: str) -> List[Proxy]:
        """
        Parse proxies from user's text message
        
        Supported formats:
        - ip:port
        - ip:port:username:password
        
        Args:
            text: Raw text from user's message
            
        Returns:
            List of validated Proxy objects
        """
        proxies = []
        # Use splitlines() to handle all types of newlines (\n, \r\n, \r)
        lines = text.strip().splitlines()
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            try:
                proxy = self._parse_proxy_line(line)
                if proxy:
                    proxies.append(proxy)
                else:
                    logger.warning(f"Line {line_num}: Could not parse proxy: {line}")
            except Exception as e:
                logger.warning(f"Line {line_num}: Error parsing '{line}': {e}")
                continue
        
        return proxies
    
    def _parse_proxy_line(self, line: str) -> Optional[Proxy]:
        """
        Parse a single proxy line
        
        Formats:
        - ip:port
        - ip:port:username:password
        
        Args:
            line: Single line containing proxy info
            
        Returns:
            Proxy object or None if parsing failed
        """
        try:
            parts = line.split(':')
            
            if len(parts) == 2:
                # Format: ip:port
                ip = parts[0].strip()
                port = int(parts[1].strip())
                
                return Proxy(
                    ip=ip,
                    port=port,
                    protocol='http',  # Default to http
                    username=None,
                    password=None
                )
            
            elif len(parts) == 4:
                # Format: ip:port:username:password
                ip = parts[0].strip()
                port = int(parts[1].strip())
                username = parts[2].strip()
                password = parts[3].strip()
                
                return Proxy(
                    ip=ip,
                    port=port,
                    protocol='http',  # Default to http
                    username=username,
                    password=password
                )
            
            else:
                logger.warning(f"Invalid proxy format (expected ip:port or ip:port:user:pass): {line}")
                return None
                
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing proxy line '{line}': {e}")
            return None
