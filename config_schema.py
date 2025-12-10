import json
import logging
from typing import List, Dict, Any
from pathlib import Path
from models import WebsiteConfig

logger = logging.getLogger(__name__)


class Config:
    """Configuration manager for the scraping system"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self._raw_config: Dict[str, Any] = {}
        self.telegram_token: str = ""
        self.telegram_chat_id: str = ""  # Legacy/Default
        self.telegram_chat_ids: Dict[str, str] = {}  # Map website_type -> chat_id
        self.websites: List[WebsiteConfig] = []
        self.database_path: str = "machines.db"
        self.scraping_delay: float = 2.0
        self.url_delay: float = 0.0  # Delay between processing different URLs
        self.request_timeout: int = 30
        self.max_retries: int = 3
        self.loop_interval: int = 0
        self.user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    @property
    def raw_config(self) -> Dict[str, Any]:
        """Expose raw configuration dict"""
        return self._raw_config
        
    def load(self) -> None:
        """Load configuration from JSON file"""
        config_file = Path(self.config_path)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        logger.info(f"Loading configuration from {self.config_path}")
        
        with open(config_file, 'r', encoding='utf-8') as f:
            self._raw_config = json.load(f)
        
        self._parse_config()
        self._validate_config()
        
        logger.info(f"Configuration loaded: {len(self.websites)} websites configured")
    
    def _parse_config(self) -> None:
        """Parse the raw configuration into typed objects"""
        # Telegram settings
        telegram = self._raw_config.get('telegram', {})
        self.telegram_token = telegram.get('bot_token', '')
        
        # Support both new chat_ids dict and legacy chat_id string
        chat_ids = telegram.get('chat_ids')
        if chat_ids and isinstance(chat_ids, dict):
            self.telegram_chat_ids = chat_ids
            # Use default as fallback for legacy property
            self.telegram_chat_id = chat_ids.get('default', '')
        else:
            # Legacy support
            self.telegram_chat_id = telegram.get('chat_id', '')
            self.telegram_chat_ids = {'default': self.telegram_chat_id}
        
        # Database settings
        self.database_path = self._raw_config.get('database', {}).get('path', 'machines.db')
        
        # Scraping settings
        scraping = self._raw_config.get('scraping', {})
        self.scraping_delay = scraping.get('delay_between_requests', 2.0)
        self.url_delay = scraping.get('delay_between_urls', 0.0)
        self.request_timeout = scraping.get('request_timeout', 30)
        self.max_retries = scraping.get('max_retries', 3)
        self.loop_interval = scraping.get('loop_interval_seconds', 0)
        self.user_agent = scraping.get('user_agent', self.user_agent)
        
        # Website configurations
        websites = []
        for site in self._raw_config.get('websites', []):
            try:
                website = WebsiteConfig(
                    url=site['url'],
                    website_type=site['website_type'],
                    search_title=site['search_title'],
                    enabled=site.get('enabled', True),
                    max_items=site.get('max_items', None),  # Parse max_items from config
                    categories=site.get('categories', None),  # Parse categories for MachineFinder
                    use_proxy=site.get('use_proxy', True)  # Parse use_proxy option (default True)
                )
                websites.append(website)
            except (KeyError, ValueError) as e:
                logger.error(f"Failed to parse website config: {site}. Error: {e}")
                continue
        
        self.websites = websites
    
    def _validate_config(self) -> None:
        """Validate the configuration"""
        errors = []
        
        if not self.telegram_token:
            errors.append("Telegram bot token is missing")
        
        if not self.telegram_chat_ids and not self.telegram_chat_id:
            errors.append("Telegram chat ID is missing")
        
        if not self.websites:
            errors.append("No websites configured")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    def get_enabled_websites(self) -> List[WebsiteConfig]:
        """Return only enabled websites"""
        return [site for site in self.websites if site.enabled]


def load_config(config_path: str = "config.json") -> Config:
    """Load and return configuration"""
    config = Config(config_path)
    config.load()
    return config
