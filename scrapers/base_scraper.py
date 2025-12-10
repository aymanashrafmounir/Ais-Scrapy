from abc import ABC, abstractmethod
from typing import List, Optional, Tuple
import requests
from bs4 import BeautifulSoup
import logging
import time

from models import Machine

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for all website scrapers
    Uses Template Method pattern - defines the workflow, subclasses implement details
    """
    
    def __init__(self, url: str, config: dict, proxy_manager=None):
        """
        Initialize scraper
        
        Args:
            url: The URL to scrape
            config: Configuration dictionary with settings like user_agent, timeout, etc.
            proxy_manager: Optional ProxyManager instance for proxy support
        """
        self.url = url
        self.config = config
        self.proxy_manager = proxy_manager
        self.use_proxies = config.get('use_proxies', False) and proxy_manager is not None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config.get('user_agent', 'Mozilla/5.0'),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
    
    def scrape(self) -> Tuple[List[Machine], int]:
        """
        Scrape machines from the website
        
        Returns:
            Tuple containing:
            - List of scraped machines
            - Number of pages scraped
        """
        all_machines = []
        pages_scraped_count = 0
        
        try:
            # Get all page URLs to scrape (handles pagination)
            page_urls = self.get_pagination_urls()
            logger.info(f"Found {len(page_urls)} pages to scrape")
            
            # Scrape each page
            for i, page_url in enumerate(page_urls, 1):
                logger.info(f"Scraping page {i}/{len(page_urls)}: {page_url}")
                
                try:
                    # Fetch page content
                    soup = self._fetch_page(page_url)
                    if not soup:
                        logger.warning(f"Failed to fetch page: {page_url}")
                        continue
                    
                    # Parse machines from this page
                    machines = self.parse_page(soup)
                    all_machines.extend(machines)
                    logger.info(f"Found {len(machines)} machines on page {i}")
                    
                    # Delay between requests
                    if i < len(page_urls):
                        delay = self.config.get('delay_between_requests', 2.0)
                        time.sleep(delay)
                
                except Exception as e:
                    logger.error(f"Error scraping page {page_url}: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error in scraping process: {e}")
        
        logger.info(f"Total machines found: {len(all_machines)}")
        return all_machines
    
    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """
        Fetch and parse a page, with optional proxy support
        
        Args:
            url: URL to fetch
            
        Returns:
            BeautifulSoup object or None if failed
        """
        max_retries = self.config.get('max_retries', 3)
        timeout = self.config.get('request_timeout', 30)
        
        for attempt in range(max_retries):
            current_proxy = None
            try:
                # Get proxy if enabled
                if self.use_proxies:
                    current_proxy = self.proxy_manager.get_next_proxy()
                    if current_proxy:
                        logger.debug(f"Using proxy: {current_proxy.get('http', 'N/A')}")
                
                # Make request
                response = self.session.get(
                    url, 
                    timeout=timeout,
                    proxies=current_proxy if current_proxy else None
                )
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                return soup
            
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
                
                # If proxy was used, increment its retry count
                if current_proxy:
                    logger.debug(f"Proxy failed, incrementing retry count")
                    self.proxy_manager.increment_proxy_retry(current_proxy)
                
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"Failed to fetch {url} after {max_retries} attempts")
        
        return None
    
    def get_pagination_urls(self) -> List[str]:
        """
        Get all page URLs to scrape (handles pagination)
        Default implementation returns just the base URL
        Override this method if the website has pagination
        
        Returns:
            List of URLs to scrape
        """
        return [self.url]
    
    @abstractmethod
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """
        Parse a single page and extract machines
        Must be implemented by subclasses
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of Machine objects found on this page
        """
        pass
    
    @abstractmethod
    def extract_machine_data(self, element) -> Optional[Machine]:
        """
        Extract machine data from a single HTML element
        Must be implemented by subclasses
        
        Args:
            element: BeautifulSoup element containing machine data
            
        Returns:
            Machine object or None if extraction failed
        """
        pass
