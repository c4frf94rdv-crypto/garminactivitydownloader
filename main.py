import os
import logging
import time
import sys
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
    download_dir = os.path.join(os.getcwd(), config.download_dir)
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

def _countdown_timer(total_seconds):
    remaining = total_seconds
    
    while remaining > 0:
        hours, remainder = divmod(remaining, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Formatiert die Anzeige (z.B. "05h 14m 22s")
        # Der Zusatz '\r' am Anfang sorgt dafür, dass der Cursor an den Zeilenanfang springt
        # end="" verhindert, dass Python automatisch eine neue Zeile anfängt
        sys.stdout.write(f"\rRunning in Docker mode. Next download in: {hours:02d}h {minutes:02d}m {seconds:02d}s ...")
        sys.stdout.flush()
        
        time.sleep(1)
        remaining -= 1
        
    # Wenn der Countdown abgelaufen ist, die Zeile sauber leeren
    print("\r" + " " * 50 + "\r", end="")

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
        # Run download at least once at startup
        rundownloader(config)

        if config.dockermode:
            total_delay_seconds = config.downloadinterval

            while True:
                _countdown_timer(config.downloadinterval)
                try:
                    rundownloader(config)
                except Exception as e:
                    print(f"Fehler im Download-Zyklus: {e}")

    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":    
    main()
