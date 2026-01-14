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
from selenium.webdriver.chrome.service import Service
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


class CraigslistScraper(BaseScraper):
    """Scraper for Craigslist with marker-based tracking and Selenium"""
    
    def __init__(self, url: str, config: dict, proxy_manager=None):
        super().__init__(url, config, proxy_manager=proxy_manager)
    
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
                # Suppress Chrome's internal error logs (GPU, GCM, DevTools warnings)
                chrome_options.add_argument('--log-level=3')  # Only show fatal errors
                chrome_options.add_argument('--silent')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_argument('--remote-debugging-port=0')  # Disable DevTools listening
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
                chrome_options.add_argument('--disable-background-networking')
                chrome_options.add_argument('--disable-sync')
                chrome_options.add_argument('--disable-translate')
                chrome_options.page_load_strategy = 'eager'
                
                # Initialize driver with suppressed logs
                service = Service(ChromeDriverManager().install(), log_output=os.devnull)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.set_page_load_timeout(60)
                driver.get(self.url)
                
                # Wait for search results to load (up to 20 seconds)
                wait = WebDriverWait(driver, 20)
                try:
                    # Try to wait for 'a.main' elements first
                    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a.main')))
                    logger.debug("Found 'a.main' elements")
                except:
                    try:
                        # Fallback to old selector
                        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'li.cl-search-result')))
                        logger.debug("Found 'li.cl-search-result' elements")
                    except:
                        logger.warning("Timeout waiting for search results to load")
                
                # Give it a bit more time for all content to render
                time.sleep(2)
                
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
        
        # Find all result items - Craigslist uses <div class="cl-search-result" data-pid="...">
        results = soup.find_all('div', class_='cl-search-result')
        
        if not results:
            logger.warning(f"No Craigslist results found with 'div.cl-search-result' selector")
            return [], None
        
        logger.info(f"Found {len(results)} total results on page")
        
        for idx, item in enumerate(results):
            try:
                # Check if we've reached the max_items limit
                if max_items and len(machines) >= max_items:
                    logger.info(f"Reached max_items limit ({max_items}), stopping")
                    break
                
                # Extract unique ID from data-pid attribute
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
                machine = self.extract_machine_data(item, unique_id)
                if machine:
                    machines.append(machine)
                    
            except Exception as e:
                logger.error(f"Error parsing Craigslist item {idx}: {e}")
                continue
        
        return machines, first_item_id
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """Not used - using _parse_with_marker instead"""
        pass
    
    def extract_machine_data(self, element, unique_id: str) -> Optional[Machine]:
        """
        Extract data from a single Craigslist result item
        
        Args:
            element: BeautifulSoup element for the result (div.cl-search-result tag)
            unique_id: The unique ID from data-pid attribute
            
        Returns:
            Machine object or None
        """
        try:
            # Element is a div.cl-search-result containing all the listing info
            
            # Extract link from a.main
            main_link = element.find('a', class_='main')
            link = ''
            if main_link:
                link = main_link.get('href', '')
                if link and not link.startswith('http'):
                    link = urljoin('https://craigslist.org', link)
            
            # Extract title from a.posting-title > span.label
            title = None
            title_elem = element.find('a', class_='posting-title')
            if title_elem:
                title_label = title_elem.find('span', class_='label')
                title = title_label.get_text(strip=True) if title_label else title_elem.get_text(strip=True)
            
            if not title:
                # Fallback to title attribute on the div
                title = element.get('title', '')
            
            if not title:
                logger.debug(f"No title found for item {unique_id}")
                return None
            
            # Extract price from span.priceinfo
            price = None
            price_elem = element.find('span', class_='priceinfo')
            if price_elem:
                price = price_elem.get_text(strip=True)
            
            # Extract location from div.meta
            location = None
            meta_elem = element.find('div', class_='meta')
            if meta_elem:
                meta_text = meta_elem.get_text(strip=True)
                # Location is typically after the date, separated by non-breaking space or span.separator
                # Format is usually like "11/23 Watkinsville" or "11/23•Watkinsville" or "10 mins agoWatkinsville"
                # Remove common time indicators
                for time_indicator in ['mins ago', 'min ago', 'hours ago', 'hour ago', 'days ago', 'day ago']:
                    meta_text = meta_text.replace(time_indicator, '')
                
                # Split by common separators
                parts = meta_text.split(maxsplit=1)
                if len(parts) > 1:
                    # Remove any separator characters and clean up
                    location = parts[1].replace('•', '').strip()
                elif len(parts) == 1 and parts[0]:
                    # If there's only one part after cleaning, check if it's not a date
                    if '/' not in parts[0]:
                        location = parts[0].replace('•', '').strip()
            
            # Extract image URL from img within a.main
            image_url = None
            if main_link:
                img_elem = main_link.find('img')
                if img_elem:
                    # Check data-image-index attribute or src
                    image_url = img_elem.get('src', '')
                    # Filter out placeholder/loading images
                    if 'data:image' in image_url or not image_url:
                        image_url = None
            
            machine = Machine(
                unique_id=unique_id,
                title=title,
                category='Heavy Equipment',  # Craigslist category
                link=link,
                price=price,
                location=location,
                image_url=image_url
            )
            
            logger.debug(f"Extracted: {title} ({unique_id}) - Price: {price}, Loc: {location}")
            return machine
            
        except Exception as e:
            logger.error(f"Error extracting Craigslist machine data: {e}")
            return None
