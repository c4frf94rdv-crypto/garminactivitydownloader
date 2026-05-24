import os
import io
import zipfile
from garminconnect import Garmin
from database import GarminDownloaderDB
from pathvalidate import sanitize_filename
from garminservice import GarminService
from config import GarminDownloaderConfig

def init_garmin_client(config):
    garmin_service = GarminService(config.user_email, config.user_password)
    garmin_service.login()
    return garmin_service

def init_download_dir(config):
    download_dir = os.path.join(os.getcwd(), config.download_dir)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def get_downloadpath_by_activitytype(activity, filetype, config):
    download_dir = os.path.join(os.getcwd(), config.download_dir)

    if config.subfolder_per_format:
        if filetype in ["fit"]:
            download_dir = os.path.join(download_dir, "fit")
        if filetype in ["tcx"]:
            download_dir = os.path.join(download_dir, "tcx")

    if config.subfolder_per_activitytype:
        act_type_dict = activity.get("activityType", {})
        activity_type = act_type_dict.get("typeKey", "unknown")
        download_dir = os.path.join(download_dir, activity_type)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def generate_filename(activity, filetype, config) -> str:

    act_type_dict = activity.get("activityType", {})
    activity_type = act_type_dict.get("typeKey", "unknown")
    startdate_and_time = activity.get('startTimeLocal', '0000-00-00T00:00:00')[:19].replace(" ", "_").replace(":", "-")
    startdate = startdate_and_time[:10]

    filename = config.filename_template.format(activityId=activity['activityId'], 
                                             activityName=activity['activityName'], 
                                        activityStartDate=startdate, 
                                        activityStartDateTime=startdate_and_time,
                                        activityType=activity_type)
    filename = sanitize_filename(filename)
    filename = filename + f".{filetype}"
    return filename

def download_activities(garmin_service, db, config):
    print("Downloading activities...")

    total_downloaded = 0
    while total_downloaded < config.limit_activities:
        blocksize = min(config.max_activities_to_download, config.limit_activities - total_downloaded)
        if blocksize <= 0:
            break
        activities = garmin_service.get_activities(total_downloaded, blocksize)
        if len(activities) == 0:
            break
        for activity in activities:
            activity_package = download_activity_by_id(garmin_service, activity['activityId'], config)
            if activity_package:
                write_activity_package_to_file(activity, activity_package, db, config)
        total_downloaded += len(activities)

def download_activity_by_id(garmin_service, activity_id, config):    
    activites_package = {}
    if config.download_format in ["fit", "both"]:
        raw_bytes = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.ORIGINAL)
        # unzip if the downloaded file is a zip (some activities have multiple files, e.g. fit and tcx, and are delivered as zip)
        if raw_bytes.startswith(b'PK\x03\x04'): 
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                first_file = z.namelist()[0]
                activites_package["fit"] = z.read(first_file)
        else:
            activites_package["fit"] = raw_bytes
    if config.download_format in ["tcx", "both"]:
        activites_package["tcx"] = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.TCX)

    return activites_package

def write_activity_package_to_file(activity, activites_package, db, config):
    for filetype, data in activites_package.items():
        if db.is_activity_saved(activity['activityId'], filetype):
            print(f" - {activity['activityName']} / {filetype} at {activity['startTimeLocal']} already downloaded, skipping.")
            continue
        try:    
            download_dir = get_downloadpath_by_activitytype(activity, filetype, config)
            file_path = build_unique_filepath(activity, download_dir, filetype, config)
            with open(file_path, "wb") as f:
                f.write(data)
            relative_file_path = os.path.relpath(file_path, os.path.join(os.getcwd(), config.download_dir))
            db.save_activity_to_db(activity['activityId'], 
                                    filetype,
                                    activity['activityName'], 
                                    activity['startTimeLocal'], 
                                    relative_file_path,
                                    activity.get("activityType", {}).get("typeKey", "unknown"),
                                    activity.get("activityType", {}).get("typeId", 0),
                                    activity.get("activityType", {}).get("parentTypeId", 0))
            print(f"Activity saved: {activity['activityName']} at {activity['startTimeLocal']} as {filetype}")

        except Exception as e: 
            # ToDo: add logging 
            print(f"Error saving activity {activity['activityName']} at {activity['startTimeLocal']} as {filetype}: {e}")
            continue


