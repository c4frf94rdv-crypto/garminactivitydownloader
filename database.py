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
                id INTEGER PRIMARY KEY,
                activity_id TEXT UNIQUE,
                name TEXT,
                start_time TEXT,
                file_path TEXT,
                downloaded_at TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def save_activity_to_db(self, activity_id, name, start_time, file_path):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO activities (activity_id, name, start_time, file_path, downloaded_at)
            VALUES (?, ?, ?, ?, datetime('now'))
        ''', (activity_id, name, start_time, file_path))
        conn.commit()
        conn.close()

    def is_activity_saved(self, activity_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM activities WHERE activity_id = ?', (activity_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None

    def cleanup_orphaned_entries(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()
        cursor.execute('SELECT id, file_path FROM activities')
        entries = cursor.fetchall()
        already_seen_files = set()
        for entry_id, file_path in entries:
            if self._should_delete_entry(file_path, already_seen_files):
                cursor.execute('DELETE FROM activities WHERE id = ?', (entry_id,))
            else:
                already_seen_files.add(file_path)
        conn.commit()
        conn.close()

    def _should_delete_entry(self, file_path: str, already_seen_files: set) -> bool:
        path_object = Path(file_path)
    
        if not path_object.exists():
            return True
     
        if file_path in already_seen_files:
            return True

        return False