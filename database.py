import sqlite3
from pathlib import Path

class fit_downloader_db:
    def __init__(self, db_file):
        self.db_file = db_file
        self.init_db()

    def init_db(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
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
        conn.commit()
        conn.close()

    def save_activity_to_db(self, activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO activities (activity_id, file_type, name, start_time, file_path, downloaded_at, activity_type_key, activity_type_id, activity_type_parent_id)
            VALUES (?, ?, ?, ?, ?, datetime('now'), ?, ?, ?)
        ''', (activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id))
        conn.commit()
        conn.close()

    def is_activity_saved(self, activity_id, filetype):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT activity_id FROM activities WHERE activity_id = ? AND file_type = ?', (activity_id, filetype))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def cleanup_orphaned_entries(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT activity_id, file_path, file_type FROM activities')
        entries = cursor.fetchall()
        already_seen_files = set()
        for entry_id, file_path, file_type in entries:
            if self._should_delete_entry(file_path, file_type, already_seen_files):
                cursor.execute('DELETE FROM activities WHERE activity_id = ? and file_type = ?', (entry_id, file_type))
            else:
                already_seen_files.add(file_path)
        conn.commit()
        conn.close()

    def _should_delete_entry(self, file_path: str, filetype: str, already_seen_files: set) -> bool:
        path_object = Path(file_path)
    
        if not path_object.exists():
            return True
     
        if (file_path, filetype) in already_seen_files:
            return True

        return False
    
    def get_all_activities(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT activity_id, file_type, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id FROM activities')
        activities = cursor.fetchall()
        conn.close()
        return activities
    
    def update_activity_file_path(self, activity_id, new_file_path, filetype):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('UPDATE activities SET file_path = ?, file_type = ? WHERE activity_id = ? and file_type = ?', (new_file_path, filetype, activity_id, filetype))
        conn.commit()
        conn.close()

    def get_all_activities(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT activity_id, file_type, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id FROM activities')
        activities = cursor.fetchall()
        conn.close()
        return activities