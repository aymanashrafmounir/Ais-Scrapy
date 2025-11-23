# Web Scraping System for Machinery Listings

A professional, extensible web scraping system that monitors machinery listings from multiple websites, tracks new items in a database, and sends Telegram notifications with images when new machines are discovered.

## Features

- ✅ **Configuration-Based**: All settings in `config.json` for easy management
- ✅ **Extensible Design**: Add new websites by creating scraper classes
- ✅ **Database Tracking**: SQLite database prevents duplicate notifications
- ✅ **Telegram Notifications**: Sends photos with detailed machine information
- ✅ **Pagination Support**: Automatically scrapes all pages
- ✅ **Robust Error Handling**: Continues even if one website fails
- ✅ **Logging**: Comprehensive logs for debugging and monitoring

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Telegram Bot

1. Create a Telegram bot via [@BotFather](https://t.me/botfather)
2. Get your bot token
3. Get your chat ID (use [@userinfobot](https://t.me/userinfobot))

### 3. Configuration

The system uses `config.json` for all settings.

1. Edit `config.json` with your Telegram credentials:
   ```json
   {
     "telegram": {
       "bot_token": "YOUR_BOT_TOKEN_HERE",
       "chat_id": "YOUR_CHAT_ID_HERE"
     },
     ...
   }
   ```

## Usage

### Run the Scraper

```bash
python main.py
```

The system will:
1. Load configuration from `config.json`
2. Initialize the database
3. Test Telegram connection
4. Scrape all configured websites
5. Save new machines to the database
6. Send Telegram notifications for new items

### First Run

On the first run, all machines will be considered "new" and you'll receive notifications for all of them. This is normal. Subsequent runs will only notify you of truly new machines.

### Schedule Regular Runs

**On Linux/Mac (using cron):**

```bash
# Edit crontab
crontab -e

# Add this line to run every 5 minutes
*/5 * * * * cd /path/to/project && /usr/bin/python3 main.py >> cron.log 2>&1
```

**On Windows (using Task Scheduler):**

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., every 5 minutes)
4. Set action: Start a program → `python` with argument `main.py`

## Configuration

### config.json Structure

```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  },
  "database": {
    "path": "machines.db"
  },
  "scraping": {
    "delay_between_requests": 2.0,
    "request_timeout": 30,
    "max_retries": 3,
    "user_agent": "Mozilla/5.0..."
  },
  "websites": [
    {
      "url": "https://example.com/machines",
      "website_type": "aisequip",
      "search_title": "Example Machines",
      "enabled": true
    }
  ]
}
```

### Adding More URLs

To monitor multiple categories or websites, add more entries to the `websites` array:

```json
"websites": [
  {
    "url": "https://www.aisequip.com/pre-owned-machines/?_categories=whl-loader",
    "website_type": "aisequip",
    "search_title": "AIS - Wheel Loaders",
    "enabled": true
  },
  {
    "url": "https://www.aisequip.com/pre-owned-machines/?_categories=excavator",
    "website_type": "aisequip",
    "search_title": "AIS - Excavators",
    "enabled": true
  }
]
```

## Extending for New Websites

### Step 1: Create a New Scraper

Create a new file in `scrapers/` (e.g., `scrapers/newsite_scraper.py`):

```python
from scrapers.base_scraper import BaseScraper
from models import Machine
from bs4 import BeautifulSoup
from typing import List, Optional

class NewSiteScraper(BaseScraper):
    """Scraper for newsite.com"""
    
    def parse_page(self, soup: BeautifulSoup) -> List[Machine]:
        """Extract machines from page"""
        machines = []
        
        # Find all machine elements (adjust selector for the site)
        machine_elements = soup.find_all('div', class_='machine-item')
        
        for element in machine_elements:
            machine = self.extract_machine_data(element)
            if machine:
                machines.append(machine)
        
        return machines
    
    def extract_machine_data(self, element) -> Optional[Machine]:
        """Extract data from a single machine element"""
        # Extract fields based on the website's HTML structure
        title = element.find('h3').get_text(strip=True)
        link = element.find('a')['href']
        unique_id = link.split('/')[-1]  # Adjust as needed
        
        # ... extract other fields ...
        
        return Machine(
            unique_id=unique_id,
            title=title,
            category="Category",
            link=link,
            # ... other fields ...
        )
```

### Step 2: Register the Scraper

Edit `scrapers/__init__.py`:

```python
from scrapers.newsite_scraper import NewSiteScraper

__all__ = ['BaseScraper', 'AISEquipScraper', 'NewSiteScraper']
```

Edit `scraper_factory.py`:

```python
from scrapers.newsite_scraper import NewSiteScraper

class ScraperFactory:
    _scrapers = {
        'aisequip': AISEquipScraper,
        'newsite': NewSiteScraper,  # Add this line
    }
```

### Step 3: Add to Configuration

Add the new website to `config.json`:

```json
{
  "url": "https://newsite.com/machines",
  "website_type": "newsite",
  "search_title": "New Site - All Machines",
  "enabled": true
}
```

## Database Schema

The SQLite database has a single table `machines`:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| website_type | VARCHAR(100) | Website identifier (e.g., "aisequip") |
| search_title | VARCHAR(200) | Search title from config |
| unique_id | VARCHAR(100) | Machine's unique identifier |
| title | VARCHAR(200) | Machine title |
| category | VARCHAR(100) | Machine category |
| price | VARCHAR(50) | Price as string |
| year | VARCHAR(10) | Year of manufacture |
| hours | VARCHAR(20) | Operating hours |
| location | VARCHAR(100) | Location |
| link | TEXT | Full URL to machine |
| image_url | TEXT | Image URL |
| created_at | TIMESTAMP | When first discovered |

**Unique constraint**: `(website_type, unique_id)`

## Logging

Logs are written to:
- `scraper.log` - Full detailed logs
- Console output - Important messages

## Troubleshooting

### No notifications received

1. Check `scraper.log` for errors
2. Verify Telegram credentials in `config.json`
3. Test connection: Look for "Telegram bot connected" message

### Database locked errors

- Don't run multiple instances simultaneously
- If stuck, delete `machines.db` and restart

### Scraping failures

- Check internet connection
- Website structure may have changed (update scraper)
- Check `scraper.log` for specific errors

## Architecture

The system uses several design patterns:

- **Strategy Pattern**: Different scraping strategies for different websites
- **Factory Pattern**: `ScraperFactory` creates appropriate scrapers
- **Template Method Pattern**: `BaseScraper` defines workflow, subclasses implement details
- **Singleton Pattern**: Database connection management

## Project Structure

```
.
├── main.py                    # Main orchestrator
├── config.json                # Configuration file
├── config_schema.py           # Configuration loader
├── models.py                  # Data models
├── database.py                # Database handler
├── telegram_notifier.py       # Telegram notifications
├── scraper_factory.py         # Scraper factory
├── scrapers/
│   ├── __init__.py
│   ├── base_scraper.py        # Abstract base scraper
│   └── aisequip_scraper.py    # AIS Equipment scraper
├── requirements.txt           # Python dependencies
├── machines.db                # SQLite database (created on first run)
└── scraper.log                # Log file
```

## License

This project is provided as-is for personal use.

## Support

For issues or questions, check the logs first. Most problems are logged with helpful error messages.
