from dataclasses import dataclass
import os
from dotenv import load_dotenv

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
    # Optional fields that can be set via environment variables, but are not required
    user_email: str | None = None
    user_password: str | None = None
    max_activities_to_download: int = 1000  # Garmin Connect API allows to download max 1000 activities per request

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
                f"max_activities_to_download={self.max_activities_to_download})"
        )

    @classmethod
    def from_env(cls) -> tuple["GarminDownloaderConfig", list[str]]:
        load_dotenv()
        errors = []

        download_dir = os.getenv("DOWNLOAD_DIR")
        if not download_dir:
            errors.append("DOWNLOAD_DIR is required")

        download_format = os.getenv("DOWNLOAD_FORMAT", "fit").lower()
        if download_format not in ["fit", "tcx", "both"]:
            errors.append(f"DOWNLOAD_FORMAT must be 'fit', 'tcx', or 'both', got '{download_format}'")

        limit_activities_str = os.getenv("LIMIT_ACTIVITIES", "5")
        limit_activities = 5
        try:
            limit_activities = int(limit_activities_str)
            if limit_activities < 1:
                errors.append(f"LIMIT_ACTIVITIES must be >= 1, got {limit_activities}")
                limit_activities = 5
        except ValueError:
            errors.append(f"LIMIT_ACTIVITIES must be an integer, got '{limit_activities_str}'")

        if errors:
            return None, errors

        return cls(
            user_email=os.getenv("USER_EMAIL"),
            user_password=os.getenv("USER_PASSWORD"),
            download_dir=download_dir,
            db_file=os.getenv("DB_FILE", "garmin_activities.db"),
            limit_activities=limit_activities,
            subfolder_per_activitytype=os.getenv("SUBFOLDER_PER_ACTIVITYTYPE", "true").lower() == "true",
            filename_template=os.getenv("FILENAME_TEMPLATE", "{activityId}"),
            rename_existing_files=os.getenv("RENAME_EXISTING_FILES", "false").lower() == "true",
            download_format=download_format,
            subfolder_per_format=os.getenv("SUBFOLDER_PER_FORMAT", "false").lower() == "true",
            reorder_existing_filestructure=os.getenv("REORDER_EXISTING_FILESTRUCTURE", "false").lower() == "true",
        ),[]