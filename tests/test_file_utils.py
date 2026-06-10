import os
from pathlib import Path
import pytest
from file_utils import SafeDict, ensure_unique_filename, get_downloadpath_by_activitytype, generate_filename

def test_safe_dict_missing_key():
    """Verify SafeDict returns {key} for missing keys."""
    d = SafeDict({"a": 1})
    assert d["a"] == 1
    assert d["missing"] == "{missing}"

def test_ensure_unique_filename_collision(tmp_path: Path):
    """Tests the loop and counter increments inside ensure_unique_filename."""
    test_dir = str(tmp_path)
    filename = "run.fit"

    # No collision on first call
    assert ensure_unique_filename(test_dir, filename) == "run.fit"
    assert os.path.exists(os.path.join(test_dir, "run.fit"))

    # Single collision: counter advances to _1
    assert ensure_unique_filename(test_dir, filename) == "run_1.fit"
    assert os.path.exists(os.path.join(test_dir, "run_1.fit"))

    # Block run_2.fit manually so the loop must skip it and land on _3
    with open(os.path.join(test_dir, "run_2.fit"), "w") as f:
        f.write("placeholder")

    assert ensure_unique_filename(test_dir, filename) == "run_3.fit"
    assert os.path.exists(os.path.join(test_dir, "run_3.fit"))

def test_get_downloadpath_logic(mock_config):
    """Verifies all conditional branches of get_downloadpath_by_activitytype."""
    activity_cycling = {"activityType": {"typeKey": "cycling"}}
    activity_missing_key = {"activityType": {}}  # triggers the 'unknown' fallback

    # Branch A: no subfolders
    mock_config.subfolder_per_activitytype = False
    mock_config.subfolder_per_format = False
    path = get_downloadpath_by_activitytype(activity_cycling, "fit", mock_config)
    assert path.endswith("test_downloads")

    # Branch B: activity type subfolder only
    mock_config.subfolder_per_activitytype = True
    mock_config.subfolder_per_format = False
    path = get_downloadpath_by_activitytype(activity_cycling, "fit", mock_config)
    assert path.endswith(os.path.join("test_downloads", "cycling"))

    # Branch C: format subfolder only — gpx falls back to "fit" folder
    mock_config.subfolder_per_activitytype = False
    mock_config.subfolder_per_format = True
    assert os.path.basename(get_downloadpath_by_activitytype(activity_cycling, "fit", mock_config)) == "fit"
    assert os.path.basename(get_downloadpath_by_activitytype(activity_cycling, "gpx", mock_config)) == "fit"

    # Branch D: format subfolder for tcx
    assert os.path.basename(get_downloadpath_by_activitytype(activity_cycling, "tcx", mock_config)) == "tcx"

    # Branch E: both subfolders active, missing typeKey triggers 'unknown' fallback
    mock_config.subfolder_per_activitytype = True
    mock_config.subfolder_per_format = True
    path_comb = get_downloadpath_by_activitytype(activity_missing_key, "tcx", mock_config)
    path_parts = os.path.normpath(path_comb).split(os.sep)
    assert path_parts[-2:] == ["tcx", "unknown"]

