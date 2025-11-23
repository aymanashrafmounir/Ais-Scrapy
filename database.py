import sqlite3
import logging
from datetime import datetime
from typing import List, Optional, Tuple
from contextlib import contextmanager
from models import Machine

logger = logging.getLogger(__name__)


class DatabaseHandler:
    """Handles all database operations for machine tracking"""
    
    def __init__(self, db_path: str = "machines.db"):
        self.db_path = db_path
        self._create_tables()
        logger.info(f"Database initialized: {db_path}")
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def _create_tables(self) -> None:
        """Create database tables if they don't exist"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS machines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_title VARCHAR(200) NOT NULL,
                    website_type VARCHAR(100) NOT NULL,
                    unique_id VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(search_title, unique_id)
                )
            ''')
            
            # Create markers table for Craigslist marker-based tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS markers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_title VARCHAR(200) NOT NULL UNIQUE,
                    marker_id VARCHAR(100) NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create index for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_search_unique 
                ON machines(search_title, unique_id)
            ''')
            
            logger.debug("Database tables created/verified")
    
    def is_new_machine(self, search_title: str, unique_id: str) -> bool:
        """
        Check if a machine is new for this specific search title
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT COUNT(*) FROM machines WHERE search_title = ? AND unique_id = ?',
                (search_title, unique_id)
            )
            count = cursor.fetchone()[0]
            return count == 0
    
    def save_machine(self, search_title: str, website_type: str, unique_id: str) -> bool:
        """
        Save a new machine to the database for this specific search title
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO machines (search_title, website_type, unique_id) 
                    VALUES (?, ?, ?)
                ''', (search_title, website_type, unique_id))
                logger.debug(f"Saved new machine ID: {unique_id}")
                return True
        except sqlite3.IntegrityError:
            logger.debug(f"Machine already exists: {unique_id}")
            return False
        except Exception as e:
            logger.error(f"Error saving machine {unique_id}: {e}")
            return False
            
    def cleanup_old_machines(self, search_title: str, active_unique_ids: List[str]) -> int:
        """
        Remove machines from DB that are no longer in the active list for this search title
        
        Args:
            search_title: The specific search title to clean up
            active_unique_ids: List of unique_ids currently found on the site
            
        Returns:
            Number of deleted machines
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get all existing IDs for this search title
                cursor.execute('SELECT unique_id FROM machines WHERE search_title = ?', (search_title,))
                existing_ids = {row[0] for row in cursor.fetchall()}
                
                # Identify IDs to delete
                ids_to_delete = existing_ids - set(active_unique_ids)
                
                if not ids_to_delete:
                    return 0
                
                # Delete them
                placeholders = ','.join('?' * len(ids_to_delete))
                cursor.execute(
                    f'DELETE FROM machines WHERE search_title = ? AND unique_id IN ({placeholders})',
                    (search_title, *ids_to_delete)
                )
                
                deleted_count = cursor.rowcount
                if deleted_count > 0:
                    logger.info(f"Cleaned up {deleted_count} old machines from DB for '{search_title}'")
                    for mid in ids_to_delete:
                        logger.debug(f"Removed: {mid}")
                        
                return deleted_count
                
        except Exception as e:
            logger.error(f"Error cleaning up machines for '{search_title}': {e}")
            return 0
    
    def get_all_machines(self, website_type: Optional[str] = None) -> List[Tuple]:
        """
        Get all machines from database
        
        Args:
            website_type: Optional filter by website type
            
        Returns:
            List of machine records
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if website_type:
                cursor.execute(
                    'SELECT * FROM machines WHERE website_type = ? ORDER BY created_at DESC',
                    (website_type,)
                )
            else:
                cursor.execute('SELECT * FROM machines ORDER BY created_at DESC')
            
            return cursor.fetchall()
    
    def get_machine_count(self) -> int:
        """Get total number of machines in database"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM machines')
            return cursor.fetchone()[0]
    
    def delete_machine(self, website_type: str, unique_id: str) -> bool:
        """
        Delete a machine from database (for testing)
        
        Args:
            website_type: Type of website
            unique_id: Unique identifier
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'DELETE FROM machines WHERE website_type = ? AND unique_id = ?',
                    (website_type, unique_id)
                )
                deleted = cursor.rowcount > 0
                if deleted:
                    logger.info(f"Deleted machine: {unique_id}")
                return deleted
        except Exception as e:
            logger.error(f"Error deleting machine {unique_id}: {e}")
            return False
    
    def get_marker(self, search_title: str) -> Optional[str]:
        """
        Get the marker ID for a search title (for Craigslist tracking)
        
        Args:
            search_title: The search title to get marker for
            
        Returns:
            marker_id if found, None otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT marker_id FROM markers WHERE search_title = ?',
                    (search_title,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting marker for '{search_title}': {e}")
            return None
    
    def save_marker(self, search_title: str, marker_id: str) -> bool:
        """
        Save or update the marker ID for a search title (for Craigslist tracking)
        
        Args:
            search_title: The search title
            marker_id: The marker ID (usually the first item's unique_id)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO markers (search_title, marker_id, updated_at) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(search_title) 
                    DO UPDATE SET marker_id = ?, updated_at = CURRENT_TIMESTAMP
                ''', (search_title, marker_id, marker_id))
                logger.info(f"Saved marker for '{search_title}': {marker_id}")
                return True
        except Exception as e:
            logger.error(f"Error saving marker for '{search_title}': {e}")
            return False
