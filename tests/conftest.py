import pytest
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