from dataclasses import dataclass
from typing import Optional


@dataclass
class Machine:
    """Represents a single machine listing"""
    unique_id: str  # Extracted from URL (e.g., "w43961")
    title: str
    category: str
    link: str
    price: Optional[str] = None
    year: Optional[str] = None
    hours: Optional[str] = None
    location: Optional[str] = None
    image_url: Optional[str] = None
    country_code: Optional[str] = None  # For filtering (e.g., "CN" for China)
    
    def to_dict(self):
        """Convert to dictionary for Telegram notification"""
        return {
            'title': self.title,
            'price': self.price,
            'year': self.year,
            'hours': self.hours,
            'location': self.location,
            'link': self.link,
            'image_url': self.image_url
        }
    
    def __str__(self):
        return f"{self.title} ({self.unique_id}) - {self.price or 'N/A'}"


@dataclass
class WebsiteConfig:
    """Configuration for a single website/URL to scrape"""
    url: str
    website_type: str  # e.g., "aisequip"
    search_title: str  # e.g., "AIS Equipment - Wheel Loaders"
    enabled: bool = True
    max_items: Optional[int] = None  # Limit number of items to scrape (for Craigslist)
    categories: Optional[list] = None  # Categories list (for MachineFinder API)
    use_proxy: bool = True  # Whether to use proxy for this website (default True)
    
    def __post_init__(self):
        """Validate configuration"""
        if not self.url.startswith('http'):
            raise ValueError(f"Invalid URL: {self.url}")
        if not self.website_type:
            raise ValueError("website_type cannot be empty")
        if not self.search_title:
            raise ValueError("search_title cannot be empty")


@dataclass
class Proxy:
    """Represents a proxy server"""
    ip: str
    port: int
    protocol: str  # http, https, socks4, socks5
    country: Optional[str] = None
    anonymity: Optional[str] = None
    latency: Optional[int] = None
    username: Optional[str] = None  # For authenticated proxies
    password: Optional[str] = None  # For authenticated proxies
    is_valid: bool = True
    retry_count: int = 0
    
    def to_dict(self):
        """Convert to dictionary for requests library"""
        if self.username and self.password:
            # Authenticated proxy
            proxy_url = f"{self.protocol}://{self.username}:{self.password}@{self.ip}:{self.port}"
        else:
            # Unauthenticated proxy
            proxy_url = f"{self.protocol}://{self.ip}:{self.port}"
        
        return {
            'http': proxy_url,
            'https': proxy_url
        }
    
    def get_proxy_url(self) -> str:
        """Get formatted proxy URL"""
        if self.username and self.password:
            return f"{self.protocol}://{self.username}:{self.password}@{self.ip}:{self.port}"
        return f"{self.protocol}://{self.ip}:{self.port}"
    
    def __str__(self):
        auth_info = f" [auth]" if self.username else ""
        return f"{self.protocol}://{self.ip}:{self.port}{auth_info} ({self.country or 'Unknown'})"
