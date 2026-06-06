import io
import zipfile
from downloader import download_activities, download_activity_by_id, write_activity_package_to_file
from unittest.mock import MagicMock, call

def test_download_activities_skips_existing(mock_config, mocker):
    """Tests that the function skips activities that are already present in the database."""
    garmin_service = MagicMock()
    db = MagicMock()
    
    mock_config.limit_activities = 1
    mock_config.download_format = "fit"
    
    activity = {
        'activityId': '123',
        'activityName': 'Morning Run',
        'startTimeLocal': '2026-06-01 08:00:00'
    }
    garmin_service.get_activities.return_value = [activity]
    db.is_activity_saved.return_value = True
    
    mock_download_by_id = mocker.patch('downloader.download_activity_by_id')
    download_activities(garmin_service, db, mock_config)
    
    db.is_activity_saved.assert_called_with('123', 'fit')
    mock_download_by_id.assert_not_called()


def test_download_activities_downloads_new(mock_config, mocker):
    """Tests that new activities are downloaded and written if not in DB."""
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
    db.is_activity_saved.return_value = False
    
    mock_package = {"fit": b"data"}
    mocker.patch('downloader.download_activity_by_id', return_value=mock_package)
    mock_writer = mocker.patch('downloader.write_activity_package_to_file', return_value=1)
    
    download_activities(garmin_service, db, mock_config)
    mock_writer.assert_called_once_with(activity, mock_package, db, mock_config)


def test_download_activities_pagination(mock_config):
    """Tests that the function requests activities in blocks (pagination)."""
    garmin_service = MagicMock()
    db = MagicMock()
    
    mock_config.limit_activities = 15
    mock_config.max_activities_to_download = 10
    
    garmin_service.get_activities.side_effect = [
        [{'activityId': str(i), 'startTimeLocal': '...'} for i in range(10)],
        [{'activityId': str(i), 'startTimeLocal': '...'} for i in range(10, 15)]
    ]
    
    db.is_activity_saved.return_value = True
    download_activities(garmin_service, db, mock_config)
    
    expected_calls = [call(0, 10), call(10, 5)]
    garmin_service.get_activities.assert_has_calls(expected_calls)

def test_write_activity_package_to_file_success(mock_config, tmp_path):
    """Verifies the full flow from data package to database entry and disk storage."""
    db = MagicMock()
    db.is_activity_saved.return_value = False
    
    mock_config.download_dir = str(tmp_path)
    mock_config.subfolder_per_activitytype = True
    
    activity = {
        "activityId": "999",
        "activityName": "Morning Run",
        "startTimeLocal": "2026-06-01 07:00:00",
        "activityType": {"typeKey": "running"}
    }
    package = {"fit": b"dummy-fit-data"}

    saved_count = write_activity_package_to_file(activity, package, db, mock_config)
    
    assert saved_count == 1
    db.save_activity_to_db.assert_called_once()
    
    expected_path = tmp_path / "running" / "2026-06-01_Morning Run.fit"
    assert expected_path.exists()

def test_download_activity_zip_handling(mock_config):
    """Tests if .fit files are correctly extracted from a Garmin API ZIP response."""
    garmin_service = MagicMock()
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "a") as zf:
        zf.writestr("activity_123.fit", b"fit-binary-content")
    zip_data = zip_buffer.getvalue()
    
    garmin_service.download_activity.return_value = zip_data
    mock_config.download_format = "fit"

    package = download_activity_by_id(garmin_service, "123", mock_config)
    assert "fit" in package
    assert package["fit"] == b"fit-binary-content"
