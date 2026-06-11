import pytest
import sqlite3
import os
from database import GarminDownloaderDB


class MockConfig:
    def __init__(self, download_dir="", db_file=":memory:", basedir=""):
        self.download_dir = download_dir
        self.db_file = db_file
        self.basedir = basedir


@pytest.fixture
def db():
    """Creates a GarminDownloaderDB instance backed by an in-memory SQLite database."""
    with GarminDownloaderDB(MockConfig()) as db_instance:
        yield db_instance


def test_init_db(db):
    """The 'activities' table must be created on first init."""
    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities'")
    assert cursor.fetchone() is not None


def test_save_and_is_activity_saved(db):
    """A saved activity must be found by is_activity_saved; unknown IDs must return False."""
    db.save_activity_to_db("12345", "fit", "Morning Run", "2026-05-31", "fit/run.fit", "running", 1, 0)

    assert db.is_activity_saved("12345", "fit") is True
    assert db.is_activity_saved("999", "fit") is False


def test_integrity_error_on_duplicate(db, caplog):
    """Inserting the same activity_id + file_type twice must log a skip, not raise."""
    data = ("100", "fit", "Run", "2026", "p.fit", "running", 1, 0)
    db.save_activity_to_db(*data)
    db.save_activity_to_db(*data)

    assert "already exists in database, skipping insert" in caplog.text


def test_save_same_id_different_filetype(db):
    """The same activity_id with different file types must both be stored (composite key)."""
    db.save_activity_to_db("555", "fit", "Run", "2026-01-01", "p1.fit", "running", 1, 0)
    db.save_activity_to_db("555", "tcx", "Run", "2026-01-01", "p2.tcx", "running", 1, 0)
    db.save_activity_to_db("555", "fit", "Run", "2026-01-01", "p1.fit", "running", 1, 0)  # duplicate — skipped

    cursor = db.conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM activities WHERE activity_id = '555'")
    assert cursor.fetchone()[0] == 2


def test_is_file_path_saved(db):
    """is_file_path_saved must return True only for file paths referenced by an entry."""
    db.save_activity_to_db("12345", "fit", "Morning Run", "2026-05-31", "fit/run.fit", "running", 1, 0)

    assert db.is_file_path_saved("fit/run.fit") is True
    assert db.is_file_path_saved("fit/other.fit") is False


def test_get_all_activities(db):
    """get_all_activities must return all stored entries."""
    db.save_activity_to_db("1", "fit", "A1", "2026", "p1", "running", 1, 0)
    db.save_activity_to_db("2", "tcx", "A2", "2026", "p2", "running", 1, 0)

    activities = db.get_all_activities()
    assert len(activities) == 2
    assert activities[0][0] == "1"
    assert activities[1][1] == "tcx"


def test_update_activity_file_path(db):
    """update_activity_file_path must persist the new path in the database."""
    db.save_activity_to_db("1", "fit", "Run", "2026", "old/p1.fit", "running", 1, 0)
    db.update_activity_file_path("1", "new/p1.fit", "fit")

    activities = db.get_all_activities()
    assert activities[0][4] == "new/p1.fit"


def test_cleanup_orphaned_entries(db, tmp_path):
    """cleanup_orphaned_entries must remove DB entries whose files no longer exist on disk."""
    db.download_dir = str(tmp_path)

    existing_file = tmp_path / "exists.fit"
    existing_file.write_text("data")

    db.save_activity_to_db("1", "fit", "Exists", "2026", "exists.fit", "running", 1, 0)
    db.save_activity_to_db("2", "fit", "Missing", "2026", "missing.fit", "running", 1, 0)

    assert len(db.get_all_activities()) == 2
    db.cleanup_orphaned_entries()

    activities = db.get_all_activities()
    assert len(activities) == 1
    assert activities[0][0] == "1"


def test_cleanup_null_byte_path_does_not_crash(db):
    """Paths with null bytes in the DB must be handled gracefully by cleanup."""
    cursor = db.conn.cursor()
    cursor.execute(
        "INSERT INTO activities (activity_id, file_path, file_type) VALUES (?, ?, ?)",
        ("bad", "activities/\x00invalid.fit", "fit")
    )
    db.conn.commit()

    db.cleanup_orphaned_entries()  # must not raise


