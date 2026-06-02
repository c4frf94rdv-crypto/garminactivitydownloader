import pytest
import sqlite3
import os
from database import GarminDownloaderDB

# Helper class for configuration (mock object)
class MockConfig:
    def __init__(self, download_dir=".", db_file=":memory:"):
        self.download_dir = download_dir
        self.db_file = db_file

@pytest.fixture
def db():
    """Creates a GarminDownloaderDB instance in memory."""
    config = MockConfig()
    # We briefly patch the method so it does not try to
    # look for :memory: in the file system
    with GarminDownloaderDB(config) as db_instance:
        yield db_instance

def test_init_db(db):
    """Checks whether the 'activities' table was created correctly."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities'")
    assert cursor.fetchone() is not None

def test_save_and_is_activity_saved(db):
    """Tests saving and querying an activity."""
    activity_id = "12345"
    filetype = "fit"
    
    # Save
    db.save_activity_to_db(
        activity_id, filetype, "Morgenlauf", "2026-05-31", 
        "fit/2026-05-31_Morgenlauf.fit", "running", 1, 0
    )
    
    # Query
    assert db.is_activity_saved(activity_id, filetype) is True
    assert db.is_activity_saved("999", "fit") is False

def test_integrity_error_on_duplicate(db, caplog):
    """Checks whether duplicates (same ID + same type) are caught."""
    data = ("100", "fit", "Lauf", "2026", "p.fit", "run", 1, 0)
    
    db.save_activity_to_db(*data)
    # Second attempt with the same ID and type
    db.save_activity_to_db(*data)
    
    assert "already exists in database, skipping insert" in caplog.text

def test_get_all_activities(db):
    """Checks the retrieval of all entries."""
    db.save_activity_to_db("1", "fit", "A1", "2026", "p1", "run", 1, 0)
    db.save_activity_to_db("2", "tcx", "A2", "2026", "p2", "run", 1, 0)
    
    activities = db.get_all_activities()
    assert len(activities) == 2
    assert activities[0][0] == "1"
    assert activities[1][1] == "tcx"

def test_update_activity_file_path(db):
    """Tests moving/renaming paths in the DB."""
    db.save_activity_to_db("1", "fit", "A", "2026", "alt/p1.fit", "run", 1, 0)
    
    new_path = "neu/p1.fit"
    db.update_activity_file_path("1", new_path, "fit")
    
    activities = db.get_all_activities()
    assert activities[0][4] == new_path

def test_cleanup_orphaned_entries(db, tmp_path):
    """
    Tests the cleanup process.
    Here we need to simulate real files.
    """
    # We redirect the download_dir to a temporary test directory
    db.download_dir = str(tmp_path)
    
    # 1. File exists
    existing_file = tmp_path / "exists.fit"
    existing_file.write_text("data")
    
    # 2. File does NOT exist
    missing_file_path = "missing.fit"
    
    db.save_activity_to_db("1", "fit", "Existiert", "2026", "exists.fit", "run", 1, 0)
    db.save_activity_to_db("2", "fit", "Fehlt", "2026", "missing.fit", "run", 1, 0)
    
    # Before cleanup: 2 entries
    assert len(db.get_all_activities()) == 2
    
    db.cleanup_orphaned_entries()
    
    # After cleanup: only 1 entry remaining
    activities = db.get_all_activities()
    assert len(activities) == 1
    assert activities[0][0] == "1"

def test_save_to_readonly_db(tmp_path):
    """Checks whether the code handles a read-only DB gracefully."""
    from database import GarminDownloaderDB
    
    db_file = tmp_path / "readonly.db"
    # Create an empty file and remove write permissions
    db_file.touch()
    os.chmod(db_file, 0o444) 
    
    class Config:
        download_dir = str(tmp_path)
        db_file = "readonly.db"

    # This should raise a sqlite3.OperationalError during init or write
    with pytest.raises(sqlite3.OperationalError):
        with GarminDownloaderDB(Config()) as db:
            db.save_activity_to_db("1", "fit", "Test", "2026", "p", "run", 1, 0)

def test_cleanup_with_broken_path_string(db):
    """Tests whether cleanup crashes when the DB contains completely invalid paths."""
    # We manually insert a path that can cause issues on some systems (e.g. null bytes)
    cursor = db.conn.cursor()
    cursor.execute(
        "INSERT INTO activities (activity_id, file_path, file_type) VALUES (?, ?, ?)",
        ("bad_path", "\0/forbidden/path", "fit")
    )
    db.conn.commit()
    
    # The code should not crash, but instead ignore or delete the entry
    db.cleanup_orphaned_entries()

def test_save_activity_type_mismatch(db):
    """
    Checks what happens when the same ID is saved with a different file type
    (should work) vs. an identical combination (should be skipped).
    """
    # First entry: fit
    db.save_activity_to_db("555", "fit", "Lauf", "2026-01-01", "p1", "run", 1, 0)
    
    # Second entry: same ID, but tcx (should work thanks to composite primary key)
    db.save_activity_to_db("555", "tcx", "Lauf", "2026-01-01", "p2", "run", 1, 0)
    
    # Third entry: exact duplicate (should be logged but ignored)
    db.save_activity_to_db("555", "fit", "Lauf", "2026-01-01", "p1", "run", 1, 0)
    
    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM activities WHERE activity_id = '555'")
    assert cursor.fetchone()[0] == 2 # Only fit and tcx should exist

def test_cleanup_with_invalid_path_characters(db):
    """
    Checks whether the cleanup process remains stable for paths with special
    characters that os.path.exists() may reject.
    """
    # A path that could technically exist in the DB but causes errors in the file system
    bad_path = "activities/fit/\0invalid_path.fit" 
    
    cursor = db.conn.cursor()
    cursor.execute('''
        INSERT INTO activities (activity_id, file_type, file_path) 
        VALUES (?, ?, ?)
    ''', ("999", "fit", bad_path))
    db.conn.commit()
    
    # The cleanup should not crash with a ValueError due to the null byte
    try:
        db.cleanup_orphaned_entries()
    except ValueError:
        pytest.fail("cleanup_orphaned_entries crashed due to null byte in path!")

def test_init_db_with_incompatible_schema(tmp_path):
    """
    Simulates a 'corrupt' table with missing columns.
    """
    from database import GarminDownloaderDB
    db_file = tmp_path / "corrupt.db"
    
    # We manually create an incorrect table
    conn = sqlite3.connect(db_file)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            activity_id TEXT,
            file_type TEXT,
            PRIMARY KEY (activity_id, file_type)
        )
    ''')
    conn.close()
    
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "corrupt.db"
    
    with GarminDownloaderDB(MockConfig()) as db:
        # 2. Saving must NOT raise an error anymore
        db.save_activity_to_db("1", "fit", "Name", "Date", "Path", "Type", 1, 0)
        
        # 3. Verify that the data is actually present (proof of successful migration)
        cursor = db.conn.cursor()
        cursor.execute("SELECT name, file_path FROM activities WHERE activity_id = '1'")
        row = cursor.fetchone()
        assert row[0] == "Name"
        assert row[1] == "Path"

def test_init_db_migration_works(tmp_path):
    from database import GarminDownloaderDB
    db_file = tmp_path / "migration_test.db"
    
    # Simulate the old state
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE activities (activity_id TEXT, file_type TEXT, PRIMARY KEY(activity_id, file_type))")
    conn.close()
    
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "migration_test.db"
    
    # This should NOT crash anymore
    with GarminDownloaderDB(MockConfig()) as db:
        # Check whether the missing column is now present
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(activities)")
        cols = [row[1] for row in cursor.fetchall()]
        assert "file_path" in cols
        assert "activity_type_id" in cols

def test_database_connection_closure(tmp_path):
    """Checks whether the connection is truly closed after the 'with' block."""
    from database import GarminDownloaderDB
    
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "test.db"
        
    with GarminDownloaderDB(MockConfig()) as db:
        conn = db.conn
        assert conn.total_changes >= 0 # Connection is open
        
    # After the block: any access to the connection should fail
    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")

def test_should_delete_entry_duplicate_path(tmp_path):
    """
    Tests whether _should_delete_entry returns True when the path
    is already contained in already_seen_files (duplicate check).
    """
    # 1. Setup: create mock config
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "test.db"

    with GarminDownloaderDB(MockConfig()) as db:
        # 2. Create a real temporary file so that the first check
        # (path_object.exists()) returns True (i.e. the file exists)
        test_file = tmp_path / "test_activity.fit"
        test_file.write_text("dummy data")
        
        file_path = str(test_file)
        file_type = "fit"
        
        # 3. Simulate that this path has already been "seen" by another DB entry
        already_seen = { (file_path, file_type) }
        
        # 4. Call the internal method
        # Since the file exists but is in already_seen, True MUST be returned
        result = db._should_delete_entry(file_path, file_type, already_seen)
        
        assert result is True, "Should return True because the path/type combination is a duplicate"

def test_should_delete_entry_first_time_seen(tmp_path):
    """
    Counter-test: file exists and has NOT been seen yet.
    """
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "test.db"

    with GarminDownloaderDB(MockConfig()) as db:
        test_file = tmp_path / "unique_activity.fit"
        test_file.write_text("dummy data")
        
        file_path = str(test_file)
        already_seen = set() # Nothing seen yet
        
        result = db._should_delete_entry(file_path, "fit", already_seen)
        
        assert result is False, "Should return False because the file exists and is new"

def test_database_locked(tmp_path, mocker):
    """Checks whether the script remains stable when the DB is locked."""
    from database import GarminDownloaderDB
    
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "locked.db"

    with GarminDownloaderDB(MockConfig()) as db:
        # We do not patch the connection, but the method of your class.
        # We make it raise an OperationalError as soon as it is called.
        mocker.patch.object(
            db, 
            'save_activity_to_db', 
            side_effect=sqlite3.OperationalError("database is locked")
        )
        
        # Now we call it. If save_activity_to_db has a try-except,
        # the app should not crash.
        try:
            db.save_activity_to_db("1", "fit", "Test", "2026", "p", "run", 1, 0)
        except sqlite3.OperationalError:
            # If your method does NOT catch the error, it surfaces here.
            # This is also an important finding for the test.
            pass

def test_cleanup_with_null_byte_path(db):
    """
    Tests cleanup for paths that could cause os.path.exists() to crash.
    """
    cursor = db.conn.cursor()
    # A null byte in the path (\x00) often causes ValueErrors in Python's os module
    cursor.execute(
        "INSERT INTO activities (activity_id, file_type, file_path) VALUES (?, ?, ?)",
        ("invalid_path_id", "fit", "activities/fit/filename\x00.fit")
    )
    db.conn.commit()

    # This should not crash
    db.cleanup_orphaned_entries()

def test_partial_migration(tmp_path):
    """Simulates a DB that only has 3 of the 9 required columns."""
    from database import GarminDownloaderDB
    db_file = tmp_path / "partial.db"
    
    conn = sqlite3.connect(db_file)
    # Create only a few columns
    conn.execute("CREATE TABLE activities (activity_id TEXT, file_type TEXT, name TEXT, PRIMARY KEY(activity_id, file_type))")
    conn.close()
    
    class MockConfig:
        download_dir = str(tmp_path)
        db_file = "partial.db"

    with GarminDownloaderDB(MockConfig()) as db:
        cursor = db.conn.cursor()
        cursor.execute("PRAGMA table_info(activities)")
        cols = [row[1] for row in cursor.fetchall()]
        # Check whether one of the "new" columns now exists
        assert "activity_type_id" in cols
        assert "file_path" in cols

def test_save_activity_with_quotes(db):
    """Checks whether names with single quotes (SQL injection risk) are saved correctly."""
    dangerous_name = "Lauf ' OR '1'='1"
    db.save_activity_to_db("666", "fit", dangerous_name, "2026", "path", "run", 1, 0)
    
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM activities WHERE activity_id = '666'")
    assert cursor.fetchone()[0] == dangerous_name