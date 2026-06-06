import os
from unittest.mock import MagicMock, patch, call
from migration import migrate_filename_template, migrate_file_structure

def test_migrate_file_structure_reorder(mock_config, mocker, tmp_path):
    db = MagicMock()
    old_rel_path = os.path.join("running", "activity.fit")
    db.get_all_activities.return_value = [
        ("201", "fit", "activity", "2026-02-01 12:00:00", old_rel_path, "running", 1, 0)
    ]
    
    mock_config.download_dir = str(tmp_path)
    mock_config.subfolder_per_format = True
    mock_config.subfolder_per_activitytype = True
    
    old_full_dir = tmp_path / "running"
    old_full_dir.mkdir(parents=True, exist_ok=True)
    old_file_path = old_full_dir / "activity.fit"
    old_file_path.write_text("binary")
    
    migrate_file_structure(db, mock_config)
    
    expected_new_path = tmp_path / "fit" / "running" / "activity.fit"
    assert expected_new_path.exists()
    
    expected_rel_path = os.path.join("fit", "running", "activity.fit")
    db.update_activity_file_path.assert_called_once_with("201", expected_rel_path, "fit")


def test_migration_skips_if_file_missing(mock_config, caplog):
    db = MagicMock()
    db.get_all_activities.return_value = [
        ("404", "fit", "Ghost Run", "2026-05-01 00:00:00", "running/non_existent.fit", "running", 1, 0)
    ]
    mock_config.download_dir = "/tmp/fake_dir"
    
    migrate_filename_template(db, mock_config)
    
    assert db.update_activity_file_path.call_count == 0


def test_migrate_filename_template_success(mock_config, mocker, tmp_path):
    db = MagicMock()
    db.get_all_activities.return_value = [
        ("101", "fit", "Old_Name_1", "2026-01-01 10:00:00", "running/Old_Name_1.fit", "running", 1, 0),
        ("102", "fit", "Old_Name_2", "2026-01-02 11:00:00", "cycling/Old_Name_2.fit", "cycling", 2, 0)
    ]
    
    mock_config.download_dir = str(tmp_path)
    mock_config.filename_template = "{activityStartDate}_{activityName}"
    
    run_dir = tmp_path / "running"
    run_dir.mkdir(parents=True, exist_ok=True)
    old_run_file = run_dir / "Old_Name_1.fit"
    old_run_file.write_text("data")

    cycle_dir = tmp_path / "cycling"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    old_cycle_file = cycle_dir / "Old_Name_2.fit"
    old_cycle_file.write_text("data")
    
    mocker.patch("migration.generate_filename", side_effect=[
        "2026-01-01_Morning Run.fit", 
        "2026-01-02_Lunch Ride.fit"
    ])
    
    migrate_filename_template(db, mock_config)
    
    new_run_file = run_dir / "2026-01-01_Morning Run.fit"
    new_cycle_file = cycle_dir / "2026-01-02_Lunch Ride.fit"
    
    assert new_run_file.exists()
    assert new_cycle_file.exists()
    
    expected_calls = [
        call("101", "running/2026-01-01_Morning Run.fit", "fit"),
        call("102", "cycling/2026-01-02_Lunch Ride.fit", "fit")
    ]
    db.update_activity_file_path.assert_has_calls(expected_calls, any_order=True)