def test_cleanup_logs_when_entries_deleted(db, tmp_path, caplog):
    """cleanup_orphaned_entries must log the count only when entries are actually deleted."""
    import logging
    db.download_dir = str(tmp_path)
    db.save_activity_to_db("1", "fit", "Missing", "2026", "gone.fit", "running", 1, 0)

    with caplog.at_level(logging.INFO, logger="database"):
        db.cleanup_orphaned_entries()

    assert "1 orphaned entries removed" in caplog.text


def test_cleanup_silent_when_nothing_deleted(db, tmp_path, caplog):
    """cleanup_orphaned_entries must produce no INFO log when nothing is deleted."""
    import logging
    db.download_dir = str(tmp_path)

    existing = tmp_path / "run.fit"
    existing.write_text("data")
    db.save_activity_to_db("1", "fit", "Run", "2026", "run.fit", "running", 1, 0)

    with caplog.at_level(logging.INFO, logger="database"):
        db.cleanup_orphaned_entries()

    assert "orphaned entries removed" not in caplog.text


def test_save_to_readonly_db(tmp_path):
    """Writing to a read-only database file must raise sqlite3.OperationalError."""
    db_file = tmp_path / "readonly.db"
    db_file.touch()
    os.chmod(db_file, 0o444)

    class Config:
        download_dir = str(tmp_path)
        db_file = "readonly.db"
        basedir = str(tmp_path)

    with pytest.raises(sqlite3.OperationalError):
        with GarminDownloaderDB(Config()) as db:
            db.save_activity_to_db("1", "fit", "Test", "2026", "p", "running", 1, 0)


def test_schema_migration_adds_missing_columns(tmp_path):
    """Opening a DB with an outdated schema must add all missing columns without data loss."""
    db_file = tmp_path / "old.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE activities (activity_id TEXT, file_type TEXT, PRIMARY KEY(activity_id, file_type))")
    conn.close()

    class Config:
        download_dir = str(tmp_path)
        db_file = "old.db"
        basedir = str(tmp_path)

    with GarminDownloaderDB(Config()) as db:
        db.save_activity_to_db("1", "fit", "Name", "Date", "Path", "running", 1, 0)

        cursor = db.conn.cursor()
        cursor.execute("SELECT name, file_path FROM activities WHERE activity_id = '1'")
        row = cursor.fetchone()
        assert row[0] == "Name"
        assert row[1] == "Path"

        cursor.execute("PRAGMA table_info(activities)")
        cols = [r[1] for r in cursor.fetchall()]
        assert "file_path" in cols
        assert "activity_type_id" in cols


def test_database_connection_closure(tmp_path):
    """The SQLite connection must be closed after the context manager exits."""
    class Config:
        download_dir = str(tmp_path)
        db_file = "test.db"
        basedir = str(tmp_path)

    with GarminDownloaderDB(Config()) as db:
        conn = db.conn
        assert conn.total_changes >= 0

    with pytest.raises(sqlite3.ProgrammingError):
        conn.execute("SELECT 1")


def test_should_delete_entry_duplicate_path(tmp_path):
    """_should_delete_entry must return True when the path is already in already_seen_files."""
    class Config:
        download_dir = str(tmp_path)
        db_file = "test.db"
        basedir = str(tmp_path)

    with GarminDownloaderDB(Config()) as db:
        test_file = tmp_path / "activity.fit"
        test_file.write_text("data")
        file_path = str(test_file)

        already_seen = {(file_path, "fit")}
        assert db._should_delete_entry(file_path, "fit", already_seen) is True


def test_should_delete_entry_first_time_seen(tmp_path):
    """_should_delete_entry must return False when the file exists and has not been seen yet."""
    class Config:
        download_dir = str(tmp_path)
        db_file = "test.db"
        basedir = str(tmp_path)

    with GarminDownloaderDB(Config()) as db:
        test_file = tmp_path / "activity.fit"
        test_file.write_text("data")

        assert db._should_delete_entry(str(test_file), "fit", set()) is False


def test_save_activity_with_sql_injection_in_name(db):
    """Activity names containing SQL special characters must be stored and retrieved correctly."""
    dangerous_name = "Run ' OR '1'='1"
    db.save_activity_to_db("666", "fit", dangerous_name, "2026", "path", "running", 1, 0)

    cursor = db.conn.cursor()
    cursor.execute("SELECT name FROM activities WHERE activity_id = '666'")
    assert cursor.fetchone()[0] == dangerous_name