def ensure_unique_filename(download_dir, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename

    while os.path.exists(os.path.join(download_dir, unique_filename)):
        unique_filename = f"{base}_{counter}{ext}"
        counter += 1

    return unique_filename

def build_unique_filepath(activity, directory, filetype, config):
    filename = ensure_unique_filename(directory, generate_filename(activity, filetype, config))
    return os.path.join(directory, filename)

def row_to_activity(row, config):
    activity_id, filetype, name, start_time, file_path, activity_type_key, activity_type_id, activity_type_parent_id = row
    activity = {
        "activityId": activity_id,
        "activityName": name,
        "startTimeLocal": start_time,
        "activityType": {
            "typeKey": activity_type_key,
            "typeId": activity_type_id,
            "parentTypeId": activity_type_parent_id
        }
    }
    file_path = os.path.join(os.getcwd(), config.download_dir, file_path)
    return activity, filetype, file_path   


def migrate_filename_template(db, config):
    print("Migrating existing files to new filename template...")
    rows = db.get_all_activities()
    for row in rows:
        activity, filetype, file_path = row_to_activity(row, config)
        new_file_path = os.path.join(os.path.dirname(file_path),  generate_filename(activity, filetype, config))
        if file_path != new_file_path:
            os.rename(file_path, new_file_path)
            relative_new_path = os.path.relpath(new_file_path, os.path.join(os.getcwd(), config.download_dir))
            db.update_activity_file_path(activity["activityId"], relative_new_path, filetype)
            print(f"Renamed {file_path} to {new_file_path}")

def migrate_file_structure(db, config):
    """Migrates existing files to the new file structure based on activity type and format. This function retrieves all activities from the database, determines the new file path for each activity based on its type and format, and moves the file to the new location if it is not already there. After moving the file, it updates the file path in the database accordingly. Finally, it removes any empty folders left behind after the migration.
     :param db: An instance of the GarminDownloaderDB class used to access the database and update file paths.
     :param config: An instance of the GarminDownloaderConfig class containing the application configuration."""
    print("Migrating existing files to new file structure...")
    rows = db.get_all_activities()
    for row in rows:
        activity, filetype, file_path = row_to_activity(row, config)
        new_download_dir = get_downloadpath_by_activitytype(activity, filetype, config)
        new_file_path = os.path.join(new_download_dir, os.path.basename(file_path))
        if file_path != new_file_path:
            os.makedirs(new_download_dir, exist_ok=True)
            os.rename(file_path, new_file_path)
            relative_new_path = os.path.relpath(new_file_path, os.path.join(os.getcwd(), config.download_dir))
            db.update_activity_file_path(activity["activityId"], relative_new_path, filetype)
            print(f"Moved {file_path} to {new_file_path}")
    remove_empty_folders(os.path.join(os.getcwd(), config.download_dir))


def remove_empty_folders(path_to_check):
    """Removes empty folders in the given path. This function walks through the directory structure and deletes any folders that are empty. It continues to check for empty folders until no more can be deleted, ensuring that nested empty folders are also removed.
    :param path_to_check: The root path where the function should start checking for empty folders"""
    while True:
        folders_deleted_this_run = 0
        for root, dirs, files in os.walk(path_to_check, topdown=False):
            if root == path_to_check:
                continue
            try:
                if not os.listdir(root):
                    os.rmdir(root)
                    folders_deleted_this_run += 1
            except Exception:

                pass
        if folders_deleted_this_run == 0:
            break
            
def main():
    try:
        config, errors = GarminDownloaderConfig.from_env()
        if not config:
            print("Invalid configuration:")
            for error in errors:
                print(f" - {error}")
            return
        client = init_garmin_client(config)
        with GarminDownloaderDB(config) as db:
            db.cleanup_orphaned_entries()
            if config.rename_existing_files:
                migrate_filename_template(db, config)
            if config.reorder_existing_filestructure:
                migrate_file_structure(db, config)
            download_activities(client, db, config)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":    
    main()
