import logging
from typing import Dict, Type
from scrapers.base_scraper import BaseScraper
from scrapers.aisequip_scraper import AISEquipScraper
from scrapers.monroe_tractor_scraper import MonroeTractorScraper
from scrapers.craigslist_scraper import CraigslistScraper
from scrapers.machinefinder_scraper import MachineFinderScraper

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
        'craigslist': CraigslistScraper,
        'machinefinder': MachineFinderScraper,
    }
    
    @classmethod
    def create_scraper(cls, website_type: str, url: str, config: dict, categories: list = None) -> BaseScraper:
        """
        Create a scraper instance for the given website type
        
        Args:
            website_type: Type of website (e.g., "aisequip", "machinefinder")
            url: URL to scrape
            config: Configuration dictionary
            categories: Optional list of categories (for MachineFinder)
            
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
        
        # MachineFinder needs categories parameter
        if website_type.lower() == 'machinefinder':
            return scraper_class(url, config, categories=categories)
        else:
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
