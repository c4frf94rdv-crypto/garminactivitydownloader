from dataclasses import dataclass, field
import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Downloading more often than this risks running into the Garmin Connect rate limits
RECOMMENDED_MIN_DOWNLOADINTERVAL = 3600


def _getenv(name, default=None):
    """Returns the environment variable or the default if it is unset, empty, or whitespace-only.

    Unlike os.getenv, an empty value (e.g. "BASEDIR=" in the .env file) falls back to the default
    instead of returning an empty string.
    """
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _getenv_bool(name, default):
    """Reads a boolean environment variable; invalid values log a warning and fall back to the default."""
    raw = _getenv(name)
    if raw is None:
        return default
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    logger.warning(f"{name} must be 'true' or 'false', got '{raw}'. Using default '{str(default).lower()}'.")
    return default

@dataclass
class GarminDownloaderConfig:
    download_dir: str
    db_file: str
    limit_activities: int
    subfolder_per_activitytype: bool
    filename_template: str
    rename_existing_files: bool
    download_format: str
    subfolder_per_format: bool
    reorder_existing_filestructure: bool
    use_parent_activity_type: bool = False
    # Optional fields that can be set via environment variables, but are not required
    user_email: str | None = None
    user_password: str | None = None
    max_activities_to_download: int = 1000  # Garmin Connect API allows to download max 1000 activities per request
    dockermode: bool = True  # Default to True, assuming most users will run in Docker
    downloadinterval: int = 86400  # Default to 24 hours in seconds
    schedule_time: str | None = None  # Optional fixed start time, e.g. "18:00"
    basedir: str = field(default_factory=lambda: os.path.join(os.getcwd(), "data"))

    def __repr__(self) -> str:
        # Mask sensitive fields in output
        return (f"GarminDownloaderConfig("
                f"user_email='***', "
                f"user_password='***', "
                f"download_dir='{self.download_dir}', "
                f"db_file='{self.db_file}', "
                f"limit_activities={self.limit_activities}, "
                f"subfolder_per_activitytype={self.subfolder_per_activitytype}, "
                f"filename_template='{self.filename_template}', "
                f"rename_existing_files={self.rename_existing_files}, "
                f"download_format='{self.download_format}', "
                f"subfolder_per_format={self.subfolder_per_format}, "
                f"reorder_existing_filestructure={self.reorder_existing_filestructure}, "
                f"use_parent_activity_type={self.use_parent_activity_type}, "
                f"max_activities_to_download={self.max_activities_to_download}, "
                f"dockermode={self.dockermode}, "
                f"downloadinterval={self.downloadinterval}, "
                f"schedule_time={self.schedule_time}, "
                f"basedir={self.basedir}"
        )

    @classmethod
    def from_env(cls) -> tuple["GarminDownloaderConfig", list[str]]:
        load_dotenv()
        errors = []

        download_dir = _getenv("DOWNLOAD_DIR")
        if not download_dir:
            errors.append("DOWNLOAD_DIR is required")

        download_format = _getenv("DOWNLOAD_FORMAT", "fit").lower()
        if download_format not in ["fit", "tcx", "both"]:
            errors.append(f"DOWNLOAD_FORMAT must be 'fit', 'tcx', or 'both', got '{download_format}'")

        limit_activities_str = _getenv("LIMIT_ACTIVITIES", "5")
        limit_activities = 5
        try:
            limit_activities = int(limit_activities_str)
            if limit_activities < 1:
                errors.append(f"LIMIT_ACTIVITIES must be >= 1, got {limit_activities}")
                limit_activities = 5
        except ValueError:
            errors.append(f"LIMIT_ACTIVITIES must be an integer, got '{limit_activities_str}'")

        downloadinterval_str = _getenv("DOWNLOADINTERVAL", "86400")
        downloadinterval = 86400
        try:
            downloadinterval = int(downloadinterval_str)
            if downloadinterval < 1:
                errors.append(f"DOWNLOADINTERVAL must be >= 1, got {downloadinterval}")
                downloadinterval = 86400
            elif downloadinterval < RECOMMENDED_MIN_DOWNLOADINTERVAL:
                logger.warning(f"DOWNLOADINTERVAL is set to {downloadinterval} seconds. "
                               f"Garmin Connect enforces rate limits — intervals below {RECOMMENDED_MIN_DOWNLOADINTERVAL} seconds are not recommended.")
        except ValueError:
            errors.append(f"DOWNLOADINTERVAL must be an integer, got '{downloadinterval_str}'")

        schedule_time_str = _getenv("SCHEDULE_TIME", "")
        schedule_time = None
        if schedule_time_str:
            try:
                time_parts = schedule_time_str.split(":")
                if len(time_parts) != 2:
                    raise ValueError()
                h, m = int(time_parts[0]), int(time_parts[1])
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    raise ValueError()
                schedule_time = schedule_time_str
            except ValueError:
                errors.append(f"SCHEDULE_TIME must be in HH:MM format (e.g. 18:00), got '{schedule_time_str}'")

        if errors:
            return None, errors

        return cls(
            user_email=_getenv("USER_EMAIL"),
            user_password=_getenv("USER_PASSWORD"),
            download_dir=download_dir,
            db_file=_getenv("DB_FILE", "garmin_activities.db"),
            limit_activities=limit_activities,
            subfolder_per_activitytype=_getenv_bool("SUBFOLDER_PER_ACTIVITYTYPE", True),
            filename_template=_getenv("FILENAME_TEMPLATE", "{activityId}"),
            rename_existing_files=_getenv_bool("RENAME_EXISTING_FILES", False),
            download_format=download_format,
            subfolder_per_format=_getenv_bool("SUBFOLDER_PER_FORMAT", False),
            reorder_existing_filestructure=_getenv_bool("REORDER_EXISTING_FILESTRUCTURE", False),
            use_parent_activity_type=_getenv_bool("USE_PARENT_ACTIVITY_TYPE", False),
            dockermode=_getenv_bool("DOCKERMODE", True),
            downloadinterval=downloadinterval,
            schedule_time=schedule_time,
            basedir=_getenv("BASEDIR", os.path.join(os.getcwd(), "data"))
        ),[]