import os
import io
import zipfile
import pytest
from unittest.mock import MagicMock, patch, call
from main import (
    get_downloadpath_by_activitytype, 
    ensure_unique_filename, 
    download_activity_by_id, 
    write_activity_package_to_file,
    main,
    download_activities,
    generate_filename,
    SafeDict,
    migrate_filename_template, migrate_file_structure
)
from config import GarminDownloaderConfig

@pytest.fixture
def mock_config():
    """Create a default configuration for tests."""
    return GarminDownloaderConfig(
        download_dir="test_downloads",
        db_file="test.db",
        limit_activities=5,
        subfolder_per_activitytype=True,
        filename_template="{activityStartDate}_{activityName}",
        rename_existing_files=False,
        download_format="fit",
        subfolder_per_format=False,
        reorder_existing_filestructure=False
    )

def test_safe_dict_missing_key():
    """Verify SafeDict returns {key} for missing keys."""
    d = SafeDict({"a": 1})
    assert d["a"] == 1
    assert d["missing"] == "{missing}"

import pytest
from main import generate_filename

@pytest.mark.parametrize("activity_input, expected", [
    # --- Existing & standard cases ---
    # Standard case: spaces are preserved
    ({
        "activityId": "123",
        "activityName": "Lauf mit George",
        "startTimeLocal": "2026-05-31 08:30:00"
    }, "2026-05-31_Lauf mit George.fit"),

    # Special chars: / and ? are removed, surrounding spaces remain (results in double spaces)
    ({
        "activityId": "124",
        "activityName": "Lauf / Training?",
        "startTimeLocal": "2026-05-31 10:00:00"
    }, "2026-05-31_Lauf  Training.fit"),

    # Fallback for None: when Garmin explicitly returns None
    ({
        "activityId": "125",
        "activityName": None,
        "startTimeLocal": "2026-05-31 12:00:00"
    }, "2026-05-31_Unnamed.fit"),

    # --- New stress tests & edge cases ---
    # Windows-illegal characters: removed by pathvalidate
    ({
        "activityId": "100",
        "activityName": 'Lauf "Intervall" <Schnell>', 
        "startTimeLocal": "2026-05-31 10:00:00"
    }, "2026-05-31_Lauf Intervall Schnell.fit"),

    # Timestamp formatting: too-short string ([:19] slice safety)
    ({
        "activityId": "300",
        "activityName": "Kurzer Zeitstempel",
        "startTimeLocal": "2026-05-31" 
    }, "2026-05-31_Kurzer Zeitstempel.fit"),

    # Empty type structure: ensure .get() on empty dicts does not crash
    ({
        "activityId": "400",
        "activityName": "Typ Test",
        "startTimeLocal": "2026-05-31 12:00:00",
        "activityType": {} 
    }, "2026-05-31_Typ Test.fit"),

    # Trailing dot: many filesystems trim dots before the extension
    ({
        "activityId": "500",
        "activityName": "Lauf Ende.",
        "startTimeLocal": "2026-05-31 13:00:00"
    }, "2026-05-31_Lauf Ende.fit"),

    # Extremely long name: tests the 255-character limit (important for QNAP/Linux)
    ({
        "activityId": "600",
        "activityName": "A" * 300,
        "startTimeLocal": "2026-05-31 14:00:00"
    }, "2026-05-31_" + ("A" * 240) + ".fit"),

    # --- Broken / incomplete data structures ---
    # Missing activityId (should raise KeyError or be handled gracefully)
    # Since your code uses activity['activityId'], this is a critical path
    ({
        "activityName": "Missing ID Test",
        "startTimeLocal": "2026-05-31 15:00:00"
        # activityId is missing entirely
    }, "2026-05-31_Missing ID Test.fit"), 

    # Type mismatch: ID is a number instead of a string
    ({
        "activityId": 99999, 
        "activityName": "Numeric ID",
        "startTimeLocal": "2026-05-31 15:00:00"
    }, "2026-05-31_Numeric ID.fit"),

    # Completely corrupt timestamp (shorter than 10 characters)
    ({
        "activityId": "700",
        "activityName": "Broken Date",
        "startTimeLocal": "2026" 
    }, "2026_Broken Date.fit"),

    # --- Configuration edge cases ---
    # Unknown placeholder in template (SafeDict test)
    # For example if the template was "{non_existent_key}_{activityName}"
    ("UNKNOWN_KEY_TEMPLATE", "2026-05-31_{non_existent_key}_Test.fit"),

    # Template special-chars overload (e.g. path separator in the template itself)
    ("TEMPLATE_TEST_SLASHES", "2026-05-31 Test.fit"),

    # --- Extreme data types & API inconsistencies ---
    # activityName is not a string (e.g. a number)
    ({
        "activityId": "800",
        "activityName": 12345, 
        "startTimeLocal": "2026-05-31 16:00:00"
    }, "2026-05-31_12345.fit"),

    # startTimeLocal is None (should become '0000-00-00' per code)
    ({
        "activityId": "801",
        "activityName": "No Date",
        "startTimeLocal": None
    }, "0000-00-00_No Date.fit"),

    # --- Path injection & directory traversal ---
    # Attempt to escape via activity name
    ({
        "activityId": "900",
        "activityName": "../../../etc/passwd",
        "startTimeLocal": "2026-05-31 17:00:00"
    }, "2026-05-31_......etcpasswd.fit"),

    # --- Whitespace & hidden characters ---
    # Only spaces as name (should trigger fallback to "Unnamed")
    ({
        "activityId": "1000",
        "activityName": "   ",
        "startTimeLocal": "2026-05-31 18:00:00"
    }, "2026-05-31_Unnamed.fit"),

    # Newline in the name (should be removed by sanitize_filename)
    ({
        "activityId": "1001",
        "activityName": "Lauf\nZweite Zeile",
        "startTimeLocal": "2026-05-31 19:00:00"
    }, "2026-05-31_LaufZweite Zeile.fit"),

    # --- Template stress ---
    # Extreme template containing only special characters
    ("TEMPLATE_ONLY_SPECIAL", "_.fit"),

])
def test_generate_filename_all_cases(mock_config, activity_input, expected):
    # 1. SPECIAL CASE: template manipulations
    if activity_input == "UNKNOWN_KEY_TEMPLATE":
        mock_config.filename_template = "{activityStartDate}_{non_existent_key}_Test"
        activity = {
            "activityId": "1", 
            "activityName": "Lauf", 
            "startTimeLocal": "2026-05-31 10:00:00"
        }
    elif activity_input == "TEMPLATE_ONLY_SPECIAL":
        mock_config.filename_template = "<>:|?*"
        activity = {
            "activityId": "1", 
            "activityName": "Test", 
            "startTimeLocal": "2026-05-31 10:00:00"
        }
    elif activity_input == "TEMPLATE_TEST_SLASHES":
        mock_config.filename_template = "{activityStartDate}/{activityName}"
        activity = {
            "activityId": "1", 
            "activityName": "Test", 
            "startTimeLocal": "2026-05-31 10:00:00"
        }
        # Expectation: pathvalidate removes the / from the filename
        expected = "2026-05-31Test.fit"
    
    # 2. STANDARD PREPARATION for all other cases
    else:
        activity = {"activityType": {"typeKey": "running"}}
        if isinstance(activity_input, dict):
            activity.update(activity_input)

    # 3. EXECUTION & ASSERTIONS
      
    # Case B: over-length test (flexible validation)
    if expected == "LONG_NAME_TEST" or (isinstance(activity_input, dict) and len(str(activity_input.get("activityName", ""))) > 250):
        result = generate_filename(activity, "fit", mock_config)
        assert len(result) <= 255
        assert result.startswith("2026-05-31_")
        assert result.endswith(".fit")

    # Case C: all regular cases
    else:
        result = generate_filename(activity, "fit", mock_config)
        assert result == expected

