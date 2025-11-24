import requests
import logging
import time
from bs4 import BeautifulSoup
from typing import List, Optional, Tuple
from urllib.parse import urljoin
from models import Machine
from scrapers.base_scraper import BaseScraper
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

logger = logging.getLogger(__name__)


class CraigslistScraper(BaseScraper):
    """Scraper for Craigslist with marker-based tracking and Selenium"""
    
    def scrape(self, current_marker: Optional[str] = None, max_items: Optional[int] = None) -> Tuple[List[Machine], Optional[str]]:
        """
        Scrape Craigslist with marker-based tracking using Selenium
        
        Args:
            current_marker: The marker ID to stop at (from previous scrape)
            max_items: Maximum number of items to scrape (optional limit)
            
        Returns:
            Tuple of (new_machines, first_item_id)
        """
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            driver = None
            try:
                logger.info(f"Starting Craigslist scrape with Selenium (marker: {current_marker}, limit: {max_items or 'unlimited'}) - Attempt {attempt + 1}/{max_retries}")
                
                # Setup Chrome options for headless mode
                chrome_options = Options()
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--disable-software-rasterizer')
                chrome_options.add_argument('--disable-extensions')
                chrome_options.add_argument('--disable-infobars')
                chrome_options.add_argument('--window-size=1920,1080')
                chrome_options.page_load_strategy = 'eager'
                
                # Initialize driver
                driver = webdriver.Chrome(options=chrome_options)
                driver.set_page_load_timeout(60)
                driver.get(self.url)
                
                # Wait for page to load
                time.sleep(3)
                
                # Parse the fully loaded page
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Parse with marker logic
                machines, first_item_id = self._parse_with_marker(soup, current_marker, max_items)
                
                logger.info(f"Scraped {len(machines)} new machines (first ID: {first_item_id})")
                return machines, first_item_id
                
            except Exception as e:
                logger.error(f"Error scraping Craigslist (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            finally:
                if driver:
                    driver.quit()
        
        return [], None
    
    def _parse_with_marker(self, soup: BeautifulSoup, marker: Optional[str], max_items: Optional[int] = None) -> Tuple[List[Machine], Optional[str]]:
        """
        Parse page and stop at marker or max_items limit
        
        Args:
            soup: BeautifulSoup object
            marker: ID to stop at
            max_items: Maximum items to return
            
        Returns:
            Tuple of (new_machines, first_item_id)
        """
        machines = []
        first_item_id = None
        
        # Find all result items (Craigslist uses galleries)
        results = soup.find_all('div', class_='cl-search-result')
        
        if not results:
            logger.warning(f"No Craigslist results found. Trying alternative selector...")
            # Try alternative selector for combined classes
            results = soup.select('div.cl-search-result.cl-search-view-mode-gallery')
        
        if not results:
            logger.warning("No Craigslist results found with any selector")
            return [], None
        
        logger.info(f"Found {len(results)} total results on page")
        
        for idx, item in enumerate(results):
            try:
                # Check if we've reached the max_items limit
                if max_items and len(machines) >= max_items:
                    logger.info(f"Reached max_items limit ({max_items}), stopping")
                    break
                
                # Extract data-pid as unique ID
                unique_id = item.get('data-pid')
                if not unique_id:
                    logger.debug(f"Skipping item {idx}: no data-pid")
                    continue
                
                # Save first item ID
                if idx == 0:
                    first_item_id = unique_id
                    logger.debug(f"First item ID: {first_item_id}")
                
                # Stop if we reached the marker
                if marker and unique_id == marker:
                    logger.info(f"Reached marker {marker} at position {idx}, stopping")
                    break
                
                # Extract machine data
                machine = self.extract_machine_data(item)
                if machine:
                    machines.append(machine)
                    
            except Exception as e:
                logger.error(f"Error parsing Craigslist item {idx}: {e}")
                continue
        
        return machines, first_item_id
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """Not used - using _parse_with_marker instead"""
        pass
    
    def extract_machine_data(self, element) -> Optional[Machine]:
        """
        Extract data from a single Craigslist result item
        
        Args:
            element: BeautifulSoup element for the result
            
        Returns:
            Machine object or None
        """
        try:
            # Get unique ID from data-pid
            unique_id = element.get('data-pid')
            if not unique_id:
                return None
            
            # Extract title
            title_elem = element.find('a', class_='posting-title')
            if not title_elem:
                return None
            
            title_label = title_elem.find('span', class_='label')
            title = title_label.get_text(strip=True) if title_label else element.get('title', '')
            
            # Extract URL
            link = title_elem.get('href', '')
            if link and not link.startswith('http'):
                link = urljoin('https://craigslist.org', link)
            
            # Extract price
            price_elem = element.find('span', class_='priceinfo')
            price = price_elem.get_text(strip=True) if price_elem else None
            
            # Extract location and time from meta
            location = None
            meta_elem = element.find('div', class_='meta')
            if meta_elem:
                meta_text = meta_elem.get_text(strip=True)
                # Location is after separator
                if '•' in meta_text:
                    location = meta_text.split('•')[-1].strip()
            
            # Extract image URL
            image_url = None
            img_elem = element.find('img')
            if img_elem:
                image_url = img_elem.get('src', '')
            
            machine = Machine(
                unique_id=unique_id,
                title=title,
                category='Heavy Equipment',  # Craigslist category
                link=link,
                price=price,
                location=location,
                image_url=image_url
            )
            
            logger.debug(f"Extracted: {title} ({unique_id})")
            return machine
            
        except Exception as e:
            logger.error(f"Error extracting Craigslist machine data: {e}")
            return None
