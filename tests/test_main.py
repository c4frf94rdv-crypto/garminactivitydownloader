from datetime import datetime
from unittest.mock import patch
from config import GarminDownloaderConfig
from main import main, _next_scheduled_run


def test_next_scheduled_run_same_day():
    """If schedule_time has not yet passed today, the next run is today."""
    after = datetime(2026, 6, 10, 9, 0, 0)   # 09:00
    result = _next_scheduled_run("18:00", 86400, after)
    assert result == datetime(2026, 6, 10, 18, 0, 0)


def test_next_scheduled_run_next_day():
    """If schedule_time has already passed today, the next run is tomorrow."""
    after = datetime(2026, 6, 10, 20, 0, 0)  # 20:00, past 18:00
    result = _next_scheduled_run("18:00", 86400, after)
    assert result == datetime(2026, 6, 11, 18, 0, 0)


def test_next_scheduled_run_advances_by_interval():
    """With a short interval the anchor is advanced until it is in the future."""
    # Simulate: anchor would be 10:00 today, but it's already 22:00.
    # Interval is 6h → anchors are 10:00, 16:00, 22:00 (past), 04:00 next day.
    after = datetime(2026, 6, 10, 21, 30, 0)  # 21:30
    result = _next_scheduled_run("10:00", 21600, after)   # every 6h
    # slots: 10:00, 16:00, 22:00 → 22:00 is the first slot after 21:30
    assert result == datetime(2026, 6, 10, 22, 0, 0)


def test_next_scheduled_run_exact_match_is_future():
    """A schedule_time equal to the current second must still yield the next occurrence."""
    after = datetime(2026, 6, 10, 18, 0, 0)  # exactly 18:00
    result = _next_scheduled_run("18:00", 86400, after)
    assert result == datetime(2026, 6, 11, 18, 0, 0)


def test_main_invalid_config(caplog):
    """Ensures the application terminates gracefully when configuration errors occur."""
    with patch.object(GarminDownloaderConfig, "from_env", return_value=(None, ["DOWNLOAD_DIR is required"])):
        main()
    
    assert "Invalid configuration" in caplog.text
    assert "DOWNLOAD_DIR is required" in caplog.text
 