# --- Tests for directory logic and filesystem operations ---

def test_get_downloadpath_logic(mock_config):
    """Verifies that activities are placed in the correct folders based on configuration."""
    activity = {"activityType": {"typeKey": "cycling"}}
    
    # Scenario 1: Subfolders by activity type only
    mock_config.subfolder_per_activitytype = True
    mock_config.subfolder_per_format = False
    path = get_downloadpath_by_activitytype(activity, "fit", mock_config)
    assert path.endswith("cycling")

    # Scenario 2: Subfolders by format (FIT files should end up in the 'fit' folder)
    mock_config.subfolder_per_activitytype = False
    mock_config.subfolder_per_format = True
    path = get_downloadpath_by_activitytype(activity, "fit", mock_config)
    assert os.path.basename(path) == "fit"

    # Scenario 3: Combination (Format/Type) -> e.g., test_downloads/tcx/cycling
    mock_config.subfolder_per_activitytype = True
    mock_config.subfolder_per_format = True
    path = get_downloadpath_by_activitytype(activity, "tcx", mock_config)
    path_parts = os.path.normpath(path).split(os.sep)
    assert path_parts[-2:] == ["tcx", "cycling"]


def test_ensure_unique_filename_collision(tmp_path):
    """Ensures that existing files are not overwritten by generating unique names."""
    # Create a file that already exists
    test_dir = str(tmp_path)
    filename = "run.fit"
    with open(os.path.join(test_dir, filename), "w") as f:
        f.write("existing data")
    
    # The function should now return "run_1.fit"
    unique_name = ensure_unique_filename(test_dir, filename)
    assert unique_name == "run_1.fit"
    
    # Verify that the new file was created as a placeholder (atomic reservation)
    assert os.path.exists(os.path.join(test_dir, "run_1.fit"))


