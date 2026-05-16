import os
from dotenv import load_dotenv
from garminconnect import Garmin
from database import fit_downloader_db
from pathvalidate import sanitize_filename

load_dotenv()

# Load Configuration from environment variables
USER_EMAIL = os.getenv("USER_EMAIL")
USER_PASSWORD = os.getenv("USER_PASSWORD")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR")
DB_FILE = os.getenv("DB_FILE")
LIMIT_ACTIVITIES = int(os.getenv("LIMIT_ACTIVITIES", "5"))
SUBFOLDER_PER_ACTIVITYTYPE = os.getenv("SUBFOLDER_PER_ACTIVITYTYPE", "true").lower() == "true"
MAX_ACTIVITIES_TO_DOWNLOAD=1000
FILENAME_TEMPLATE = os.getenv("FILENAME_TEMPLATE", "{activityId}")

def init_garmin_client():
    client = Garmin(USER_EMAIL, USER_PASSWORD)
    client.login()
    return client

def init_download_dir():
    download_dir = os.path.join(os.getcwd(), DOWNLOAD_DIR)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def get_and_create_downloadpath_by_activitytype(activity):
    download_dir = os.path.join(os.getcwd(), DOWNLOAD_DIR)

    if SUBFOLDER_PER_ACTIVITYTYPE:
        act_type_dict = activity.get("activityType", {})
        activity_type = act_type_dict.get("typeKey", "unknown")
        download_dir = os.path.join(download_dir, activity_type)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def generate_filename(activity) -> str:

    act_type_dict = activity.get("activityType", {})
    activity_type = act_type_dict.get("typeKey", "unknown")
    startTime = activity.get('startTimeLocal', '0000-00-00')

    filename = FILENAME_TEMPLATE.format(activityId=activity['activityId'], 
                                        activityName=activity['activityName'], 
                                        activityStartTime=startTime[:10], 
                                        activityType=activity_type)
    filename = sanitize_filename(filename)
    return f"{filename}.fit"

def download_activities(client, db):
    print("Downloading activities...")

    total_downloaded = 0
    while total_downloaded < LIMIT_ACTIVITIES:
        blocksize = min(MAX_ACTIVITIES_TO_DOWNLOAD, LIMIT_ACTIVITIES - total_downloaded)
        if blocksize <= 0:
            break
        activities = client.get_activities(total_downloaded, blocksize)
        for activity in activities:
            if db.is_activity_saved(activity['activityId']):
                print(f" - {activity['activityName']} am {activity['startTimeLocal']} already downloaded, skipping.")
                continue

            fit_data = client.download_activity(activity['activityId'])
            activity_type_dir = get_and_create_downloadpath_by_activitytype(activity)
            write_activity_to_file(activity_type_dir, activity, fit_data, db)
        total_downloaded += len(activities)

def ensure_unique_filename(download_dir, filename):
    base, ext = os.path.splitext(filename)
    counter = 1
    unique_filename = filename

    while os.path.exists(os.path.join(download_dir, unique_filename)):
        unique_filename = f"{base}_{counter}{ext}"
        counter += 1

    return unique_filename

def write_activity_to_file(download_dir, activity, fit_data, db):
    filename = ensure_unique_filename(download_dir, generate_filename(activity))
    file_path = os.path.join(download_dir, filename)

    with open(file_path, "wb") as f:
        f.write(fit_data)
        db.save_activity_to_db(activity['activityId'], activity['activityName'], activity['startTimeLocal'], file_path)
        print(f"Activity saved: {activity['activityName']} at {activity['startTimeLocal']}")

def main():
    print("Connecting to Garmin Connect...")

    try:
        client = init_garmin_client()
        db = fit_downloader_db(DB_FILE)
        db.cleanup_orphaned_entries()
        download_activities(client, db)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":    main()
