from unittest.mock import patch
from config import GarminDownloaderConfig
from main import (
    main
)

def test_main_invalid_config(caplog):
    """Ensures the application terminates gracefully when configuration errors occur."""
    with patch.object(GarminDownloaderConfig, "from_env", return_value=(None, ["DOWNLOAD_DIR is required"])):
        main()
    
    assert "Invalid configuration" in caplog.text
    assert "DOWNLOAD_DIR is required" in caplog.text
 