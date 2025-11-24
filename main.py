#!/usr/bin/env python3
"""
Web Scraping System for Machinery Listings
Main orchestrator that coordinates scraping, database, and notifications
"""
import asyncio
import logging
import sys
from typing import List, Tuple
from pathlib import Path
from logging.handlers import RotatingFileHandler

from config_schema import load_config
from database import DatabaseHandler
from telegram_notifier import TelegramNotifier
from scraper_factory import ScraperFactory
from models import Machine


# Configure logging with rotation (10MB max, 3 backup files)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# File handler with rotation
file_handler = RotatingFileHandler(
    'scraper.log',
    maxBytes=10 * 1024 * 1024,  # 10MB
    backupCount=3,  # Keep 3 backup files (scraper.log.1, scraper.log.2, scraper.log.3)
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)

# Configure root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)

# Disable httpx verbose logs (Telegram API requests)
logging.getLogger('httpx').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Configure separate timing logger
timing_logger = logging.getLogger('timing')
timing_logger.setLevel(logging.INFO)
timing_logger.propagate = False  # Don't propagate to root logger

timing_formatter = logging.Formatter('%(asctime)s - %(message)s')
timing_handler = RotatingFileHandler(
    'timing.log',
    maxBytes=5 * 1024 * 1024,  # 5MB
    backupCount=3,
    encoding='utf-8'
)
timing_handler.setFormatter(timing_formatter)
timing_logger.addHandler(timing_handler)


