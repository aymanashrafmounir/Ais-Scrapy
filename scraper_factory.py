import logging
from typing import Dict, Type
from scrapers.base_scraper import BaseScraper
from scrapers.aisequip_scraper import AISEquipScraper
from scrapers.monroe_tractor_scraper import MonroeTractorScraper

logger = logging.getLogger(__name__)


class ScraperFactory:
    """
    Factory class for creating appropriate scraper instances
    Uses Factory Pattern for extensibility
    """
    
    # Registry mapping website types to scraper classes
    _scrapers: Dict[str, Type[BaseScraper]] = {
        'aisequip': AISEquipScraper,
        'monroetractor': MonroeTractorScraper,
    }
    
    @classmethod
    def create_scraper(cls, website_type: str, url: str, config: dict) -> BaseScraper:
        """
        Create a scraper instance for the given website type
        
        Args:
            website_type: Type of website (e.g., "aisequip")
            url: URL to scrape
            config: Configuration dictionary
            
        Returns:
            Scraper instance
            
        Raises:
            ValueError: If website type is not supported
        """
        scraper_class = cls._scrapers.get(website_type.lower())
        
        if not scraper_class:
            supported = ', '.join(cls._scrapers.keys())
            raise ValueError(
                f"Unsupported website type: '{website_type}'. "
                f"Supported types: {supported}"
            )
        
        logger.info(f"Creating scraper for website type: {website_type}")
        return scraper_class(url, config)
    
    @classmethod
    def register_scraper(cls, website_type: str, scraper_class: Type[BaseScraper]) -> None:
        """
        Register a new scraper type (for extensions)
        
        Args:
            website_type: Type identifier for the website
            scraper_class: Scraper class to register
        """
        if not issubclass(scraper_class, BaseScraper):
            raise TypeError(f"{scraper_class} must inherit from BaseScraper")
        
        cls._scrapers[website_type.lower()] = scraper_class
        logger.info(f"Registered scraper for website type: {website_type}")
    
    @classmethod
    def get_supported_types(cls) -> list:
        """Get list of supported website types"""
        return list(cls._scrapers.keys())
