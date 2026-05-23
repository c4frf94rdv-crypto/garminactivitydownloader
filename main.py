import os
import io
import zipfile
from dotenv import load_dotenv
from garminconnect import Garmin
from database import fit_downloader_db
from pathvalidate import sanitize_filename
from garminservice import GarminService

load_dotenv()

# Load Configuration from environment variables
# ToDo move configuration loading to a separate function/class and add validation for required variables and correct formats
USER_EMAIL = os.getenv("USER_EMAIL")
USER_PASSWORD = os.getenv("USER_PASSWORD")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR")
DB_FILE = os.getenv("DB_FILE", "garmin_activities.db")
LIMIT_ACTIVITIES = int(os.getenv("LIMIT_ACTIVITIES", "5"))
SUBFOLDER_PER_ACTIVITYTYPE = os.getenv("SUBFOLDER_PER_ACTIVITYTYPE", "true").lower() == "true"
FILENAME_TEMPLATE = os.getenv("FILENAME_TEMPLATE", "{activityId}")
RENAME_EXISTING_FILES = os.getenv("RENAME_EXISTING_FILES", "false").lower() == "true"
DOWNLOAD_FORMAT = os.getenv("DOWNLOAD_FORMAT", "fit").lower()  # Options: "fit", "tcx", "both"
SUBFOLDER_PER_FORMAT = os.getenv("SUBFOLDER_PER_FORMAT", "false").lower() == "true"
REORDER_EXISTING_FILESTRUCTURE = os.getenv("REORDER_EXISTING_FILESTRUCTURE", "false").lower() == "true"
# Hardcoded constants
MAX_ACTIVITIES_TO_DOWNLOAD=1000             # Garmin Connect API allows to download max 1000 activities per request

def init_garmin_client():
    garmin_service = GarminService(USER_EMAIL, USER_PASSWORD)
    garmin_service.login()
    return garmin_service

def init_download_dir():
    download_dir = os.path.join(os.getcwd(), DOWNLOAD_DIR)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def get_downloadpath_by_activitytype(activity, filetype):
    download_dir = os.path.join(os.getcwd(), DOWNLOAD_DIR)

    if SUBFOLDER_PER_FORMAT:
        if filetype in ["fit"]:
            download_dir = os.path.join(download_dir, "fit")
        if filetype in ["tcx"]:
            download_dir = os.path.join(download_dir, "tcx")

    if SUBFOLDER_PER_ACTIVITYTYPE:
        act_type_dict = activity.get("activityType", {})
        activity_type = act_type_dict.get("typeKey", "unknown")
        download_dir = os.path.join(download_dir, activity_type)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def generate_filename(activity, filetype) -> str:

    act_type_dict = activity.get("activityType", {})
    activity_type = act_type_dict.get("typeKey", "unknown")
    startdate_and_time = activity.get('startTimeLocal', '0000-00-00T00:00:00')[:19].replace(" ", "_").replace(":", "-")
    startdate = startdate_and_time[:10]

    filename = FILENAME_TEMPLATE.format(activityId=activity['activityId'], 
                                        activityName=activity['activityName'], 
                                        activityStartDate=startdate, 
                                        activityStartDateTime=startdate_and_time,
                                        activityType=activity_type)
    filename = sanitize_filename(filename)
    filename = filename + f".{filetype}"
    return filename

def download_activities(garmin_service, db):
    print("Downloading activities...")

    total_downloaded = 0
    while total_downloaded < LIMIT_ACTIVITIES:
        blocksize = min(MAX_ACTIVITIES_TO_DOWNLOAD, LIMIT_ACTIVITIES - total_downloaded)
        if blocksize <= 0:
            break
        activities = garmin_service.get_activities(total_downloaded, blocksize)
        if len(activities) == 0:
            break
        for activity in activities:
            activity_package = download_activity_by_id(garmin_service, activity['activityId'])
            if activity_package:
                write_activity_package_to_file(activity, activity_package, db)
        total_downloaded += len(activities)