class ScraperOrchestrator:
    """Main orchestrator for the scraping system"""
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the orchestrator"""
        logger.info("=" * 80)
        logger.info("Initializing Web Scraping System")
        logger.info("=" * 80)
        
        # Load configuration
        self.config = load_config(config_path)
        logger.info(f"Configuration loaded from {config_path}")
        
        # Initialize database
        self.db = DatabaseHandler(self.config.database_path)
        logger.info(f"Database initialized: {self.config.database_path}")
        
        # Initialize Telegram notifier with backup bots support
        backup_tokens = self.config.raw_config.get('telegram', {}).get('backup_bot_tokens', [])
        self.notifier = TelegramNotifier(
            self.config.telegram_token,
            self.config.telegram_chat_ids,
            backup_tokens=backup_tokens
        )
        logger.info("Telegram notifier initialized")
        
        # Scraper configuration
        self.scraper_config = {
            'user_agent': self.config.user_agent,
            'request_timeout': self.config.request_timeout,
            'max_retries': self.config.max_retries,
            'delay_between_requests': self.config.scraping_delay
        }
    
    async def run(self):
        """Main execution method"""
        try:
            # Test Telegram connection
            logger.info("Testing Telegram connection...")
            if not await self.notifier.test_connection():
                logger.error("Failed to connect to Telegram. Check your token and chat ID.")
                return
            
            # Get enabled websites
            websites = self.config.get_enabled_websites()
            logger.info(f"Found {len(websites)} enabled website(s) to scrape")
            
            if not websites:
                logger.warning("No enabled websites found in configuration")
                return
            
            logger.info(f"Starting scraping loop (Interval: {self.config.loop_interval}s)")
            logger.info("Press Ctrl+C to stop")
            
            cycle_count = 1
            
            while True:
                cycle_start_time = asyncio.get_event_loop().time()
                logger.info(f"Cycle {cycle_count} Started")
                timing_logger.info(f"="*60)
                timing_logger.info(f"CYCLE {cycle_count} STARTED")
                timing_logger.info(f"="*60)
                
                # Process each website
                for i, website_config in enumerate(websites, 1):
                    url_start_time = asyncio.get_event_loop().time()
                    logger.info(f"Processing {i}/{len(websites)}: {website_config.search_title}")
                    timing_logger.info(f"URL {i}/{len(websites)}: {website_config.search_title} - Started")
                    
                    try:
                        # Create scraper (pass categories for MachineFinder)
                        scraper = ScraperFactory.create_scraper(
                            website_config.website_type,
                            website_config.url,
                            self.scraper_config,
                            categories=website_config.categories
                        )
                        
                        # Handle Craigslist with marker-based approach
                        if website_config.website_type in ['craigslist', 'mascus']:
                            # Marker-based approach (Craigslist/Mascus style)
                            current_marker = self.db.get_marker(website_config.search_title)
                            max_items = getattr(website_config, 'max_items', None)
                            
                            new_machines, first_id = scraper.scrape(
                                current_marker=current_marker,
                                max_items=max_items
                            )
                            logger.info(f"Found {len(new_machines)} new items")
                            
                            # Alert if 0 items scraped (might indicate problem)
                            if len(new_machines) == 0 and not current_marker:
                                await self.notifier.send_zero_items_alert(
                                    website_config.search_title,
                                    website_config.url,
                                    website_config.website_type
                                )
                            
                            # Update marker if we have a first item
                            if first_id:
                                self.db.save_marker(website_config.search_title, first_id)
                                logger.debug(f"Updated marker to: {first_id}")
                            
                            # For Mascus: filter China items from notifications ONLY
                            machines_for_notification = new_machines
                            if website_config.website_type == 'mascus':
                                machines_for_notification = [m for m in new_machines if m.country_code != 'CN']
                                china_count = len(new_machines) - len(machines_for_notification)
                                if china_count > 0:
                                    logger.info(f"Filtered {china_count} China items from notifications")
                            
                            # Send notifications for filtered machines (skip first cycle)
                            if machines_for_notification and cycle_count > 1:
                                await self.notifier.send_new_items_notification(
                                    website_config.search_title,
                                    [m.to_dict() for m in machines_for_notification],
                                    website_config.website_type
                                )
                            
                            # Log stats
                            logger.info(f"Marker: {first_id or 'none'} | {len(new_machines)} new items")
                        
                        else:
                            # Standard approach for Monroe/AIS (save all, compare)
                            machines, pages = scraper.scrape()
                            logger.info(f"Found {len(machines)} items in {pages} pages")
                            
                            # Alert if 0 items scraped (might indicate problem)
                            if len(machines) == 0:
                                await self.notifier.send_zero_items_alert(
                                    website_config.search_title,
                                    website_config.url,
                                    website_config.website_type
                                )
                            
                            # Check for new machines and cleanup old ones
                            new_machines, deleted_count = await self._process_machines(
                                website_config.website_type,
                                website_config.search_title,
                                machines
                            )
                            
                            # DB Stats
                            total_in_db = len(machines)
                            
                            logger.info(f"Database: {total_in_db} active | {len(new_machines)} new | {deleted_count} removed")
                            
                            # Send notifications for new machines
                            if new_machines:
                                if cycle_count == 1:
                                    pass # Suppress on first cycle
                                else:
                                    await self.notifier.send_new_items_notification(
                                        website_config.search_title,
                                        [m.to_dict() for m in new_machines],
                                        website_config.website_type
                                    )
                        
                        url_duration = asyncio.get_event_loop().time() - url_start_time
                        logger.info(f"URL processed in {url_duration:.2f}s")
                        timing_logger.info(f"URL {i}/{len(websites)}: {website_config.search_title} - Completed in {url_duration:.2f}s")
                        
                        # Delay between URLs if configured (but not after the last URL)
                        if self.config.url_delay > 0 and i < len(websites):
                            timing_logger.info(f"⏳ Waiting {self.config.url_delay}s before next URL...")
                            await asyncio.sleep(self.config.url_delay)
                    
                    except Exception as e:
                        logger.error(f"Error processing website {website_config.url}: {e}", exc_info=True)
                        url_duration = asyncio.get_event_loop().time() - url_start_time
                        timing_logger.info(f"URL {i}/{len(websites)}: {website_config.search_title} - Failed after {url_duration:.2f}s")
                        
                        # Delay even after errors (but not after the last URL)
                        if self.config.url_delay > 0 and i < len(websites):
                            timing_logger.info(f"⏳ Waiting {self.config.url_delay}s before next URL...")
                            await asyncio.sleep(self.config.url_delay)
                        continue
                
                cycle_duration = asyncio.get_event_loop().time() - cycle_start_time
                logger.info(f"Cycle duration: {cycle_duration:.2f}s")
                logger.info(f"Cycle {cycle_count} Ended")
                timing_logger.info(f"CYCLE {cycle_count} ENDED - Total Duration: {cycle_duration:.2f}s")
                timing_logger.info(f"")
                
                # Wait for next run if interval is set
                if self.config.loop_interval > 0:
                    logger.info(f"Waiting {self.config.loop_interval} seconds before next cycle...")
                    await asyncio.sleep(self.config.loop_interval)
                
                cycle_count += 1
        
        except asyncio.CancelledError:
            logger.info("Scraping loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in orchestrator: {e}", exc_info=True)
            await self.notifier.send_alert(f"Scraping system error: {str(e)}")
    
    async def _process_machines(
        self,
        website_type: str,
        search_title: str,
        machines: List[Machine]
    ) -> Tuple[List[Machine], int]:
        """
        Process machines: check which are new, save them, and cleanup old ones
        Returns: (new_machines, deleted_count)
        """
        new_machines = []
        current_unique_ids = []
        
        for machine in machines:
            current_unique_ids.append(machine.unique_id)
            
            # Check if machine is new for this search title
            if self.db.is_new_machine(search_title, machine.unique_id):
                # Save to database
                if self.db.save_machine(search_title, website_type, machine.unique_id):
                    new_machines.append(machine)
                    # logger.info(f"✓ New machine: {machine.title} ({machine.unique_id})") # Suppress individual logs
            else:
                pass
                # logger.debug(f"  Existing machine: {machine.title} ({machine.unique_id})")
        
        # Cleanup old machines that are no longer on the site for this search title
        cleaned_count = self.db.cleanup_old_machines(search_title, current_unique_ids)
            
        return new_machines, cleaned_count


async def main():
    """Main entry point"""
    try:
        orchestrator = ScraperOrchestrator()
        await orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
