import pytest
import os
from config import GarminDownloaderConfig

@pytest.fixture
def clean_env(mocker):
    """
    Fixture to clear environment variables and mock load_dotenv.
    This ensures tests are not affected by an actual .env file.
    """
    mocker.patch("config.load_dotenv")

    keys = [
        "DOWNLOAD_DIR", "DB_FILE", "LIMIT_ACTIVITIES",
        "SUBFOLDER_PER_ACTIVITYTYPE", "FILENAME_TEMPLATE",
        "RENAME_EXISTING_FILES", "DOWNLOAD_FORMAT",
        "SUBFOLDER_PER_FORMAT", "REORDER_EXISTING_FILESTRUCTURE",
        "USER_EMAIL", "USER_PASSWORD", "DOWNLOADINTERVAL", "SCHEDULE_TIME",
    ]
    for key in keys:
        if key in os.environ:
            del os.environ[key]
    yield

def test_config_from_env_success(clean_env):
    """
    Tests successful configuration loading when all required 
    environment variables are provided correctly.
    """
    os.environ["DOWNLOAD_DIR"] = "/path/to/downloads"
    os.environ["DOWNLOAD_FORMAT"] = "tcx"
    os.environ["LIMIT_ACTIVITIES"] = "10"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert len(errors) == 0
    assert config.download_dir == "/path/to/downloads"
    assert config.download_format == "tcx"
    assert config.limit_activities == 10
    # Check default value for db_file
    assert config.db_file == "garmin_activities.db"

def test_config_missing_required_fields(clean_env):
    """
    Verifies that missing mandatory environment variables 
    (like DOWNLOAD_DIR) are correctly identified as errors.
    """
    # Ensure the variable is definitely not there
    if "DOWNLOAD_DIR" in os.environ:
        del os.environ["DOWNLOAD_DIR"]
        
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config is None
    assert "DOWNLOAD_DIR is required" in errors

def test_config_invalid_format(clean_env):
    """
    Tests validation logic for the DOWNLOAD_FORMAT field.
    Only 'fit', 'tcx', or 'both' should be accepted.
    """
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["DOWNLOAD_FORMAT"] = "pdf"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config is None
    assert any("DOWNLOAD_FORMAT must be" in err for err in errors)

def test_config_invalid_limit_type(clean_env):
    """
    Ensures that non-integer values for LIMIT_ACTIVITIES 
    trigger a validation error.
    """
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["LIMIT_ACTIVITIES"] = "not-a-number"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert any("must be an integer" in err for err in errors)

def test_config_boolean_parsing(clean_env):
    """
    Tests if string-based environment variables are correctly 
    converted into boolean values.
    """
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["SUBFOLDER_PER_ACTIVITYTYPE"] = "false"
    os.environ["RENAME_EXISTING_FILES"] = "true"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config.subfolder_per_activitytype is False
    assert config.rename_existing_files is True

def test_config_repr_masking():
    """
    Confirms that the __repr__ method masks sensitive data 
    like email and password for logging security.
    """
    config = GarminDownloaderConfig(
        download_dir=".",
        db_file="test.db",
        limit_activities=5,
        subfolder_per_activitytype=True,
        filename_template="{activityId}",
        rename_existing_files=False,
        download_format="fit",
        subfolder_per_format=False,
        reorder_existing_filestructure=False,
        user_email="private@example.com",
        user_password="secret_password"
    )
    
    repr_str = repr(config)
    assert "user_email='***'" in repr_str
    assert "user_password='***'" in repr_str
    assert "private@example.com" not in repr_str
    assert "secret_password" not in repr_str

def test_config_invalid_limit_value_too_low(clean_env):
    """
    Ensures that if LIMIT_ACTIVITIES is less than 1, an error is added 
    and the config object is not created.
    """
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["LIMIT_ACTIVITIES"] = "0" # Boundary value
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config is None
    assert any("LIMIT_ACTIVITIES must be >= 1" in err for err in errors)

def test_config_negative_limit_value(clean_env):
    """
    Checks the behavior when a negative integer is provided for the limit.
    """
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["LIMIT_ACTIVITIES"] = "-50"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config is None
    assert any("LIMIT_ACTIVITIES must be >= 1" in err for err in errors)

def test_config_empty_download_dir_string(clean_env):
    """
    Tests if an empty string for DOWNLOAD_DIR is treated as an error, 
    even if the key exists in the environment.
    """
    os.environ["DOWNLOAD_DIR"] = ""
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config is None
    assert "DOWNLOAD_DIR is required" in errors

def test_config_case_sensitivity_format(clean_env):
    """
    Verifies that the download format is case-insensitive (e.g., 'FIT' becomes 'fit').
    """
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["DOWNLOAD_FORMAT"] = "FIT"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert len(errors) == 0
    assert config.download_format == "fit"