# --- Tests for API handling and ZIP extraction ---

def test_download_activity_zip_handling(mock_config):
    """Tests if .fit files are correctly extracted from a Garmin API ZIP response."""
    garmin_service = MagicMock()
    
    # Create a fake ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a") as zf:
        zf.writestr("activity_123.fit", b"fit-binary-content")
    zip_data = zip_buffer.getvalue()
    
    garmin_service.download_activity.return_value = zip_data
    mock_config.download_format = "fit"

    package = download_activity_by_id(garmin_service, "123", mock_config)
    
    assert "fit" in package
    assert package["fit"] == b"fit-binary-content"

# --- Tests for directory logic and filesystem operations ---

def test_get_downloadpath_logic(mock_config):
    """Verifies that activities are placed in the correct folders based on configuration."""
    activity = {"activityType": {"typeKey": "cycling"}}
    
    # Scenario 1: Subfolders by activity type only
    mock_config.subfolder_per_activitytype = True
    mock_config.subfolder_per_format = False
    path = get_downloadpath_by_activitytype(activity, "fit", mock_config)
    assert path.endswith("cycling")

    # Scenario 2: Subfolders by format (FIT files should end up in the 'fit' folder)
    mock_config.subfolder_per_activitytype = False
    mock_config.subfolder_per_format = True
    path = get_downloadpath_by_activitytype(activity, "fit", mock_config)
    assert os.path.basename(path) == "fit"

    # Scenario 3: Combination (Format/Type) -> e.g., test_downloads/tcx/cycling
    mock_config.subfolder_per_activitytype = True
    mock_config.subfolder_per_format = True
    path = get_downloadpath_by_activitytype(activity, "tcx", mock_config)
    path_parts = os.path.normpath(path).split(os.sep)
    assert path_parts[-2:] == ["tcx", "cycling"]


def test_ensure_unique_filename_collision(tmp_path):
    """Ensures that existing files are not overwritten by generating unique names."""
    # Create a file that already exists
    test_dir = str(tmp_path)
    filename = "run.fit"
    with open(os.path.join(test_dir, filename), "w") as f:
        f.write("existing data")
    
    # The function should now return "run_1.fit"
    unique_name = ensure_unique_filename(test_dir, filename)
    assert unique_name == "run_1.fit"
    
    # Verify that the new file was created as a placeholder (atomic reservation)
    assert os.path.exists(os.path.join(test_dir, "run_1.fit"))


# --- Tests for API handling and ZIP extraction ---

def test_download_activity_zip_handling(mock_config):
    """Tests if .fit files are correctly extracted from a Garmin API ZIP response."""
    garmin_service = MagicMock()
    
    # Create a fake ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a") as zf:
        zf.writestr("activity_123.fit", b"fit-binary-content")
    zip_data = zip_buffer.getvalue()
    
    garmin_service.download_activity.return_value = zip_data
    mock_config.download_format = "fit"

    package = download_activity_by_id(garmin_service, "123", mock_config)
    
    assert "fit" in package
    assert package["fit"] == b"fit-binary-content"


# --- Integration tests for the file writing process ---

