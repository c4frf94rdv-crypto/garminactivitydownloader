import os
import logging
import time
from datetime import datetime, timedelta
from database import GarminDownloaderDB
from garminservice import GarminService
from config import GarminDownloaderConfig
from downloader import download_activities
from migration import migrate_filename_template, migrate_file_structure

logger = logging.getLogger(__name__)

def init_garmin_client(config):
    garmin_service = GarminService(config)
    garmin_service.login()
    return garmin_service

def init_download_dir(config):
    download_dir = os.path.join(config.basedir, config.download_dir)
    os.makedirs(download_dir, exist_ok=True)
    return download_dir

def rundownloader(config):
    init_download_dir(config)
    client = init_garmin_client(config)
    with GarminDownloaderDB(config) as db:
        if config.rename_existing_files:
            migrate_filename_template(db, config)
        if config.reorder_existing_filestructure:
            migrate_file_structure(db, config)
        download_activities(client, db, config)

def _next_scheduled_run(schedule_time: str, interval_seconds: int, after: datetime) -> datetime:
    """Calculate the next run time based on SCHEDULE_TIME and DOWNLOADINTERVAL.

    Starting from the first occurrence of schedule_time on or after `after`,
    advance by interval_seconds until the result is in the future.
    """
    h, m = map(int, schedule_time.split(":"))
    anchor = after.replace(hour=h, minute=m, second=0, microsecond=0)
    while anchor <= after:
        anchor += timedelta(seconds=interval_seconds)
    return anchor

def _wait_until_next_run(config) -> None:
    now = datetime.now()
    if config.schedule_time:
        next_run = _next_scheduled_run(config.schedule_time, config.downloadinterval, now)
    else:
        next_run = now + timedelta(seconds=config.downloadinterval)
    logger.info(f"Next download scheduled at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    time.sleep((next_run - datetime.now()).total_seconds())

def main():
    try:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            handlers=[console_handler]
            )
        config, errors = GarminDownloaderConfig.from_env()
        if not config:
            logger.error("Invalid configuration:")
            for error in errors:
                logger.error(f" - {error}")
            return

        os.makedirs(config.basedir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(config.basedir, "garmin_downloader.log"))
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
        logging.getLogger().addHandler(file_handler)

        # Run download at least once at startup
        rundownloader(config)

        if config.dockermode:
            while True:
                _wait_until_next_run(config)
                try:
                    rundownloader(config)
                except Exception as e:
                    logger.exception(f"Error in download cycle: {e}")

    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":    
    main()
