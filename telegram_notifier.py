import asyncio
import requests
from io import BytesIO
from telegram import Bot
from telegram.error import TelegramError
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_ids: Dict[str, str], backup_tokens: List[str] = None):
        # Build list of all bot tokens (primary + backups)
        self.bot_tokens = [bot_token]
        if backup_tokens:
            # Filter out placeholder tokens
            valid_backups = [t for t in backup_tokens if t and not t.startswith("BACKUP_BOT_TOKEN") and not t.startswith("YOUR_BACKUP")]
            self.bot_tokens.extend(valid_backups)
        
        self.chat_ids = chat_ids
        # Use default as fallback
        self.default_chat_id = chat_ids.get('default')
        if not self.default_chat_id and chat_ids:
            # If no default, use the first one available
            self.default_chat_id = next(iter(chat_ids.values()))
    
    def _get_chat_id(self, website_type: str = None) -> str:
        """Get the appropriate chat ID for the website type"""
        if not website_type:
            return self.default_chat_id
            
        # Try to get specific chat ID for website type
        chat_id = self.chat_ids.get(website_type.lower())
        
        # Fallback to default if not found
        if not chat_id:
            chat_id = self.default_chat_id
            
        return chat_id
    
    async def send_new_items_notification(self, search_title: str, machines: List[Dict], website_type: str = None):
        """Send notification for new machines found"""
        if not machines:
            return
        
        try:
            for machine in machines:
                await self._send_machine_notification(search_title, machine, website_type)
                # Delay between messages to avoid Telegram flood control
                await asyncio.sleep(2)
        except TelegramError as e:
            logger.error(f"Error sending Telegram notification: {e}")
    
    async def _send_machine_notification(self, search_title: str, machine: Dict, website_type: str = None):
        """Send notification for a single machine with image (with bot fallback)"""
        # Format message
        message = self._format_message(search_title, machine)
        
        # Get appropriate chat ID
        chat_id = self._get_chat_id(website_type)
        
        # Try to send with image
        image_url = machine.get('image_url', '')
        
        # Try each bot in order (primary, then backups)
        for bot_idx, bot_token in enumerate(self.bot_tokens):
            bot_name = "Primary Bot" if bot_idx == 0 else f"Backup Bot {bot_idx}"
            
            try:
                bot = Bot(token=bot_token)
                
                if image_url:
                    try:
                        # Download image
                        image_data = self._download_image(image_url)
                        
                        if image_data:
                            # Send photo with caption
                            async with bot:
                                await bot.send_photo(
                                    chat_id=chat_id,
                                    photo=image_data,
                                    caption=message,
                                    parse_mode='HTML'
                                )
                            logger.info(f"✓ {bot_name} sent notification with image: {machine['title']}")
                            return  # Success!
                    except Exception as e:
                        logger.warning(f"{bot_name}: Failed to send image, trying text only: {e}")
                
                # Fallback: send text only
                async with bot:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML'
                    )
                logger.info(f"✓ {bot_name} sent text notification: {machine['title']}")
                return  # Success!
                
            except Exception as e:
                logger.error(f"✗ {bot_name} failed: {e}")
                if bot_idx < len(self.bot_tokens) - 1:
                    logger.info(f"→ Trying {['Backup Bot 1', 'Backup Bot 2'][bot_idx]}...")
                    continue
                else:
                    logger.error(f"✗ All {len(self.bot_tokens)} bots failed for: {machine['title']}")
                    raise
    
    def _format_message(self, search_title: str, machine: Dict) -> str:
        """Format the notification message"""
        message = f"🆕 <b>New item(s) found on {search_title}:</b>\n\n"
        message += f"<b>Title:</b> {machine['title']}\n"
        
        if machine.get('price'):
            message += f"<b>Price:</b> {machine['price']}\n"
        
        if machine.get('location'):
            message += f"<b>Location:</b> {machine['location']}\n"
        
        if machine.get('hours'):
            message += f"<b>Hours:</b> {machine['hours']}\n"
        
        message += f"<b>Link:</b> {machine['link']}"
        
        return message
    
    def _download_image(self, image_url: str) -> BytesIO:
        """Download image from URL"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = requests.get(image_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            return BytesIO(response.content)
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            return None
    
    async def send_alert(self, message: str) -> bool:
        """Send a general alert message (with bot fallback)"""
        formatted_message = f"⚠️ <b>ALERT</b>\n\n{message}"
        
        # Try each bot
        for bot_idx, bot_token in enumerate(self.bot_tokens):
            bot_name = "Primary Bot" if bot_idx == 0 else f"Backup Bot {bot_idx}"
            try:
                bot = Bot(token=bot_token)
                async with bot:
                    await bot.send_message(
                        chat_id=self.default_chat_id,
                        text=formatted_message,
                        parse_mode='HTML'
                    )
                logger.info(f"✓ {bot_name} sent alert: {message[:50]}...")
                return True
            except Exception as e:
                logger.error(f"✗ {bot_name} failed: {e}")
                if bot_idx < len(self.bot_tokens) - 1:
                    continue
        
        logger.error("✗ All bots failed to send alert")
        return False
    
    async def send_zero_items_alert(self, search_title: str, url: str, website_type: str = None) -> bool:
        """
        Send alert when a URL scrapes 0 items (with bot fallback)
        """
        message = (
            f"⚠️ <b>Zero Items Alert</b>\n\n"
            f"<b>Source:</b> {search_title}\n"
            f"<b>Status:</b> Scraped 0 items\n"
            f"<b>URL:</b> {url[:80]}...\n\n"
            f"This might indicate:\n"
            f"• Website structure changed\n"
            f"• No items available\n"
            f"• Scraping issue"
        )
        
        chat_id = self._get_chat_id(website_type)
        
        # Try each bot
        for bot_idx, bot_token in enumerate(self.bot_tokens):
            bot_name = "Primary Bot" if bot_idx == 0 else f"Backup Bot {bot_idx}"
            try:
                bot = Bot(token=bot_token)
                async with bot:
                    await bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                logger.info(f"✓ {bot_name} sent zero items alert for: {search_title}")
                return True
            except Exception as e:
                logger.error(f"✗ {bot_name} failed: {e}")
                if bot_idx < len(self.bot_tokens) - 1:
                    continue
        
        logger.error("✗ All bots failed to send zero items alert")
        return False
    
    async def test_connection(self):
        """Test Telegram bot connection (tests all bots)"""
        results = []
        for bot_idx, bot_token in enumerate(self.bot_tokens):
            try:
                bot = Bot(token=bot_token)
                async with bot:
                    await bot.get_me()
                results.append(True)
            except TelegramError:
                results.append(False)
        
        # Summary log
        connected = sum(results)
        failed = len(results) - connected
        logger.info(f"🤖 Telegram: {connected} bot(s) connected, {failed} failed")
        
        # Return True if at least one bot works
        return any(results)
    
    async def request_proxies_from_user(self) -> bool:
        """
        Send a message to Telegram requesting proxies from the user
        
        Returns:
            True if message sent successfully, False otherwise
        """
        message = (
            "🔄 <b>Proxy Request</b>\\n\\n"
            "The scraper needs proxies to continue.\\n"
            "Please send a list of proxies in one of these formats:\\n\\n"
            "<code>ip:port</code>\\n"
            "<code>ip:port:username:password</code>\\n\\n"
            "Example:\\n"
            "<code>216.10.27.159:6837:ljxlfyox:n8c9ncgh4zvo\\n"
            "65.111.29.119:3129</code>\\n\\n"
            "⏸️ <b>Scraping is paused</b> until you respond."
        )
        
        # Try each bot
        for bot_idx, bot_token in enumerate(self.bot_tokens):
            bot_name = "Primary Bot" if bot_idx == 0 else f"Backup Bot {bot_idx}"
            try:
                bot = Bot(token=bot_token)
                async with bot:
                    await bot.send_message(
                        chat_id=self.default_chat_id,
                        text=message,
                        parse_mode='HTML'
                    )
                logger.info(f"✓ {bot_name} sent proxy request message")
                return True
            except Exception as e:
                logger.error(f"✗ {bot_name} failed to send proxy request: {e}")
                if bot_idx < len(self.bot_tokens) - 1:
                    continue
        
        logger.error("✗ All bots failed to send proxy request")
        return False
    
    async def wait_for_proxy_response(self, timeout: int = 3600) -> Optional[str]:
        """
        Wait for user's proxy response message using polling
        This will BLOCK the scraper until user responds or timeout occurs
        
        Args:
            timeout: Maximum time to wait in seconds (default: 1 hour)
            
        Returns:
            Proxy text from user's message, or None if timeout/error
        """
        logger.info(f"⏸️ Waiting for user to send proxies (timeout: {timeout}s)...")
        
        # Try each bot until one works
        for bot_idx, bot_token in enumerate(self.bot_tokens):
            bot_name = "Primary Bot" if bot_idx == 0 else f"Backup Bot {bot_idx}"
            
            try:
                bot = Bot(token=bot_token)
                
                # Get current update offset
                async with bot:
                    updates = await bot.get_updates(limit=1, timeout=5)
                    last_update_id = updates[-1].update_id if updates else 0
                
                logger.info(f"Using {bot_name} for message polling (offset: {last_update_id})")
                
                # Poll for new messages
                start_time = asyncio.get_event_loop().time()
                poll_interval = 2  # Check every 2 seconds
                
                while (asyncio.get_event_loop().time() - start_time) < timeout:
                    try:
                        async with bot:
                            updates = await bot.get_updates(
                                offset=last_update_id + 1,
                                timeout=poll_interval,
                                allowed_updates=['message']
                            )
                        
                        if updates:
                            logger.info(f"📨 Received {len(updates)} update(s)")
                            for update in updates:
                                last_update_id = update.update_id
                                logger.debug(f"Update {update.update_id}: has_message={bool(update.message)}")
                                
                                # Accept proxy messages from ANY chat (DM or group)
                                if update.message:
                                    msg_chat_id = str(update.message.chat.id)
                                    logger.info(f"Message from chat: {msg_chat_id}")
                                    
                                    # Check if it's a text message
                                    if update.message.text:
                                        proxy_text = update.message.text.strip()
                                        logger.info(f"✓ Received proxy message from user ({len(proxy_text)} chars)")
                                        return proxy_text
                                    else:
                                        logger.warning(f"Message received but no text content")
                        
                        # Small delay between polls
                        await asyncio.sleep(0.5)
                        
                    except TelegramError as e:
                        logger.warning(f"Polling error: {e}")
                        await asyncio.sleep(1)
                        continue
                
                # Timeout reached
                logger.warning(f"⏱️ Timeout reached ({timeout}s) waiting for proxy response")
                return None
                
            except Exception as e:
                logger.error(f"✗ {bot_name} failed during polling: {e}")
                if bot_idx < len(self.bot_tokens) - 1:
                    logger.info(f"→ Trying next bot...")
                    continue
                else:
                    logger.error("✗ All bots failed during proxy polling")
                    return None
        
        return None

