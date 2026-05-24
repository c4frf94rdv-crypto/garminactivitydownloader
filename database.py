import sqlite3
import os
from pathlib import Path

class GarminDownloaderDB:
    def __init__(self, download_dir, db_file):
        self.download_dir = download_dir
        self.db_file = db_file
        self.conn = sqlite3.connect(self._get_db_file_path())
        self._init_db()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

    def _get_db_file_path(self):
        """Returns the full path to the SQLite database file."""
        return os.path.join(self.download_dir, self.db_file)

    def _init_db(self):
        """Initializes the database by creating the activities table if it doesn't exist."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS activities (
                activity_id TEXT,
                file_type TEXT,
                name TEXT,
                start_time TEXT,
                file_path TEXT,
                downloaded_at TEXT,
                activity_type_key TEXT,
                activity_type_id INTEGER,
                activity_type_parent_id INTEGER,
                PRIMARY KEY (activity_id, file_type)
            )
        ''')
        self.conn.commit()

    def save_activity_to_db(self, activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id):
        """Saves the activity information to the database.
        :param activity_id: The ID of the activity.
        :param filetype: The type of the file (e.g., 'fit', 'tcx').
        :param name: The name of the activity.
        :param start_time: The start time of the activity.
        :param file_path: The relative file path where the activity file is stored.
        :param activity_type_key: The key of the activity type.
        :param activity_type_id: The ID of the activity type.
        :param activity_type_parent_id: The parent ID of the activity type."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO activities (activity_id, file_type, name, start_time, file_path, downloaded_at, activity_type_key, activity_type_id, activity_type_parent_id)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
        ''', (activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id))
        self.conn.commit()

    def is_activity_saved(self, activity_id, filetype):
        """Checks if the activity with the given ID and file type is already saved in the database.
        :param activity_id: The ID of the activity to check.
        :param filetype: The type of the file to check.
        :return: True if the activity is saved, False otherwise."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT activity_id FROM activities WHERE activity_id = ? AND file_type = ?', (activity_id, filetype))
        result = cursor.fetchone()
        return result is not None

    def cleanup_orphaned_entries(self):
        """Cleans up database entries that reference files that no longer exist or are duplicates.
        This method checks all entries in the database and deletes those that reference files that do not exist on disk or are duplicates of existing files."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT activity_id, file_path, file_type FROM activities')
        entries = cursor.fetchall()
        already_seen_files = set()
        for entry_id, file_path, file_type in entries:
            file_path = os.path.join(os.getcwd(), self.download_dir, file_path)
            if self._should_delete_entry(file_path, file_type, already_seen_files):
                cursor.execute('DELETE FROM activities WHERE activity_id = ? and file_type = ?', (entry_id, file_type))
            else:
                already_seen_files.add((file_path, file_type))
        self.conn.commit()

    def _should_delete_entry(self, file_path: str, filetype: str, already_seen_files: set) -> bool:
        """Determines whether a database entry should be deleted based on the existence of the file and whether it is a duplicate.
        :param file_path: The full path to the file referenced by the database entry.
        :param filetype: The type of the file (e.g., 'fit', 'tcx').
        :param already_seen_files: A set of file paths and types that have already been seen during the cleanup process.
        :return: True if the entry should be deleted, False otherwise."""
        path_object = Path(file_path)
    
        if not path_object.exists():
            return True
        if (file_path, filetype) in already_seen_files:
            return True
        return False
    
    def get_all_activities(self):
        """Retrieves all activities from the database.
        :return: A list of tuples containing activity information (activity_id, file_type, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id)."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT activity_id, file_type, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id FROM activities')
        activities = cursor.fetchall()
        return activities
    
    def update_activity_file_path(self, activity_id, new_file_path, filetype):
        """Updates the file path for a specific activity and file type in the database.
        :param activity_id: The ID of the activity to update.
        :param new_file_path: The new file path to set for the activity.
        :param filetype: The type of the file to update (e.g., 'fit', 'tcx').
        :return: True if the update was successful, False otherwise."""
        cursor = self.conn.cursor()
        cursor.execute('UPDATE activities SET file_path = ?, file_type = ? WHERE activity_id = ? and file_type = ?', (new_file_path, filetype, activity_id, filetype))
        self.conn.commit()