def test_config_multiple_errors(clean_env):
    """
    Checks if the validation logic captures multiple configuration 
    errors simultaneously.
    """
    # No DOWNLOAD_DIR set
    os.environ["DOWNLOAD_FORMAT"] = "invalid_format"
    os.environ["LIMIT_ACTIVITIES"] = "not_a_number"
    
    config, errors = GarminDownloaderConfig.from_env()
    
    assert config is None
    assert len(errors) >= 3
    assert any("DOWNLOAD_DIR is required" in err for err in errors)
    assert any("DOWNLOAD_FORMAT must be" in err for err in errors)
    assert any("LIMIT_ACTIVITIES must be an integer" in err for err in errors)

def test_config_invalid_downloadinterval_type(clean_env):
    """Non-integer DOWNLOADINTERVAL must produce a validation error."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["DOWNLOADINTERVAL"] = "daily"

    config, errors = GarminDownloaderConfig.from_env()

    assert config is None
    assert any("DOWNLOADINTERVAL must be an integer" in err for err in errors)


def test_config_invalid_downloadinterval_too_low(clean_env):
    """DOWNLOADINTERVAL below 1 must produce a validation error."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["DOWNLOADINTERVAL"] = "0"

    config, errors = GarminDownloaderConfig.from_env()

    assert config is None
    assert any("DOWNLOADINTERVAL must be >= 1" in err for err in errors)


def test_config_valid_schedule_time(clean_env):
    """A valid SCHEDULE_TIME is parsed and stored correctly."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["SCHEDULE_TIME"] = "18:00"

    config, errors = GarminDownloaderConfig.from_env()

    assert len(errors) == 0
    assert config.schedule_time == "18:00"


def test_config_invalid_schedule_time_format(clean_env):
    """SCHEDULE_TIME with wrong format must produce a validation error."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["SCHEDULE_TIME"] = "6pm"

    config, errors = GarminDownloaderConfig.from_env()

    assert config is None
    assert any("SCHEDULE_TIME must be in HH:MM format" in err for err in errors)


def test_config_invalid_schedule_time_out_of_range(clean_env):
    """SCHEDULE_TIME with out-of-range values must produce a validation error."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["SCHEDULE_TIME"] = "25:00"

    config, errors = GarminDownloaderConfig.from_env()

    assert config is None
    assert any("SCHEDULE_TIME must be in HH:MM format" in err for err in errors)


def test_config_schedule_time_not_set_defaults_to_none(clean_env):
    """When SCHEDULE_TIME is not set, schedule_time must default to None."""
    os.environ["DOWNLOAD_DIR"] = "."

    config, errors = GarminDownloaderConfig.from_env()

    assert len(errors) == 0
    assert config.schedule_time is None


def test_config_boolean_fallback_on_invalid_string(clean_env, caplog):
    """A boolean field with a value other than 'true'/'false' must log a warning and fall back to its default."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["SUBFOLDER_PER_ACTIVITYTYPE"] = "maybe"
    os.environ["RENAME_EXISTING_FILES"] = "YesPlease"

    config, errors = GarminDownloaderConfig.from_env()

    # Defaults: SUBFOLDER_PER_ACTIVITYTYPE=true, RENAME_EXISTING_FILES=false
    assert config.subfolder_per_activitytype is True
    assert config.rename_existing_files is False
    assert "SUBFOLDER_PER_ACTIVITYTYPE must be 'true' or 'false', got 'maybe'" in caplog.text
    assert "RENAME_EXISTING_FILES must be 'true' or 'false', got 'YesPlease'" in caplog.text


def test_config_boolean_accepts_case_and_whitespace(clean_env):
    """Boolean values with different casing or surrounding whitespace must be parsed correctly."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["SUBFOLDER_PER_FORMAT"] = " True "
    os.environ["DOCKERMODE"] = "FALSE"

    config, errors = GarminDownloaderConfig.from_env()

    assert config.subfolder_per_format is True
    assert config.dockermode is False


def test_config_empty_values_fall_back_to_defaults(clean_env):
    """Variables set to an empty string (e.g. 'BASEDIR=' in .env) must fall back to their defaults instead of producing empty paths."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["BASEDIR"] = ""
    os.environ["DB_FILE"] = "   "
    os.environ["FILENAME_TEMPLATE"] = ""
    os.environ["DOWNLOADINTERVAL"] = ""

    config, errors = GarminDownloaderConfig.from_env()

    assert errors == []
    assert config.basedir == os.path.join(os.getcwd(), "data")
    assert config.db_file == "garmin_activities.db"
    assert config.filename_template == "{activityId}"
    assert config.downloadinterval == 86400


def test_config_low_downloadinterval_logs_warning(clean_env, caplog):
    """A download interval below the recommended minimum is accepted but must log a rate limit warning."""
    os.environ["DOWNLOAD_DIR"] = "."
    os.environ["DOWNLOADINTERVAL"] = "60"

    config, errors = GarminDownloaderConfig.from_env()

    assert errors == []
    assert config.downloadinterval == 60
    assert "rate limits" in caplog.text