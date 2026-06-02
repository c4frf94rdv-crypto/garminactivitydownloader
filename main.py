import os
import io
import zipfile
import logging
from garminconnect import Garmin
from database import GarminDownloaderDB
from pathvalidate import sanitize_filename
from garminservice import GarminService
from config import GarminDownloaderConfig
from garminconnect.exceptions import GarminConnectAuthenticationError, GarminConnectConnectionError, GarminConnectTooManyRequestsError

logger = logging.getLogger(__name__)

class SafeDict(dict):
    
    def __missing__(self, key):
        """Return a default value if the key is not found in the dictionary."""        
        return "{"+key +"}"

def init_garmin_client(config):
    garmin_service = GarminService(config)
    garmin_service.login()
    return garmin_service

def init_download_dir(config):
    download_dir = os.path.join(os.getcwd(), config.download_dir)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def get_downloadpath_by_activitytype(activity, filetype, config):
    download_dir = os.path.join(os.getcwd(), config.download_dir)

    if config.subfolder_per_format:
        # gpx files are downloaded for activities that don't have a fit file available via the API, but since gpx files are basically just a fallback for fit files, it makes more sense to put them in the same folder as the fit files instead of putting them in a separate folder based on format
        if filetype in ["fit", "gpx"]:
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
    raw_start_time = activity.get('startTimeLocal') or '0000-00-00T00:00:00'
    startdate_and_time = raw_start_time[:19].replace(" ", "_").replace(":", "-")
    startdate = startdate_and_time[:10]
    activity_name_raw = activity.get('activityName', 'Unnamed') or 'Unnamed'
    if activity_name_raw is None or str(activity_name_raw).strip() == "":
        activity_name = "Unnamed"
    else:
        activity_name = str(activity_name_raw)

    activityId = activity.get('activityId', '0')
 
    data = {
        "activityId": activityId,
        "activityName": activity_name,
        "activityStartDate": startdate,
        "activityStartDateTime": startdate_and_time,
        "activityType": activity_type,
    }
    filename = config.filename_template.format_map(SafeDict(data))
    filename = filename[:240]
    filename = sanitize_filename(filename)
    if not filename.strip():
        filename = "_"
    return f"{filename}.{filetype}"

def download_activities(garmin_service, db, config):
    logger.info("Downloading activities...")

    total_downloaded = 0
    new_activities = 0
    while total_downloaded < config.limit_activities:
        blocksize = min(config.max_activities_to_download, config.limit_activities - total_downloaded)
        if blocksize <= 0:
            break
        activities = garmin_service.get_activities(total_downloaded, blocksize)
        if len(activities) == 0:
            break
        for activity in activities:
            activity['activityName'] = activity.get('activityName') or 'Unnamed Activity'            
            already_downloaded = True
            if config.download_format in ["fit", "both"]:
                already_downloaded = already_downloaded and db.is_activity_saved(activity['activityId'], "fit")
            if config.download_format in ["tcx", "both"]:
                already_downloaded = already_downloaded and db.is_activity_saved(activity['activityId'], "tcx")

            if already_downloaded:
                logger.debug(f" - {activity['activityName']} / fit at {activity['startTimeLocal']} already downloaded, skipping.")
                continue

            activity_package = download_activity_by_id(garmin_service, activity['activityId'], config)
            if activity_package:
                new_activities += write_activity_package_to_file(activity, activity_package, db, config)
        total_downloaded += len(activities)
    logger.info(f"Download finished, new activities downloaded {new_activities}")    

def download_activity_by_id(garmin_service, activity_id, config):    
    activites_package = {}
    if config.download_format in ["fit", "both"]:
        try:
            raw_bytes = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.ORIGINAL)
                # unzip if the downloaded file is a zip (some activities have multiple files, e.g. fit and tcx, and are delivered as zip)
            if raw_bytes.startswith(b'PK\x03\x04'): 
                try:
                    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                        fit_file = None
                        for filename in z.namelist():
                            if filename.lower().endswith('.fit'):
                                fit_file = filename
                                break
                        
                        if fit_file:
                            activites_package["fit"] = z.read(fit_file)               
                        else:
                            # fallback: if no .fit file is found, try to find a .gpx file in the zip and use it as fit data, this is not ideal but better than nothing and allows to still download the activity data for activities that don't have a .fit file available via the API
                            gpx_file = next((f for f in z.namelist() if f.lower().endswith('.gpx')), None)
                            if gpx_file:
                                activites_package["gpx"] = z.read(gpx_file)
                            else:
                                logger.warning(f"Activity {activity_id}: No .fit or .gpx file found in ZIP."
                                    f"Files in archive: {', '.join(z.namelist())}")
                except zipfile.BadZipFile:
                    logger.error(f"Activity {activity_id}: Invalid ZIP file from Garmin API")
            else:
                activites_package["fit"] = raw_bytes
        except GarminConnectConnectionError as e:
            logger.error(f"Activity {activity_id}: FIT Download failed, skipping!")
            return None
    if config.download_format in ["tcx", "both"]:
        try:
            activites_package["tcx"] = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.TCX)
        except GarminConnectConnectionError as e:
            logger.error(f"Activity {activity_id}: TCX download failed, skipping!")
    return activites_package

