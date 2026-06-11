import sqlite3
import os
import logging
from pathlib import Path


logger = logging.getLogger(__name__)
class GarminDownloaderDB:
    def __init__(self, config):
        self.download_dir = config.download_dir
        self.db_file = config.db_file
        self.basedir = config.basedir
        self.conn = sqlite3.connect(self._get_db_file_path())
        self._init_db()
        self.cleanup_orphaned_entries()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

    def _get_db_file_path(self):
        """
        Returns the full path to the SQLite database file.
        """
        return os.path.join(self.basedir, self.download_dir, self.db_file)

    def _init_db(self):
        """
        Initializes the database by creating the activities table if it doesn't exist.
        """
        cursor = self.conn.cursor()
        # Create table activites if not exists
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT,
                file_type TEXT,
                PRIMARY KEY (activity_id, file_type)
            )
        ''')
        
        # List of columns in table activities
        required_columns = {
            "name": "TEXT",
            "start_time": "TEXT",
            "file_path": "TEXT",
            "downloaded_at": "TEXT",
            "activity_type_key": "TEXT",
            "activity_type_id": "INTEGER",
            "activity_type_parent_id": "INTEGER"
        }

        # Check table for exisiting columns
        cursor.execute("PRAGMA table_info(activities)")
        existing_columns = [row[1] for row in cursor.fetchall()]

        # dynamicaly add columns if they dont exist
        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                logger.debug(f"Adding missing column '{col_name}' to activities table.")
                cursor.execute(f"ALTER TABLE activities ADD COLUMN {col_name} {col_type}")
        
        self.conn.commit()

    def save_activity_to_db(self, activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id):
        """
        Saves the activity information to the database.
        :param activity_id: The ID of the activity.
        :param filetype: The type of the file (e.g., 'fit', 'tcx').
        :param name: The name of the activity.
        :param start_time: The start time of the activity.
        :param file_path: The relative file path where the activity file is stored.
        :param activity_type_key: The key of the activity type.
        :param activity_type_id: The ID of the activity type.
        :param activity_type_parent_id: The parent ID of the activity type.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO activities (activity_id, file_type, name, start_time, file_path, downloaded_at, activity_type_key, activity_type_id, activity_type_parent_id)
                VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
            ''', (activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id))
            self.conn.commit()
        except sqlite3.IntegrityError:
            logger.warning(f"Activity {activity_id} / {filetype} already exists in database, skipping insert.")

    def is_activity_saved(self, activity_id, filetype):
        """
        Checks if the activity with the given ID and file type is already saved in the database.
        :param activity_id: The ID of the activity to check.
        :param filetype: The type of the file to check.
        :return: True if the activity is saved, False otherwise.
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT activity_id FROM activities WHERE activity_id = ? AND file_type = ?', (activity_id, filetype))
        result = cursor.fetchone()
        return result is not None

    def is_file_path_saved(self, file_path):
        """
        Checks if any activity in the database references the given relative file path.
        :param file_path: The relative file path to check ("/"-separated, as stored in the database).
        :return: True if an entry references the path, False otherwise.
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM activities WHERE file_path = ?', (file_path,))
        return cursor.fetchone() is not None

    def cleanup_orphaned_entries(self):
        """
        Cleans up database entries that reference files that no longer exist or are duplicates.
        This method checks all entries in the database and deletes those that reference files that do not exist on disk or are duplicates of existing files.
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT activity_id, file_path, file_type FROM activities')
        entries = cursor.fetchall()
        already_seen_files = set()
        deleted_count = 0
        for entry_id, file_path, file_type in entries:
            file_path = os.path.join(self.basedir, self.download_dir, file_path)
            if self._should_delete_entry(file_path, file_type, already_seen_files):
                cursor.execute('DELETE FROM activities WHERE activity_id = ? and file_type = ?', (entry_id, file_type))
                deleted_count += 1
                logger.debug(f"Orphaned entry deleted: {file_path}")
            else:
                already_seen_files.add((file_path, file_type))
        self.conn.commit()
        if deleted_count > 0:
            logger.info(f"Cleanup completed: {deleted_count} orphaned entries removed.")

    def _should_delete_entry(self, file_path: str, filetype: str, already_seen_files: set) -> bool:
        """
        Determines whether a database entry should be deleted based on the existence of the file and whether it is a duplicate.
        :param file_path: The full path to the file referenced by the database entry.
        :param filetype: The type of the file (e.g., 'fit', 'tcx').
        :param already_seen_files: A set of file paths and types that have already been seen during the cleanup process.
        :return: True if the entry should be deleted, False otherwise.
        """
        path_object = Path(file_path)
    
        if not path_object.exists():
            return True
        if (file_path, filetype) in already_seen_files:
            return True
        return False
    
    def get_all_activities(self):
        """
        Retrieves all activities from the database.
        :return: A list of tuples containing activity information (activity_id, file_type, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id).
        """
        cursor = self.conn.cursor()
        cursor.execute('SELECT activity_id, file_type, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id FROM activities')
        activities = cursor.fetchall()
        return activities
    
    def update_activity_file_path(self, activity_id, new_file_path, filetype):
        """
        Updates the file path for a specific activity and file type in the database.
        :param activity_id: The ID of the activity to update.
        :param new_file_path: The new file path to set for the activity.
        :param filetype: The type of the file to update (e.g., 'fit', 'tcx').
        """
        cursor = self.conn.cursor()
        cursor.execute('UPDATE activities SET file_path = ? WHERE activity_id = ? and file_type = ?', (new_file_path, activity_id, filetype))
        self.conn.commit()
