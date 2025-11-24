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

from config_schema import load_config
from database import DatabaseHandler
from telegram_notifier import TelegramNotifier
from scraper_factory import ScraperFactory
from models import Machine


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


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
        
        # Initialize Telegram notifier
        self.notifier = TelegramNotifier(
            self.config.telegram_token,
            self.config.telegram_chat_id
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
                
                # Process each website
                for i, website_config in enumerate(websites, 1):
                    url_start_time = asyncio.get_event_loop().time()
                    logger.info(f"Processing {i}/{len(websites)}: {website_config.search_title}")
                    
                    try:
                        # Create scraper (pass categories for MachineFinder)
                        scraper = ScraperFactory.create_scraper(
                            website_config.website_type,
                            website_config.url,
                            self.scraper_config,
                            categories=website_config.categories
                        )
                        
                        # Handle Craigslist with marker-based approach
                        if website_config.website_type == 'craigslist':
                            # Get current marker
                            current_marker = self.db.get_marker(website_config.search_title)
                            logger.debug(f"Current marker: {current_marker}")
                            
                            # Scrape with marker and optional max_items limit
                            new_machines, first_id = scraper.scrape(
                                current_marker, 
                                max_items=website_config.max_items
                            )
                            logger.info(f"Found {len(new_machines)} new items")
                            
                            # Alert if 0 items scraped (might indicate problem)
                            if len(new_machines) == 0 and not current_marker:
                                await self.notifier.send_zero_items_alert(
                                    website_config.search_title,
                                    website_config.url
                                )
                            
                            # Send notifications for new machines (skip first cycle)
                            if new_machines and cycle_count > 1:
                                await self.notifier.send_new_items_notification(
                                    website_config.search_title,
                                    [m.to_dict() for m in new_machines]
                                )
                            
                            # Update marker if we have a first item
                            if first_id:
                                self.db.save_marker(website_config.search_title, first_id)
                                logger.debug(f"Updated marker to: {first_id}")
                            
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
                                    website_config.url
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
                                        [m.to_dict() for m in new_machines]
                                    )
                        
                        url_duration = asyncio.get_event_loop().time() - url_start_time
                        logger.info(f"URL processed in {url_duration:.2f}s")
                    
                    except Exception as e:
                        logger.error(f"Error processing website {website_config.url}: {e}", exc_info=True)
                        continue
                
                cycle_duration = asyncio.get_event_loop().time() - cycle_start_time
                logger.info(f"Cycle duration: {cycle_duration:.2f}s")
                logger.info(f"Cycle {cycle_count} Ended")
                
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