def test_write_activity_package_to_file_success(mock_config, tmp_path):
    """Verifies the full flow from data package to database entry and disk storage."""
    db = MagicMock()
    db.is_activity_saved.return_value = False
    
    # Redirect download directory to a temporary test folder
    mock_config.download_dir = str(tmp_path)
    mock_config.subfolder_per_activitytype = True
    
    activity = {
        "activityId": "999",
        "activityName": "Morning Run",
        "startTimeLocal": "2026-06-01 07:00:00",
        "activityType": {"typeKey": "running"}
    }
    package = {"fit": b"dummy-fit-data"}

    # Execution
    saved_count = write_activity_package_to_file(activity, package, db, mock_config)
    
    # Assertions
    assert saved_count == 1
    db.save_activity_to_db.assert_called_once()
    
    # Path validation: tmp_path / running / 2026-06-01_Morning Run.fit
    expected_path = tmp_path / "running" / "2026-06-01_Morning Run.fit"
    assert expected_path.exists()


# --- Tests for the main entry point function ---

def test_main_invalid_config(caplog):
    """Ensures the application terminates gracefully when configuration errors occur."""
    # Patch from_env to simulate configuration errors
    with patch.object(GarminDownloaderConfig, "from_env", return_value=(None, ["DOWNLOAD_DIR is required"])):
        main()
    
    assert "Invalid configuration" in caplog.text
    assert "DOWNLOAD_DIR is required" in caplog.text

# --- Tests for download_activities logic ---

def test_download_activities_skips_existing(mock_config, mocker):
    """
    Tests that the function skips activities that are already present 
    in the database for the configured formats.
    """
    # 1. Setup mocks
    garmin_service = MagicMock()
    db = MagicMock()
    
    # Mock config to download only FIT
    mock_config.limit_activities = 1
    mock_config.download_format = "fit"
    
    # Mock activity returned by the service
    activity = {
        'activityId': '123',
        'activityName': 'Morning Run',
        'startTimeLocal': '2026-06-01 08:00:00'
    }
    garmin_service.get_activities.return_value = [activity]
    
    # 2. Scenario: Activity is already in DB
    db.is_activity_saved.return_value = True
    
    # Mock the download helper to ensure it's NOT called
    mock_download_by_id = mocker.patch('main.download_activity_by_id')
    
    # 3. Execution
    download_activities(garmin_service, db, mock_config)
    
    # 4. Assertions
    db.is_activity_saved.assert_called_with('123', 'fit')
    mock_download_by_id.assert_not_called()


def test_download_activities_downloads_new(mock_config, mocker):
    """
    Tests that new activities are downloaded and written to file 
    if they are not found in the database.
    """
    # 1. Setup mocks
    garmin_service = MagicMock()
    db = MagicMock()
    
    mock_config.limit_activities = 1
    mock_config.download_format = "fit"
    
    activity = {
        'activityId': '456',
        'activityName': 'Evening Walk',
        'startTimeLocal': '2026-06-02 18:00:00'
    }
    garmin_service.get_activities.return_value = [activity]
    
    # Activity is NOT in DB
    db.is_activity_saved.return_value = False
    
    # Mock helpers for downloading and writing
    mock_package = {"fit": b"data"}
    mocker.patch('main.download_activity_by_id', return_value=mock_package)
    mock_writer = mocker.patch('main.write_activity_package_to_file', return_value=1)
    
    # 2. Execution
    download_activities(garmin_service, db, mock_config)
    
    # 3. Assertions
    # Verify that the writer was called with the correct activity and package
    mock_writer.assert_called_once_with(activity, mock_package, db, mock_config)


def test_download_activities_pagination(mock_config):
    """
    Tests that the function correctly requests activities in blocks 
    (pagination) until the limit is reached.
    """
    garmin_service = MagicMock()
    db = MagicMock()
    
    # Mocking two pages of activities
    mock_config.limit_activities = 15
    mock_config.max_activities_to_download = 10
    
    # Return 10 activities on first call, 5 on second
    garmin_service.get_activities.side_effect = [
        [{'activityId': str(i), 'startTimeLocal': '...'} for i in range(10)],
        [{'activityId': str(i), 'startTimeLocal': '...'} for i in range(10, 15)]
    ]
    
    # Assume all are already downloaded to keep the test focused on pagination
    db.is_activity_saved.return_value = True
    
    # Execution
    download_activities(garmin_service, db, mock_config)
    
    # Assertions: Verify the calls to get_activities(start, limit)
    expected_calls = [
        call(0, 10), # First block
        call(10, 5)  # Remaining block to reach limit of 15
    ]
    garmin_service.get_activities.assert_has_calls(expected_calls)

# --- Tests for Migration Methods ---

