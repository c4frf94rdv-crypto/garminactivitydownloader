import logging
import os
from file_utils import generate_filename, get_downloadpath_by_activitytype
from database import GarminDownloaderDB
from file_utils import remove_empty_folders

logger = logging.getLogger(__name__)

def migrate_filename_template(db, config):
    logger.info("Migrating existing files to new filename template...")
    rows = db.get_all_activities()
    activitiesUpdated = 0
    for row in rows:
        activity, filetype, file_path = row_to_activity(row, config)
        new_file_path = os.path.join(os.path.dirname(file_path),  generate_filename(activity, filetype, config))
        if file_path != new_file_path:
            if not os.path.exists(file_path):
                logger.warning(f"File {file_path} could not be found on disk. Skipping migration for this entry.")
                continue
            relative_new_path = os.path.relpath(new_file_path, os.path.join(os.getcwd(), config.download_dir))
            db.update_activity_file_path(activity["activityId"], relative_new_path, filetype)
            os.rename(file_path, new_file_path)
            logger.debug(f"Renamed {file_path} to {new_file_path}")
            activitiesUpdated += 1
    logger.info(f"{activitiesUpdated} activities updated -> see log for move information")

def migrate_file_structure(db, config):
    """Migrates existing files to the new file structure based on activity type and format. This function retrieves all activities from the database, determines the new file path for each activity based on its type and format, and moves the file to the new location if it is not already there. After moving the file, it updates the file path in the database accordingly. Finally, it removes any empty folders left behind after the migration.
     :param db: An instance of the GarminDownloaderDB class used to access the database and update file paths.
     :param config: An instance of the GarminDownloaderConfig class containing the application configuration."""
    logger.info("Migrating existing files to new file structure...")
    rows = db.get_all_activities()
    filesMoved = 0
    for row in rows:
        activity, filetype, file_path = row_to_activity(row, config)
        new_download_dir = get_downloadpath_by_activitytype(activity, filetype, config)
        new_file_path = os.path.join(new_download_dir, os.path.basename(file_path))
        if file_path != new_file_path:
            os.makedirs(new_download_dir, exist_ok=True)
            relative_new_path = os.path.relpath(new_file_path, os.path.join(os.getcwd(), config.download_dir))
            db.update_activity_file_path(activity["activityId"], relative_new_path, filetype)
            os.rename(file_path, new_file_path)
            logger.debug(f"Moved {file_path} to {new_file_path}")
            filesMoved += 1
    logger.info(f"{filesMoved} activities moved -> see log for more information")
    remove_empty_folders(os.path.join(os.getcwd(), config.download_dir))

def row_to_activity(row, config):
    activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id = row
    activity = {
        "activityId": activity_id,
        "activityName": name or 'Unnamed Activity',
        "startTimeLocal": start_time,
        "activityType": {
            "typeKey": activity_type_key,
            "typeId": activity_type_id,
            "parentTypeId": activity_type_parent_id
        }
    }
    file_path = os.path.join(os.getcwd(), config.download_dir, file_path)
    return activity, filetype, file_path   