def download_activity_by_id(garmin_service, activity_id):
    if DOWNLOAD_FORMAT not in ["fit", "tcx", "both"]:
        print(f"Invalid DOWNLOAD_FORMAT: {DOWNLOAD_FORMAT}. Must be 'fit', 'tcx', or 'both'.")
        return
    
    activites_package = {}
    if DOWNLOAD_FORMAT in ["fit", "both"]:
        raw_bytes = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.ORIGINAL)
        # unzip if the downloaded file is a zip (some activities have multiple files, e.g. fit and tcx, and are delivered as zip)
        if raw_bytes.startswith(b'PK\x03\x04'): 
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                first_file = z.namelist()[0]
                activites_package["fit"] = z.read(first_file)
        else:
            activites_package["fit"] = raw_bytes
    if DOWNLOAD_FORMAT in ["tcx", "both"]:
        activites_package["tcx"] = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.TCX)

    return activites_package

def write_activity_package_to_file(activity, activites_package, db):
    for filetype, data in activites_package.items():
        if db.is_activity_saved(activity['activityId'], filetype):
            print(f" - {activity['activityName']} / {filetype} at {activity['startTimeLocal']} already downloaded, skipping.")
            continue
        try:    
            download_dir = get_downloadpath_by_activitytype(activity, filetype)
            file_path = build_unique_filepath(activity, download_dir, filetype)
            with open(file_path, "wb") as f:
                f.write(data)
            relative_file_path = os.path.relpath(file_path, os.path.join(os.getcwd(), DOWNLOAD_DIR))
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

def build_unique_filepath(activity, directory, filetype):
    filename = ensure_unique_filename(directory, generate_filename(activity, filetype))
    return os.path.join(directory, filename)

def row_to_activity(row):
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
    file_path = os.path.join(os.getcwd(), DOWNLOAD_DIR, file_path)
    return activity, filetype, file_path   


def migrate_filename_template(db):
    print("Migrating existing files to new filename template...")
    rows = db.get_all_activities()
    for row in rows:
        activity, filetype, file_path = row_to_activity(row)
        new_file_path = os.path.join(os.path.dirname(file_path), generate_filename(activity, filetype))
        if file_path != new_file_path:
            os.rename(file_path, new_file_path)
            db.update_activity_file_path(activity["activityId"], new_file_path, filetype)
            print(f"Renamed {file_path} to {new_file_path}")

def migrate_file_structure(db):
    print("Migrating existing files to new file structure...")
    rows = db.get_all_activities()
    for row in rows:
        activity, filetype, file_path = row_to_activity(row)
        new_download_dir = get_downloadpath_by_activitytype(activity, filetype)
        new_file_path = os.path.join(new_download_dir, generate_filename(activity, filetype))
        if file_path != new_file_path:
            os.makedirs(new_download_dir, exist_ok=True)
            os.rename(file_path, new_file_path)
            db.update_activity_file_path(activity["activityId"], new_file_path, filetype)
            print(f"Moved {file_path} to {new_file_path}")
    remove_empty_folders(os.path.join(os.getcwd(), DOWNLOAD_DIR))


def remove_empty_folders(path_to_check):
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
        #ToDo Move configuration loading to a separate function/class and add validation for required variables and correct formats
        if DOWNLOAD_FORMAT not in ["fit", "tcx", "both"]:
            print(f"Invalid DOWNLOAD_FORMAT: '{DOWNLOAD_FORMAT}'. Aborting.")
            return
        client = init_garmin_client()
        init_download_dir()
        db = fit_downloader_db(DOWNLOAD_DIR, DB_FILE)
        db.cleanup_orphaned_entries(DOWNLOAD_DIR)
        if RENAME_EXISTING_FILES:
            migrate_filename_template(db)
        if REORDER_EXISTING_FILESTRUCTURE:
            migrate_file_structure(db)
        download_activities(client, db)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":    
    main()
