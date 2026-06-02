import pytest
from main import generate_filename, SafeDict
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