def write_activity_package_to_file(activity, activites_package, db, config) -> int:
    saved = 0;
    for filetype, data in activites_package.items():
        if db.is_activity_saved(activity['activityId'], filetype):
            logger.debug(f" - {activity['activityName']} / {filetype} at {activity['startTimeLocal']} already downloaded, skipping.")
            continue
        try:    
            download_dir = get_downloadpath_by_activitytype(activity, filetype, config)
            file_path = build_unique_filepath(activity, download_dir, filetype, config)
            try:
                with open(file_path, "wb") as f:
                    f.write(data)
            except Exception:
                # If writing fails, remove the reserved file to avoid orphaned empty files
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except Exception:
                    pass
                raise
            relative_file_path = os.path.relpath(file_path, os.path.join(os.getcwd(), config.download_dir))
            # Save activity info to database even if the file writing fails, in that case the orphaned database entry will be cleaned up in the next run of the script
            db.save_activity_to_db(activity['activityId'], 
                                    filetype,
                                    activity['activityName'], 
                                    activity['startTimeLocal'], 
                                    relative_file_path,
                                    activity.get("activityType", {}).get("typeKey", "unknown"),
                                    activity.get("activityType", {}).get("typeId", 0),
                                    activity.get("activityType", {}).get("parentTypeId", 0))
            logger.info(f"Activity saved: {activity['activityName']} at {activity['startTimeLocal']} as {filetype}")
            saved += 1

        except Exception as e: 
            # ToDo: add logging 
            logger.error(f"Error saving activity {activity['activityName']} at {activity['startTimeLocal']} as {filetype}: {e}")
            continue
    return saved

def ensure_unique_filename(download_dir, filename):
    """Reserve a unique filename atomically.

    This creates the file using O_CREAT|O_EXCL so concurrent processes
    cannot claim the same name (prevents TOCTOU race).
    Returns the unique filename (not full path).
    """
    base, ext = os.path.splitext(filename)
    counter = 0

    while True:
        candidate = filename if counter == 0 else f"{base}_{counter}{ext}"
        path = os.path.join(download_dir, candidate)
        try:
            # Atomically create the file; mode 0600 restricts access
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            return candidate
        except FileExistsError:
            counter += 1


def build_unique_filepath(activity, directory, filetype, config):
    filename = ensure_unique_filename(directory, generate_filename(activity, filetype, config))
    return os.path.join(directory, filename)

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


def migrate_filename_template(db, config):
    logger.info("Migrating existing files to new filename template...")
    rows = db.get_all_activities()
    activitiesUpdated = 0
    for row in rows:
        activity, filetype, file_path = row_to_activity(row, config)
        new_file_path = os.path.join(os.path.dirname(file_path),  generate_filename(activity, filetype, config))
        if file_path != new_file_path:
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
                    logger.debug(f"Deleted empty directory {root}")
                    folders_deleted_this_run += 1
            except Exception:
                pass
        if folders_deleted_this_run == 0:
            break
            
def main():
    try:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        file_handler = logging.FileHandler("garmin_downloader.log")
        file_handler.setLevel(logging.DEBUG)
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers= [console_handler,file_handler]
            )
        config, errors = GarminDownloaderConfig.from_env()
        if not config:
            logger.error("Invalid configuration:")
            for error in errors:
                logger.error(f" - {error}")
            return
        init_download_dir(config)
        client = init_garmin_client(config)
        with GarminDownloaderDB(config) as db:
            if config.rename_existing_files:
                migrate_filename_template(db, config)
            if config.reorder_existing_filestructure:
                migrate_file_structure(db, config)
            download_activities(client, db, config)
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":    
    main()