# --- Updated Migration Tests with correct row unpacking ---

def test_migrate_filename_template_success(mock_config, mocker, tmp_path):
    """
    Tests that files are renamed correctly when the filename template changes.
    Matches the expected 8-column database row structure and 3-argument DB update call.
    """
    db = MagicMock()
    # Mocking activities with all 8 required fields:
    # activity_id, filetype, name, start_time, file_path, type_key, type_id, type_parent_id
    db.get_all_activities.return_value = [
        ("101", "fit", "Old_Name_1", "2026-01-01 10:00:00", "running/Old_Name_1.fit", "running", 1, 0),
        ("102", "fit", "Old_Name_2", "2026-01-02 11:00:00", "cycling/Old_Name_2.fit", "cycling", 2, 0)
    ]
    
    mock_config.download_dir = str(tmp_path)
    mock_config.filename_template = "{activityStartDate}_{activityName}"
    
    # 1. Create the 'old' running file on disk
    run_dir = tmp_path / "running"
    run_dir.mkdir(parents=True, exist_ok=True)
    old_run_file = run_dir / "Old_Name_1.fit"
    old_run_file.write_text("data")

    # 2. Create the 'old' cycling file on disk
    cycle_dir = tmp_path / "cycling"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    old_cycle_file = cycle_dir / "Old_Name_2.fit"
    old_cycle_file.write_text("data")
    
    # Mock generate_filename to return the expected new names
    mocker.patch("main.generate_filename", side_effect=[
        "2026-01-01_Morning Run.fit", 
        "2026-01-02_Lunch Ride.fit"
    ])
    
    # Execution
    migrate_filename_template(db, mock_config)
    
    # Assertions for disk changes
    new_run_file = run_dir / "2026-01-01_Morning Run.fit"
    new_cycle_file = cycle_dir / "2026-01-02_Lunch Ride.fit"
    
    assert new_run_file.exists()
    assert new_cycle_file.exists()
    
    # Assertions for DB updates (including 'fit' as the 3rd argument, ignoring call order)
    expected_calls = [
        call("101", "running/2026-01-01_Morning Run.fit", "fit"),
        call("102", "cycling/2026-01-02_Lunch Ride.fit", "fit")
    ]
    db.update_activity_file_path.assert_has_calls(expected_calls, any_order=True)

def test_migrate_file_structure_reorder(mock_config, mocker, tmp_path):
    """
    Tests moving files to a new folder structure, ensuring 8-column row compatibility,
    correct relative paths, and matching the 3-argument DB update call.
    """
    db = MagicMock()
    # Current state with 8 fields
    old_rel_path = os.path.join("running", "activity.fit")
    db.get_all_activities.return_value = [
        ("201", "fit", "activity", "2026-02-01 12:00:00", old_rel_path, "running", 1, 0)
    ]
    
    mock_config.download_dir = str(tmp_path)
    mock_config.subfolder_per_format = True
    mock_config.subfolder_per_activitytype = True
    
    # Create physical file in old structure
    old_full_dir = tmp_path / "running"
    old_full_dir.mkdir(parents=True, exist_ok=True)
    old_file_path = old_full_dir / "activity.fit"
    old_file_path.write_text("binary")
    
    # Execution
    migrate_file_structure(db, mock_config)
    
    # Assertions for disk changes (absolute paths required here)
    expected_new_path = tmp_path / "fit" / "running" / "activity.fit"
    assert expected_new_path.exists()
    
    # Assertions for DB updates (expects relative path and the 3rd 'filetype' argument)
    expected_rel_path = os.path.join("fit", "running", "activity.fit")
    db.update_activity_file_path.assert_called_once_with("201", expected_rel_path, "fit")

def test_migration_skips_if_file_missing(mock_config, caplog):
    """
    Ensures that migration handles cases where the DB entry exists but the 
    physical file is missing from the disk.
    """
    db = MagicMock()
    # Mocking a single activity with 8 columns, pointing to a non-existent path
    db.get_all_activities.return_value = [
        ("404", "fit", "Ghost Run", "2026-05-01 00:00:00", "running/non_existent.fit", "running", 1, 0)
    ]
    mock_config.download_dir = "/tmp/fake_dir"
    
    # Execution
    migrate_filename_template(db, mock_config)
    
    # Assertion: The script should not crash and skip the file since it does not exist on disk
    assert db.update_activity_file_path.call_count == 0