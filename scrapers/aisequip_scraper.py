import re
import logging
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs

from scrapers.base_scraper import BaseScraper
from models import Machine

logger = logging.getLogger(__name__)


class AISEquipScraper(BaseScraper):
    """Scraper for www.aisequip.com pre-owned machines"""
    
    def scrape(self) -> Tuple[List[Machine], int]:
        """
        Scrape all machines from all pages
        Overrides BaseScraper.scrape to handle dynamic pagination
        since the site doesn't expose pagination links in HTML
        """
        all_machines = []
        page_num = 1
        max_pages = 50  # Safety limit
        
        while page_num <= max_pages:
            # Construct URL
            if page_num == 1:
                url = self.url
            else:
                separator = '&' if '?' in self.url else '?'
                url = f"{self.url}{separator}_paged={page_num}"
            
            logger.debug(f"Scraping page {page_num}: {url}")
            
            # Fetch page
            soup = self._fetch_page(url)
            if not soup:
                logger.debug(f"Failed to fetch page {page_num}")
                break
                
            # Parse page
            machines = self.parse_page(soup)
            
            if not machines:
                logger.debug(f"No machines found on page {page_num}. Stopping pagination.")
                break
                
            logger.debug(f"Found {len(machines)} machines on page {page_num}")
            all_machines.extend(machines)
            
            # If we found fewer machines than expected (e.g. < 20), this is likely the last page
            # But we'll just let the next loop iteration check for 0 machines to be safe
            
            page_num += 1
            
            # Respect rate limiting
            import time
            time.sleep(self.config.get('delay_between_requests', 2.0))
            
        return all_machines, page_num - 1

    def get_pagination_urls(self) -> List[str]:
        """
        Deprecated: Logic moved to scrape() method
        """
        return []
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """
        Parse AIS Equipment page and extract all machines
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of Machine objects
        """
        machines = []
        
        try:
            # Find the machines container
            machines_container = soup.find('div', class_='machines')
            
            if not machines_container:
                logger.warning("Could not find machines container")
                return machines
            
            # Find all machine elements
            # Each machine is wrapped in an <a> tag containing a div.machine
            machine_links = machines_container.find_all('a', href=True)
            
            for link in machine_links:
                machine_div = link.find('div', class_='machine')
                if not machine_div:
                    continue
                
                try:
                    machine = self.extract_machine_data(link)
                    if machine:
                        machines.append(machine)
                except Exception as e:
                    logger.error(f"Error extracting machine data: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error parsing page: {e}")
        
        return machines
    
    def extract_machine_data(self, element) -> Optional[Machine]:
        """
        Extract machine data from a single machine element
        
        Args:
            element: BeautifulSoup <a> element containing machine data
            
        Returns:
            Machine object or None if extraction failed
        """
        try:
            # Get the machine div
            machine_div = element.find('div', class_='machine')
            if not machine_div:
                return None
            
            # Extract link and unique ID
            link = element.get('href', '')
            if not link:
                return None
            
            # Make absolute URL
            link = urljoin('https://www.aisequip.com', link)
            
            # Extract unique ID from URL
            # Example: /pre-owned-machines/category/whl-loader/komatsu-wa500-8-w43961/
            # Unique ID is the last part before the trailing slash
            unique_id = self._extract_unique_id(link)
            if not unique_id:
                logger.warning(f"Could not extract unique ID from: {link}")
                return None
            
            # Extract title
            title_elem = machine_div.find('h3')
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            
            # Extract category
            category_elem = machine_div.find('div', class_='machine-category')
            category = category_elem.get_text(strip=True) if category_elem else ""
            
            # Extract price
            price_elem = machine_div.find('div', class_='machine-price')
            price = price_elem.get_text(strip=True) if price_elem else None
            
            # Extract year
            year_elem = machine_div.find('div', class_='machine-year')
            year = None
            if year_elem:
                year_text = year_elem.get_text(strip=True)
                # Remove the "Year" label
                year = re.sub(r'Year\s*', '', year_text, flags=re.IGNORECASE).strip()
            
            # Extract hours
            hours_elem = machine_div.find('div', class_='machine-hours')
            hours = None
            if hours_elem:
                hours_text = hours_elem.get_text(strip=True)
                # Remove the "Hours" label
                hours = re.sub(r'Hours\s*', '', hours_text, flags=re.IGNORECASE).strip()
            
            # Extract location
            location_elem = machine_div.find('div', class_='machine-location')
            location = None
            if location_elem:
                location_text = location_elem.get_text(strip=True)
                # Remove the "Location" label
                location = re.sub(r'Location\s*', '', location_text, flags=re.IGNORECASE).strip()
            
            # Extract image URL
            image_url = self._extract_image_url(machine_div)
            
            # Create Machine object
            machine = Machine(
                unique_id=unique_id,
                title=title,
                category=category,
                link=link,
                price=price,
                year=year,
                hours=hours,
                location=location,
                image_url=image_url
            )
            
            return machine
        
        except Exception as e:
            logger.error(f"Error extracting machine data: {e}")
            return None
    
    def _extract_unique_id(self, url: str) -> Optional[str]:
        """
        Extract unique ID from machine URL
        Example: https://www.aisequip.com/pre-owned-machines/category/whl-loader/komatsu-wa500-8-w43961/
        Returns: komatsu-wa500-8-w43961
        """
        try:
            # Parse URL path
            path = urlparse(url).path
            # Remove trailing slash and split
            parts = path.rstrip('/').split('/')
            # Last part is the unique ID
            if parts:
                return parts[-1]
        except Exception as e:
            logger.error(f"Error extracting unique ID from {url}: {e}")
        
        return None
    
    def _extract_image_url(self, machine_div) -> Optional[str]:
        """
        Extract image URL from machine element
        Handles both <picture> with webp and regular <img> tags
        """
        try:
            # Try to find picture element first
            picture = machine_div.find('picture')
            if picture:
                # Get the fallback img tag
                img = picture.find('img')
                if img and img.get('src'):
                    img_url = img['src']
                    # Make absolute URL
                    return urljoin('https://www.aisequip.com', img_url)
            
            # Try regular img tag
            img = machine_div.find('img')
            if img and img.get('src'):
                img_url = img['src']
                # Skip placeholder images
                if 'placeholder' in img_url.lower():
                    return None
                # Make absolute URL
                return urljoin('https://www.aisequip.com', img_url)
        
        except Exception as e:
            logger.error(f"Error extracting image URL: {e}")
        
        return None
