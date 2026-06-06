import logging
import os
from pathvalidate import sanitize_filename

logger = logging.getLogger(__name__)

class SafeDict(dict):
    
    def __missing__(self, key):
        """Return a default value if the key is not found in the dictionary."""        
        return "{"+key +"}"

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
