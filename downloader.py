import os
import logging
import io
from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectConnectionError
import zipfile
from file_utils import get_downloadpath_by_activitytype, build_unique_filepath

logger = logging.getLogger(__name__)

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
            relative_file_path = os.path.relpath(file_path, os.path.join(config.basedir, config.download_dir))
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
