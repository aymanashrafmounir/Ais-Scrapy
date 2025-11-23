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
    
    def __post_init__(self):
        """Validate configuration"""
        if not self.url.startswith('http'):
            raise ValueError(f"Invalid URL: {self.url}")
        if not self.website_type:
            raise ValueError("website_type cannot be empty")
        if not self.search_title:
            raise ValueError("search_title cannot be empty")

