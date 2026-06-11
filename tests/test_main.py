import logging
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from config import GarminDownloaderConfig
from main import main, _next_scheduled_run, _wait_until_next_run, init_download_dir, rundownloader


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


def test_init_download_dir_creates_folder(tmp_path, mock_config):
    """init_download_dir must create the target folder if it does not exist."""
    mock_config.basedir = str(tmp_path)
    mock_config.download_dir = "activities"

    result = init_download_dir(mock_config)

    assert result == str(tmp_path / "activities")
    assert (tmp_path / "activities").is_dir()


def test_wait_until_next_run_without_schedule_time(mock_config, mocker, caplog):
    """Without SCHEDULE_TIME the next run is now + downloadinterval."""
    mock_config.schedule_time = None
    mock_config.downloadinterval = 3600

    fixed_now = datetime(2026, 6, 10, 12, 0, 0)
    mocker.patch("main.datetime", wraps=datetime)
    mocker.patch("main.datetime").now.return_value = fixed_now
    mock_sleep = mocker.patch("main.time.sleep")

    with caplog.at_level(logging.INFO, logger="main"):
        _wait_until_next_run(mock_config)

    assert "2026-06-10 13:00:00" in caplog.text
    mock_sleep.assert_called_once()
    sleep_seconds = mock_sleep.call_args[0][0]
    assert 3590 <= sleep_seconds <= 3600


def test_wait_until_next_run_clamps_negative_sleep(mock_config, mocker):
    """If next_run has already passed by the time sleep is called, the duration must be clamped to 0 instead of raising ValueError."""
    mock_config.schedule_time = None
    mock_config.downloadinterval = 1

    # First now() computes next_run, second now() is already past it
    mock_datetime = mocker.patch("main.datetime")
    mock_datetime.now.side_effect = [
        datetime(2026, 6, 10, 12, 0, 0),
        datetime(2026, 6, 10, 12, 0, 5),
    ]
    mock_sleep = mocker.patch("main.time.sleep")

    _wait_until_next_run(mock_config)

    mock_sleep.assert_called_once_with(0.0)


def test_wait_until_next_run_with_schedule_time(mock_config, mocker, caplog):
    """With SCHEDULE_TIME the logged next run matches the schedule anchor."""
    mock_config.schedule_time = "18:00"
    mock_config.downloadinterval = 86400

    fixed_now = datetime(2026, 6, 10, 9, 0, 0)
    mocker.patch("main.datetime").now.return_value = fixed_now
    mock_sleep = mocker.patch("main.time.sleep")

    with caplog.at_level(logging.INFO, logger="main"):
        _wait_until_next_run(mock_config)

    assert "2026-06-10 18:00:00" in caplog.text
    mock_sleep.assert_called_once()


def test_rundownloader_calls_download_and_migrations(mock_config, tmp_path, mocker):
    """rundownloader must call migrate and download_activities when flags are set."""
    mock_config.basedir = str(tmp_path)
    mock_config.download_dir = "activities"
    mock_config.rename_existing_files = True
    mock_config.reorder_existing_filestructure = True

    mocker.patch("main.init_garmin_client", return_value=MagicMock())
    mock_migrate_name = mocker.patch("main.migrate_filename_template")
    mock_migrate_struct = mocker.patch("main.migrate_file_structure")
    mock_download = mocker.patch("main.download_activities")

    rundownloader(mock_config)

    mock_migrate_name.assert_called_once()
    mock_migrate_struct.assert_called_once()
    mock_download.assert_called_once()


def test_rundownloader_skips_migrations_when_disabled(mock_config, tmp_path, mocker):
    """rundownloader must not call migrate functions when flags are False."""
    mock_config.basedir = str(tmp_path)
    mock_config.download_dir = "activities"
    mock_config.rename_existing_files = False
    mock_config.reorder_existing_filestructure = False

    mocker.patch("main.init_garmin_client", return_value=MagicMock())
    mock_migrate_name = mocker.patch("main.migrate_filename_template")
    mock_migrate_struct = mocker.patch("main.migrate_file_structure")
    mocker.patch("main.download_activities")

    rundownloader(mock_config)

    mock_migrate_name.assert_not_called()
    mock_migrate_struct.assert_not_called()


def test_main_docker_loop_logs_exception_and_continues(mock_config, tmp_path, mocker, caplog):
    """Exceptions in a Docker loop iteration must be logged, not crash the process."""
    mock_config.dockermode = True
    mock_config.basedir = str(tmp_path)

    class _StopTest(BaseException):
        pass

    call_count = 0

    def fake_rundownloader(_):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("Garmin API unavailable")
        if call_count == 3:
            raise _StopTest  # BaseException — not caught by except Exception in main()

    mocker.patch.object(GarminDownloaderConfig, "from_env", return_value=(mock_config, []))
    mocker.patch("main.rundownloader", side_effect=fake_rundownloader)
    mocker.patch("main._wait_until_next_run")

    with caplog.at_level(logging.ERROR, logger="main"):
        try:
            main()
        except _StopTest:
            pass

    assert "Garmin API unavailable" in caplog.text


def test_main_runs_once_when_dockermode_false(mock_config, tmp_path, mocker, caplog):
    """With DOCKERMODE=false the program must run exactly one download and then exit."""
    mock_config.dockermode = False
    mock_config.basedir = str(tmp_path)

    mocker.patch.object(GarminDownloaderConfig, "from_env", return_value=(mock_config, []))
    mock_run = mocker.patch("main.rundownloader")

    main()

    mock_run.assert_called_once()


def test_main_outer_exception_is_logged(mocker, caplog):
    """An unexpected exception before config loads must be caught and logged."""
    mocker.patch.object(
        GarminDownloaderConfig, "from_env", side_effect=RuntimeError("unexpected crash")
    )

    with caplog.at_level(logging.ERROR, logger="main"):
        main()

    assert "unexpected crash" in caplog.text


def test_main_invalid_config(caplog):
    """Ensures the application terminates gracefully when configuration errors occur."""
    with patch.object(GarminDownloaderConfig, "from_env", return_value=(None, ["DOWNLOAD_DIR is required"])):
        main()
    
    assert "Invalid configuration" in caplog.text
    assert "DOWNLOAD_DIR is required" in caplog.text
 