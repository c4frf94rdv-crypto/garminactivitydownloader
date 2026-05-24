from dataclasses import dataclass
import os
from dotenv import load_dotenv

@dataclass
class GarminDownloaderConfig:
    user_email: str
    user_password: str
    download_dir: str
    db_file: str
    limit_activities: int
    subfolder_per_activitytype: bool
    filename_template: str
    rename_existing_files: bool
    download_format: str
    subfolder_per_format: bool
    reorder_existing_filestructure: bool
    max_activities_to_download: int = 1000  # Garmin Connect API allows to download max 1000 activities per request

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

        if errors:
            return None, errors

        return cls(
            user_email=os.getenv("USER_EMAIL"),
            user_password=os.getenv("USER_PASSWORD"),
            download_dir=download_dir,
            db_file=os.getenv("DB_FILE", "garmin_activities.db"),
            limit_activities=int(os.getenv("LIMIT_ACTIVITIES", "5")),
            subfolder_per_activitytype=os.getenv("SUBFOLDER_PER_ACTIVITYTYPE", "true").lower() == "true",
            filename_template=os.getenv("FILENAME_TEMPLATE", "{activityId}"),
            rename_existing_files=os.getenv("RENAME_EXISTING_FILES", "false").lower() == "true",
            download_format=download_format,
            subfolder_per_format=os.getenv("SUBFOLDER_PER_FORMAT", "false").lower() == "true",
            reorder_existing_filestructure=os.getenv("REORDER_EXISTING_FILESTRUCTURE", "false").lower() == "true",
        ),[]