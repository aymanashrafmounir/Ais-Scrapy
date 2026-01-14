import logging
import time
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os
from models import Machine
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class MascusScraper(BaseScraper):
    """Mascus scraper with marker-based tracking (like Craigslist)"""
    
    def __init__(self, url: str, config: dict, proxy_manager=None):
        super().__init__(url, config, proxy_manager=proxy_manager)
    
    def scrape(self, current_marker: Optional[str] = None, max_items: Optional[int] = None) -> Tuple[List[Machine], Optional[str]]:
        """
        Scrape Mascus with marker-based tracking using Selenium
        
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
                logger.info(f"Starting Mascus scrape with Selenium (marker: {current_marker}, limit: {max_items or 'unlimited'}) - Attempt {attempt + 1}/{max_retries}")
                
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
                chrome_options.page_load_strategy = 'eager'  # Don't wait for full page load (images, css, etc)
                
                # Initialize driver with suppressed logs
                service = Service(ChromeDriverManager().install(), log_output=os.devnull)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.set_page_load_timeout(60)  # Set explicit timeout
                driver.get(self.url)
                
                # Wait for page to load
                time.sleep(4)  # Mascus might need more time to load
                
                # Parse the fully loaded page
                soup = BeautifulSoup(driver.page_source, 'html.parser')
                
                # Parse with marker logic
                machines, first_item_id = self._parse_with_marker(soup, current_marker, max_items)
                
                logger.info(f"Scraped {len(machines)} new machines (first ID: {first_item_id})")
                return machines, first_item_id
                
            except Exception as e:
                logger.error(f"Error scraping Mascus (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            finally:
                if driver:
                    driver.quit()
        
        return [], None
    
    def _parse_with_marker(self, soup: BeautifulSoup, marker: Optional[str], max_items: Optional[int]) -> Tuple[List[Machine], Optional[str]]:
        """
        Parse Mascus results with marker-based logic and China filtering
        
        Args:
            soup: BeautifulSoup object
            marker: Previous marker ID to stop at
            max_items: Maximum items to return
            
        Returns:
            Tuple of (new_machines, first_item_id)
        """
        machines = []
        first_item_id = None
        
        # Find all result items
        items = soup.find_all('div', class_='SearchResult_searchResultItemWrapper__VVVnZ')
        
        if not items:
            logger.warning("No Mascus results found")
            return [], None
        
        logger.info(f"Found {len(items)} total results on page")
        
        for index, item in enumerate(items):
            try:
                # Extract link and unique ID
                link_elem = item.find('a', class_='SearchResult_assetHeaderUrl__EMde6')
                if not link_elem or not link_elem.get('href'):
                    continue
                
                href = link_elem['href']
                # Extract ID from URL like /construction/.../xk0dygvi.html
                unique_id = href.rstrip('.html').split('/')[-1]
                
                # Set first_item_id on first iteration
                if index == 0:
                    first_item_id = unique_id
                
                # If we hit the marker, stop (these are old items)
                if marker and unique_id == marker:
                    logger.info(f"Reached marker {marker} at position {index}, stopping")
                    break
                
                # Extract title
                title_elem = item.find('h3', class_='SearchResult_brandmodel__04K2L')
                title = title_elem.get_text(strip=True) if title_elem else f"Machine {unique_id}"
                
                # Extract price
                price_elem = item.find('div', class_='typography__Heading5-sc-1tyz4zr-10')
                price = price_elem.get_text(strip=True) if price_elem else None
                
                # Extract year, hours, location from location text
                year = None
                hours = None
                location = None
                country_code = None
                
                location_elem = item.find('p', class_='typography__BodyText2-sc-1tyz4zr-2')
                if location_elem:
                    location_text = location_elem.get_text()
                    location_parts = location_text.split('•')
                    if len(location_parts) >= 2:
                        # Try to extract year (4 digits)
                        for part in location_parts:
                            cleaned = part.strip()
                            if cleaned.isdigit() and len(cleaned) == 4:
                                year = cleaned
                            elif 'h' in cleaned and cleaned.replace('h', '').strip().isdigit():
                                hours = cleaned.strip()
                        
                        # Last part before company contains location
                        location_part = location_parts[-2].strip() if len(location_parts) >= 2 else None
                        if location_part:
                            location = location_part
                            # Extract country code (last 2 uppercase letters)
                            words = location_part.split()
                            if words:
                                potential_code = words[-1]
                                if len(potential_code) == 2 and potential_code.isupper():
                                    country_code = potential_code
                
                # Extract image
                img_elem = item.find('img', alt=title)
                image_url = img_elem.get('src') if img_elem else None
                
                # Build full URL
                full_link = f"https://www.mascus.co.uk{href}" if href else None
                
                # Create Machine object
                machine = Machine(
                    unique_id=unique_id,
                    title=title,
                    category="Mascus - Construction Equipment",
                    link=full_link,
                    price=price,
                    year=year,
                    hours=hours,
                    location=location,
                    image_url=image_url,
                    country_code=country_code
                )
                
                machines.append(machine)
                
                # Check max_items limit
                if max_items and len(machines) >= max_items:
                    logger.info(f"Reached max_items limit ({max_items}), stopping")
                    break
                    
            except Exception as e:
                logger.error(f"Error parsing Mascus item: {e}")
                continue
        
        return machines, first_item_id
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """Not used - marker-based scraper"""
        pass
    
    def extract_machine_data(self, element) -> Optional[Machine]:
        """Not used - marker-based scraper"""
        pass
