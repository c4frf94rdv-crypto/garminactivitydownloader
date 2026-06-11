import os
import logging
import io
from garminconnect import Garmin
from garminconnect.exceptions import GarminConnectConnectionError, GarminConnectTooManyRequestsError
import zipfile
from file_utils import get_downloadpath_by_activitytype, build_unique_filepath

logger = logging.getLogger(__name__)

def download_activities(garmin_service, db, config):
    logger.info("Downloading activities...")

    total_downloaded = 0
    new_activities = 0
    new_files = 0
    rate_limited = False
    while total_downloaded < config.limit_activities and not rate_limited:
        blocksize = min(config.max_activities_to_download, config.limit_activities - total_downloaded)
        activities = garmin_service.get_activities(total_downloaded, blocksize)
        if len(activities) == 0:
            break
        for activity in activities:
            # One broken activity (unexpected API response, HTTP error, ...) must not abort the whole run
            try:
                files_saved = _download_single_activity(garmin_service, db, config, activity)
                if files_saved > 0:
                    new_activities += 1
                new_files += files_saved
            except GarminConnectTooManyRequestsError:
                # Continuing would only hammer the rate limit further; remaining activities are retried on the next run
                logger.error(f"Rate limit reached at activity {activity.get('activityId')}. Aborting this run.")
                rate_limited = True
                break
            except Exception as e:
                logger.exception(f"Activity {activity.get('activityId')}: Unexpected error, skipping this activity: {e}")
        total_downloaded += len(activities)
    logger.info(f"Download finished: {new_activities} new activities, {new_files} new files")

def _download_single_activity(garmin_service, db, config, activity) -> int:
    """Downloads and stores a single activity. Returns the number of new files saved."""
    activity['activityName'] = activity.get('activityName') or 'Unnamed Activity'
    already_downloaded = True
    # A saved gpx file also counts as fit/tcx: gpx is the fallback for activities where those formats are not available, so re-downloading them would never yield the requested format anyway
    if config.download_format in ["fit", "both"]:
        already_downloaded = already_downloaded and (db.is_activity_saved(activity['activityId'], "fit")
                                                     or db.is_activity_saved(activity['activityId'], "gpx"))
    if config.download_format in ["tcx", "both"]:
        already_downloaded = already_downloaded and (db.is_activity_saved(activity['activityId'], "tcx")
                                                     or db.is_activity_saved(activity['activityId'], "gpx"))

    if already_downloaded:
        logger.debug(f" - {activity['activityName']} / {config.download_format} at {activity.get('startTimeLocal')} already downloaded, skipping.")
        return 0

    activity_package = download_activity_by_id(garmin_service, activity['activityId'], config)
    if not activity_package:
        return 0
    return write_activity_package_to_file(activity, activity_package, db, config)

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
                            # fallback: if no .fit file is found, store a .gpx file from the zip instead. This is not ideal but better than nothing and allows downloading activity data for activities that don't have a .fit file available via the API
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
            logger.error(f"Activity {activity_id}: FIT Download failed, skipping! ({e})")
            return None
    if config.download_format in ["tcx", "both"]:
        try:
            tcx_data = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.TCX)
            if tcx_data:
                activites_package["tcx"] = tcx_data
            else:
                # No TCX data available for this activity (e.g. manually created), fall back to GPX
                logger.info(f"Activity {activity_id}: No TCX data available, falling back to GPX.")
                _add_gpx_fallback(garmin_service, activity_id, activites_package)
        except GarminConnectConnectionError as e:
            # Transient error: no GPX fallback so the TCX download is retried on the next run
            logger.error(f"Activity {activity_id}: TCX download failed, skipping! ({e})")
    return activites_package

def _add_gpx_fallback(garmin_service, activity_id, activites_package):
    """Downloads the ORIGINAL format and adds a contained .gpx file to the package, unless one is already present."""
    if "gpx" in activites_package:
        return
    try:
        raw_bytes = garmin_service.download_activity(activity_id, Garmin.ActivityDownloadFormat.ORIGINAL)
    except GarminConnectConnectionError:
        logger.error(f"Activity {activity_id}: GPX fallback download failed, skipping!")
        return
    if raw_bytes and raw_bytes.startswith(b'PK\x03\x04'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as z:
                gpx_file = next((f for f in z.namelist() if f.lower().endswith('.gpx')), None)
                if gpx_file:
                    activites_package["gpx"] = z.read(gpx_file)
                    return
        except zipfile.BadZipFile:
            logger.error(f"Activity {activity_id}: Invalid ZIP file from Garmin API")
            return
    logger.warning(f"Activity {activity_id}: No .gpx file available as fallback.")

def write_activity_package_to_file(activity, activites_package, db, config) -> int:
    saved = 0
    for filetype, data in activites_package.items():
        if db.is_activity_saved(activity['activityId'], filetype):
            logger.debug(f" - {activity['activityName']} / {filetype} at {activity.get('startTimeLocal')} already downloaded, skipping.")
            continue
        try:    
            download_dir = get_downloadpath_by_activitytype(activity, filetype, config)
            file_path = build_unique_filepath(activity, download_dir, filetype, config, db)
            try:
                with open(file_path, "wb") as f:
                    f.write(data)
            except Exception:
                # If writing fails, remove the reserved file to avoid orphaned empty files
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                except OSError as cleanup_error:
                    logger.warning(f"Could not remove incomplete file {file_path}: {cleanup_error}")
                raise
            relative_file_path = os.path.relpath(file_path, os.path.join(config.basedir, config.download_dir)).replace(os.sep, "/")
            db.save_activity_to_db(activity['activityId'],
                                    filetype,
                                    activity['activityName'],
                                    activity.get('startTimeLocal'),
                                    relative_file_path,
                                    activity.get("activityType", {}).get("typeKey", "unknown"),
                                    activity.get("activityType", {}).get("typeId", 0),
                                    activity.get("activityType", {}).get("parentTypeId", 0))
            logger.info(f"Activity saved: {activity['activityName']} at {activity.get('startTimeLocal')} as {filetype}")
            saved += 1

        except Exception as e:
            logger.error(f"Error saving activity {activity['activityName']} at {activity.get('startTimeLocal')} as {filetype}: {e}")
            continue
    return saved