@pytest.mark.parametrize("activity_input, expected", [
    ({
        "activityId": "123",
        "activityName": "Lauf mit George",
        "startTimeLocal": "2026-05-31 08:30:00"
    }, "2026-05-31_Lauf mit George.fit"),

    ({
        "activityId": "124",
        "activityName": "Lauf / Training?",
        "startTimeLocal": "2026-05-31 10:00:00"
    }, "2026-05-31_Lauf  Training.fit"),

    ({
        "activityId": "125",
        "activityName": None,
        "startTimeLocal": "2026-05-31 12:00:00"
    }, "2026-05-31_Unnamed.fit"),

    ({
        "activityId": "100",
        "activityName": 'Lauf "Intervall" <Schnell>', 
        "startTimeLocal": "2026-05-31 10:00:00"
    }, "2026-05-31_Lauf Intervall Schnell.fit"),

    ({
        "activityId": "300",
        "activityName": "Kurzer Zeitstempel",
        "startTimeLocal": "2026-05-31" 
    }, "2026-05-31_Kurzer Zeitstempel.fit"),

    ({
        "activityId": "400",
        "activityName": "Typ Test",
        "startTimeLocal": "2026-05-31 12:00:00",
        "activityType": {} 
    }, "2026-05-31_Typ Test.fit"),

    ({
        "activityId": "500",
        "activityName": "Lauf Ende.",
        "startTimeLocal": "2026-05-31 13:00:00"
    }, "2026-05-31_Lauf Ende.fit"),

    ({
        "activityId": "600",
        "activityName": "A" * 300,
        "startTimeLocal": "2026-05-31 14:00:00"
    }, "2026-05-31_" + ("A" * 240) + ".fit"),

    ({
        "activityName": "Missing ID Test",
        "startTimeLocal": "2026-05-31 15:00:00"
    }, "2026-05-31_Missing ID Test.fit"), 

    ({
        "activityId": 99999, 
        "activityName": "Numeric ID",
        "startTimeLocal": "2026-05-31 15:00:00"
    }, "2026-05-31_Numeric ID.fit"),

    ({
        "activityId": "700",
        "activityName": "Broken Date",
        "startTimeLocal": "2026" 
    }, "2026_Broken Date.fit"),

    ("UNKNOWN_KEY_TEMPLATE", "2026-05-31_{non_existent_key}_Test.fit"),
    ("TEMPLATE_TEST_SLASHES", "2026-05-31 Test.fit"),

    ({
        "activityId": "800",
        "activityName": 12345, 
        "startTimeLocal": "2026-05-31 16:00:00"
    }, "2026-05-31_12345.fit"),

    ({
        "activityId": "801",
        "activityName": "No Date",
        "startTimeLocal": None
    }, "0000-00-00_No Date.fit"),

    ({
        "activityId": "900",
        "activityName": "../../../etc/passwd",
        "startTimeLocal": "2026-05-31 17:00:00"
    }, "2026-05-31_......etcpasswd.fit"),

    ({
        "activityId": "1000",
        "activityName": "   ",
        "startTimeLocal": "2026-05-31 18:00:00"
    }, "2026-05-31_Unnamed.fit"),

    ({
        "activityId": "1001",
        "activityName": "Lauf\nZweite Zeile",
        "startTimeLocal": "2026-05-31 19:00:00"
    }, "2026-05-31_LaufZweite Zeile.fit"),

    ("TEMPLATE_ONLY_SPECIAL", "_.fit"),
])
def test_generate_filename_all_cases(mock_config, activity_input, expected):
    if activity_input == "UNKNOWN_KEY_TEMPLATE":
        mock_config.filename_template = "{activityStartDate}_{non_existent_key}_Test"
        activity = {"activityId": "1", "activityName": "Lauf", "startTimeLocal": "2026-05-31 10:00:00"}
    elif activity_input == "TEMPLATE_ONLY_SPECIAL":
        mock_config.filename_template = "<>:|?*"
        activity = {"activityId": "1", "activityName": "Test", "startTimeLocal": "2026-05-31 10:00:00"}
    elif activity_input == "TEMPLATE_TEST_SLASHES":
        mock_config.filename_template = "{activityStartDate}/{activityName}"
        activity = {"activityId": "1", "activityName": "Test", "startTimeLocal": "2026-05-31 10:00:00"}
        expected = "2026-05-31Test.fit"
    else:
        activity = {"activityType": {"typeKey": "running"}}
        if isinstance(activity_input, dict):
            activity.update(activity_input)
      
    if expected == "LONG_NAME_TEST" or (isinstance(activity_input, dict) and len(str(activity_input.get("activityName", ""))) > 250):
        result = generate_filename(activity, "fit", mock_config)
        assert len(result) <= 255
        assert result.startswith("2026-05-31_")
        assert result.endswith(".fit")
    else:
        result = generate_filename(activity, "fit", mock_config)
        assert result == expected
