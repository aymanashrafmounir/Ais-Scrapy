import logging
import asyncio
import aiohttp
import time
from typing import List, Optional, Tuple
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import os
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from models import Machine
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class MachineFinderScraper(BaseScraper):
    """API-based scraper for MachineFinder.com with parallel requests"""
    
    # Class-level cache for tokens
    _cached_csrf_token = None
    _cached_cookies = None
    _token_timestamp = 0
    _TOKEN_TTL = 1800  # 30 minutes
    
    def __init__(self, url: str, config: dict, categories: list = None):
        """
        Initialize MachineFinder scraper
        
        Args:
            url: Base URL (not used, kept for compatibility)
            config: Scraper configuration
            categories: List of category dicts with title, search_kind, bcat
        """
        super().__init__(url, config)
        self.categories = categories or []
        # Initialize instance tokens from cache
        self.csrf_token = MachineFinderScraper._cached_csrf_token
        self.cookies = MachineFinderScraper._cached_cookies or {}
    
    def scrape(self) -> Tuple[List[Machine], int]:
        """
        Scrape MachineFinder using API calls
        
        Returns:
            Tuple of (machines_list, pages_count)
        """
        try:
            # Run async scraping in a separate thread to avoid event loop conflict
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._run_async_scrape)
                return future.result()
            
        except Exception as e:
            logger.error(f"Error in MachineFinder scraper: {e}")
            return [], 0

    def _run_async_scrape(self) -> Tuple[List[Machine], int]:
        """Helper to run async logic in a new event loop"""
        return asyncio.run(self._scrape_async_logic())

    async def _scrape_async_logic(self) -> Tuple[List[Machine], int]:
        """The actual async scraping logic"""
        # Step 1: Extract CSRF token and cookies (if not cached or expired)
        if not self._ensure_tokens():
            logger.error("Failed to extract CSRF token and cookies")
            return [], 0
        
        # Step 2: Fetch all machines via API
        all_machines = []
        for category in self.categories:
            logger.info(f"Fetching {category['title']}...")
            machines = await self._fetch_category_async(category)
            all_machines.extend(machines)
        
        logger.info(f"Successfully fetched {len(all_machines)} total machines")
        return all_machines, 1
    
    def _ensure_tokens(self) -> bool:
        """Ensure valid tokens exist, refreshing if necessary"""
        current_time = time.time()
        
        # Check if we have valid cached tokens
        if (MachineFinderScraper._cached_csrf_token and 
            MachineFinderScraper._cached_cookies and 
            (current_time - MachineFinderScraper._token_timestamp < MachineFinderScraper._TOKEN_TTL)):
            
            self.csrf_token = MachineFinderScraper._cached_csrf_token
            self.cookies = MachineFinderScraper._cached_cookies
            return True
            
        # Need to refresh tokens
        if self._extract_tokens():
            # Update cache
            MachineFinderScraper._cached_csrf_token = self.csrf_token
            MachineFinderScraper._cached_cookies = self.cookies
            MachineFinderScraper._token_timestamp = current_time
            return True
            
        return False

    def _extract_tokens(self) -> bool:
        """
        Extract CSRF token and cookies from MachineFinder website
        
        Returns:
            True if successful, False otherwise
        """
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            driver = None
            try:
                logger.info(f"Extracting CSRF token and cookies from MachineFinder... (Attempt {attempt + 1}/{max_retries})")
                
                # Setup Chrome
                chrome_options = Options()
                chrome_options.add_argument('--headless=new')
                chrome_options.add_argument('--no-sandbox')
                chrome_options.add_argument('--disable-dev-shm-usage')
                chrome_options.add_argument('--disable-gpu')
                chrome_options.add_argument('--disable-extensions')
                chrome_options.add_argument('--disable-infobars')
                # Suppress Chrome's internal error logs (GPU, GCM, DevTools warnings)
                chrome_options.add_argument('--log-level=3')  # Only show fatal errors
                chrome_options.add_argument('--silent')
                chrome_options.add_argument('--disable-logging')
                chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
                chrome_options.add_argument('--disable-background-networking')
                chrome_options.add_argument('--disable-sync')
                chrome_options.add_argument('--disable-translate')
                chrome_options.page_load_strategy = 'eager'
                
                # Initialize driver with suppressed logs
                service = Service(log_output=os.devnull)
                driver = webdriver.Chrome(service=service, options=chrome_options)
                driver.set_page_load_timeout(60)
                driver.get('https://www.machinefinder.com/')
                
                # Wait for page to load
                time.sleep(3)
                
                # Extract cookies
                selenium_cookies = driver.get_cookies()
                self.cookies = {cookie['name']: cookie['value'] for cookie in selenium_cookies}
                
                # Extract CSRF token from page source or meta tag
                page_source = driver.page_source
                
                # Try to find CSRF token in meta tag
                soup = BeautifulSoup(page_source, 'html.parser')
                csrf_meta = soup.find('meta', {'name': 'csrf-token'})
                if csrf_meta:
                    self.csrf_token = csrf_meta.get('content')
                else:
                    # Try to find in script or other places
                    import re
                    csrf_match = re.search(r'csrf[_-]?token["\']?\s*[:=]\s*["\']([^"\']+)', page_source, re.IGNORECASE)
                    if csrf_match:
                        self.csrf_token = csrf_match.group(1)
                
                # If still no token, try getting from cookies
                if not self.csrf_token:
                    self.csrf_token = self.cookies.get('XSRF-TOKEN', '') or self.cookies.get('csrf_token', '')
                
                if self.csrf_token:
                    logger.info(f"✓ Successfully extracted CSRF token: {self.csrf_token[:20]}...")
                    logger.debug(f"Extracted {len(self.cookies)} cookies")
                    return True
                else:
                    logger.warning(f"Could not find CSRF token (Attempt {attempt + 1}/{max_retries})")
                    # Don't return False immediately, let it retry or fail at the end of loop if this was an error
                    # But here it's just not found, maybe we should retry? 
                    # The original code returned False. Let's treat "not found" as a failure to retry if we think it's transient.
                    # For now, let's assume if it loads but no token, retrying might help if page load was partial.
                    raise Exception("CSRF token not found in page")
                    
            except Exception as e:
                logger.error(f"Error extracting tokens (Attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    time.sleep(retry_delay)
            finally:
                if driver:
                    driver.quit()
        
        return False
    
    async def _fetch_category_async(self, category: dict, max_concurrent: int = 5) -> List[Machine]:
        """
        Fetch machines for a category using parallel async API calls
        
        Args:
            category: Dict with title, search_kind, bcat
            max_concurrent: Number of parallel requests
            
        Returns:
            List of Machine objects
        """
        search_title = category['title']
        search_kind = category['search_kind']
        bcat = category['bcat']
        
        base_url = "https://www.machinefinder.com/ww/en-US/mfinder/results?mw=t&lang_code=en-US"
        
        headers = {
            "authority": "www.machinefinder.com",
            "accept": "application/json, text/plain, */*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json;charset=UTF-8",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "x-csrf-token": self.csrf_token,
            "x-requested-with": "XMLHttpRequest"
        }
        
        # Convert cookies to string
        cookie_str = "; ".join([f"{k}={v}" for k, v in self.cookies.items()])
        headers["cookie"] = cookie_str
        
        # Initial payload
        payload = {
            "branding": "co",
            "context": {
                "kind": "mf",
                "region": "na",
                "property": "mf_na",
                "search_kind": search_kind
            },
            "criteria": {
                "bcat": [bcat]
            },
            "fw": "pr:hrs:shr:chr:fhr",
            "intro_header": f"Used {search_title} For Sale",
            "locked_criteria": {
                "bcat": [bcat]
            },
            "show_more_start": 0
        }
        
        all_machines = []
        
        try:
            async with aiohttp.ClientSession() as session:
                # Get total count
                async with session.post(base_url, headers=headers, json=payload, timeout=30) as response:
                    if response.status != 200:
                        logger.error(f"API Error for {search_title}: Status {response.status}")
                        return []
                    
                    data = await response.json()
                    if 'results' not in data:
                        logger.error(f"API Error for {search_title}: 'results' key missing")
                        return []
                    
                    results = data['results']
                    total_matches = results.get('matches', 0)
                    logger.info(f"  Found {total_matches} total matches for {search_title}")
                    
                    # Process first page
                    if 'machines' in results:
                        machines = self._process_machines(results['machines'], search_title)
                        all_machines.extend(machines)
                
                # Calculate offsets for remaining pages (25 items per page)
                offsets = list(range(25, total_matches, 25))
                
                if not offsets:
                    return all_machines
                
                # Fetch remaining pages in parallel batches
                for i in range(0, len(offsets), max_concurrent):
                    batch_offsets = offsets[i:i + max_concurrent]
                    tasks = []
                    
                    for offset in batch_offsets:
                        payload_copy = payload.copy()
                        payload_copy['show_more_start'] = offset
                        tasks.append(self._fetch_single_page(session, base_url, headers, payload_copy, search_title))
                    
                    # Execute parallel requests
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Process results
                    for result in batch_results:
                        if isinstance(result, Exception):
                            logger.error(f"Error in batch fetch: {result}")
                            continue
                        if result:
                            all_machines.extend(result)
                    
                    # Small delay between batches
                    if i + max_concurrent < len(offsets):
                        await asyncio.sleep(0.1)
        
        except Exception as e:
            logger.error(f"Error fetching {search_title}: {e}")
        
        return all_machines

    async def _fetch_single_page(self, session, url, headers, payload, search_title):
        """Fetch a single page of results"""
        try:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'results' in data and 'machines' in data['results']:
                        return self._process_machines(data['results']['machines'], search_title)
        except Exception as e:
            logger.warning(f"Failed to fetch page offset {payload.get('show_more_start')}: {e}")
        return []
    
    def _process_machines(self, machines_list: list, search_title: str) -> List[Machine]:
        """
        Convert API machine objects to Machine dataclass
        
        Args:
            machines_list: List of machine dicts from API
            search_title: Category title
            
        Returns:
            List of Machine objects
        """
        processed = []
        for m in machines_list:
            try:
                machine_id = str(m.get('id'))
                
                # Get URL
                relative_url = m.get('url', '')
                if relative_url:
                    link = f"https://www.machinefinder.com{relative_url}"
                else:
                    link = f"https://www.machinefinder.com/ww/en-US/machines/{machine_id}"
                
                # Extract fields
                title = m.get('label', f"Machine {machine_id}")
                price = m.get('retail', '')
                hours = m.get('hrs', '')
                location = m.get('situ', '').strip()
                image_url = m.get('gallery', '') or m.get('thumb', '')
                
                machine = Machine(
                    unique_id=machine_id,
                    title=title,
                    category=search_title,
                    link=link,
                    price=price if price else None,
                    hours=hours if hours else None,
                    location=location if location else None,
                    image_url=image_url if image_url else None
                )
                
                processed.append(machine)
                
            except Exception as e:
                logger.error(f"Error processing machine: {e}")
                continue
        
        return processed
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """Not used - API-based scraper"""
        pass
    
    def extract_machine_data(self, element) -> Optional[Machine]:
        """Not used - API-based scraper"""
        pass
