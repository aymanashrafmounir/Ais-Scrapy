import re
import logging
import time
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from scrapers.base_scraper import BaseScraper
from models import Machine

logger = logging.getLogger(__name__)


class MonroeTractorScraper(BaseScraper):
    """Scraper for www.monroetractor.com construction equipment"""
    
    def scrape(self) -> Tuple[List[Machine], int]:
        """
        Override to use Selenium for lazy-loaded content
        Monroe Tractor loads machines via infinite scroll
        """
        all_machines = []
        
        # Setup Selenium with optimizations for low-resource servers (2 CPU, 1GB RAM)
        chrome_options = Options()
        chrome_options.add_argument('--headless=new')  # New headless mode (more stable)
        chrome_options.add_argument('--no-sandbox')  # Required for Docker/Linux
        chrome_options.add_argument('--disable-dev-shm-usage')  # Overcome limited resource problems
        chrome_options.add_argument('--disable-gpu')  # Disable GPU hardware acceleration
        chrome_options.add_argument('--disable-software-rasterizer')  # Reduce CPU usage
        chrome_options.add_argument('--disable-extensions')  # No extensions
        chrome_options.add_argument('--disable-images')  # Don't load images (faster)
        chrome_options.add_argument('--blink-settings=imagesEnabled=false')  # Block images
        chrome_options.add_argument('--window-size=1920,1080')  # Set window size for consistency
        # Suppress Chrome's internal error logs (GPU, GCM, DevTools warnings)
        chrome_options.add_argument('--log-level=3')  # Only show fatal errors
        chrome_options.add_argument('--silent')
        chrome_options.add_argument('--disable-logging')
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.add_argument('--disable-background-networking')
        chrome_options.add_argument('--disable-sync')
        chrome_options.add_argument('--disable-translate')
        chrome_options.add_argument(f'user-agent={self.config.get("user_agent", "Mozilla/5.0")}')
        
        # Initialize driver with suppressed logs
        service = Service(log_output=os.devnull)
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.get(self.url)
            
            # Wait for initial content to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, 'equipment_by_type'))
            )
            
            # Get expected count
            container = driver.find_element(By.CLASS_NAME, 'equipment_by_type')
            expected_count = int(container.get_attribute('data-equip-count') or 0)
            logger.info(f"Expected {expected_count} machines based on data-equip-count")
            
            # Scroll to load all items
            last_height = driver.execute_script("return document.body.scrollHeight")
            items_loaded = len(driver.find_elements(By.CLASS_NAME, 'equip-item-wrap'))
            
            logger.info(f"Starting with {items_loaded} machines loaded")
            
            max_attempts = 20  # Maximum scroll attempts
            attempts = 0
            no_change_count = 0
            
            while items_loaded < expected_count and attempts < max_attempts:
                # Scroll down in multiple steps for better loading
                for _ in range(3):
                    driver.execute_script("window.scrollBy(0, 500);")
                    time.sleep(0.5)
                
                # Scroll to absolute bottom
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
                # Wait longer for lazy loading
                time.sleep(3)
                
                # Calculate new scroll height and items
                new_height = driver.execute_script("return document.body.scrollHeight")
                new_items_loaded = len(driver.find_elements(By.CLASS_NAME, 'equip-item-wrap'))
                
                logger.info(f"Loaded {new_items_loaded}/{expected_count} machines (attempt {attempts + 1})")
                
                # Check if stuck
                if new_items_loaded == items_loaded:
                    no_change_count += 1
                    if no_change_count >= 3:
                        logger.warning(f"No new items after 3 attempts, stopping at {new_items_loaded} machines")
                        break
                else:
                    no_change_count = 0
                    
                last_height = new_height
                items_loaded = new_items_loaded
                attempts += 1
            
            logger.info(f"Finished scrolling after {attempts} attempts, loaded {items_loaded} machines")
            
            # Parse the fully loaded page
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            all_machines = self.parse_page(soup)
            
            logger.info(f"Successfully scraped {len(all_machines)} machines")
            return all_machines, 1
            
        except Exception as e:
            logger.error(f"Error in scrape: {e}", exc_info=True)
            return [], 0
        finally:
            if driver:
                driver.quit()
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """
        Parse Monroe Tractor page and extract all machines
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of Machine objects
        """
        machines = []
        
        # Find the container with equipment count
        container = soup.find('div', class_='equipment_by_type')
        if not container:
            logger.warning("Could not find equipment container")
            return machines
        
        # Get expected count for validation
        expected_count = container.get('data-equip-count')
        if expected_count:
            logger.info(f"Expected {expected_count} machines based on data-equip-count")
        
        # Find all machine items
        machine_items = soup.find_all('div', class_='col-md-4 equip-item-wrap')
        logger.info(f"Found {len(machine_items)} machine containers")
        
        for item in machine_items:
            try:
                machine = self.extract_machine_data(item)
                if machine:
                    machines.append(machine)
            except Exception as e:
                logger.error(f"Error extracting machine data: {e}")
                continue
        
        # Validate count matches expected
        if expected_count and len(machines) != int(expected_count):
            logger.warning(
                f"Scraped {len(machines)} machines but expected {expected_count}"
            )
        
        return machines
    
    def extract_machine_data(self, element) -> Optional[Machine]:
        """
        Extract machine data from a single machine element
        
        Args:
            element: BeautifulSoup element containing machine data
            
        Returns:
            Machine object or None if extraction failed
        """
        try:
            # Find the equip_item div
            equip_item = element.find('div', class_='equip_item')
            if not equip_item:
                logger.warning("Could not find equip_item div")
                return None
            
            # Extract URL from the image link
            image_link = equip_item.find('a', class_='image')
            if not image_link or not image_link.get('href'):
                logger.warning("Could not find machine URL")
                return None
            
            relative_url = image_link['href']
            url = urljoin(self.url, relative_url)
            
            # Extract unique ID from URL (stock number)
            unique_id = self._extract_unique_id(url)
            if not unique_id:
                logger.warning(f"Could not extract unique ID from URL: {url}")
                return None
            
            # Extract image URL
            image_url = self._extract_image_url(equip_item)
            
            # Find details section
            details = equip_item.find('div', class_='details')
            if not details:
                logger.warning("Could not find details section")
                return None
            
            # Extract brand from top section
            top_section = details.find('div', class_='top')
            brand = "Unknown"
            if top_section:
                brand_tag = top_section.find('strong')
                if brand_tag:
                    brand = brand_tag.get_text(strip=True)
            
            # Extract data from bottom section
            bottom_section = details.find('div', class_='bottom')
            if not bottom_section:
                logger.warning("Could not find bottom section")
                return None
            
            bottom_text = bottom_section.get_text()
            
            # Extract model
            model_match = re.search(r'Model:\s*([^\|]+?)(?:\||Stock)', bottom_text)
            model = model_match.group(1).strip() if model_match else "Unknown"
            
            # Extract stock number
            stock_match = re.search(r'Stock #:\s*([^\n]+)', bottom_text)
            stock_num = stock_match.group(1).strip() if stock_match else unique_id
            
            # Extract price
            price_match = re.search(r'Price:\s*([^\n]+)', bottom_text)
            price = price_match.group(1).strip() if price_match else "Upon Request"
            
            # Extract location
            location_match = re.search(r'Location:\s*([^\n]+)', bottom_text)
            location = location_match.group(1).strip() if location_match else "Unknown"
            
            # Extract year
            year_match = re.search(r'Year:\s*(\d{4})', bottom_text)
            year = year_match.group(1) if year_match else ""
            
            # Build title: Brand Model Year Stock# (clean format per user request)
            title = f"{brand} {model}"
            if year:
                title = f"{title} {year}"
            if stock_num:
                title = f"{title} {stock_num}"
            
            # Build category from URL path if available
            category = "Construction Equipment"
            
            # Create Machine object (using correct field names)
            machine = Machine(
                unique_id=unique_id,
                title=title,
                category=category,
                link=url,
                price=price,
                year=year,
                hours=None,  # Monroe Tractor doesn't show hours
                location=location,
                image_url=image_url
            )
            
            logger.debug(f"Extracted machine: {title} - {stock_num}")
            return machine
            
        except Exception as e:
            logger.error(f"Error extracting machine data: {e}", exc_info=True)
            return None
    
    def _extract_unique_id(self, url: str) -> Optional[str]:
        """
        Extract unique ID from machine URL
        Example: https://www.monroetractor.com/for-sale/construction/.../H071568/
        Returns: H071568
        """
        # Extract stock number from URL (format: /H######/)
        match = re.search(r'/(H\d+)/?$', url)
        if match:
            return match.group(1)
        
        # Fallback: try to extract any alphanumeric ID from the last segment
        parts = url.rstrip('/').split('/')
        if parts:
            return parts[-1]
        
        return None
    
    def _extract_image_url(self, equip_item) -> Optional[str]:
        """
        Extract image URL from machine element
        
        Args:
            equip_item: BeautifulSoup element of equip_item div
            
        Returns:
            Image URL or None
        """
        # Find the image tag
        img_tag = equip_item.find('a', class_='image')
        if img_tag:
            img = img_tag.find('img')
            if img and img.get('src'):
                src = img['src']
                # Skip loading placeholder images
                if 'img-loading' not in src:
                    # Make absolute URL
                    return urljoin(self.url, src)
        
        return None
