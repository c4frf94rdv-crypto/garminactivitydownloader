# Garmin Activity Downloader

Automatically downloads activity files from Garmin Connect and saves them locally. Supports FIT and TCX formats, configurable folder structures, and runs continuously in Docker with a scheduled download interval.

---

## Quick Start (Docker)

**1. Create your configuration:**

```bash
cp .env.example .env
```

Edit `.env` and set at least `DOWNLOAD_DIR`. Credentials (`USER_EMAIL`, `USER_PASSWORD`) are optional — if left empty, you can log in interactively via the browser terminal on first start.

**2. Start the container:**

```bash
docker compose up -d
```

The provided `docker-compose.yml` is ready to use and only requires a configured `.env` file.

**3. First login (if no credentials are set):**

Open `http://localhost:9000` in your browser. A terminal opens where you can complete the Garmin login, including MFA if enabled. Tokens are saved and reused on subsequent runs — no repeated login required.

---

## Quick Start (Local)

**Requirements:** Python 3.11+

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env as needed

python main.py
```

Set `DOCKERMODE=false` in `.env` to run only once instead of continuously.

---

## Configuration

All settings are controlled via environment variables in the `.env` file.

### Credentials

| Variable | Description |
|---|---|
| `USER_EMAIL` | Garmin Connect email address |
| `USER_PASSWORD` | Garmin Connect password |

Both are optional. If not set, the program prompts for login via the browser terminal on first start. After a successful login, tokens are saved automatically and reused on every subsequent run.

### Directories

| Variable | Default | Description |
|---|---|---|
| `DOWNLOAD_DIR` | *(required)* | Folder where activity files are saved |
| `BASEDIR` | `./data` | Root folder for all data (downloads, database, logs). In Docker this maps to `/app/data`. |
| `DB_FILE` | `garmin_activities.db` | Name of the database file used to track downloads |

### Download Settings

| Variable | Default | Description |
|---|---|---|
| `LIMIT_ACTIVITIES` | `5` | Number of most recent activities to download per run |
| `DOWNLOAD_FORMAT` | `fit` | File format: `fit`, `tcx`, or `both` |

### Filename Template

Controls how downloaded files are named.

| Variable | Default |
|---|---|
| `FILENAME_TEMPLATE` | `{activityId}` |

Available placeholders:

| Placeholder | Example |
|---|---|
| `{activityId}` | `1234567890` |
| `{activityName}` | `Morning Run` |
| `{activityType}` | `running` |
| `{activityStartDate}` | `2026-06-10` |
| `{activityStartDateTime}` | `2026-06-10_08-30-00` |

Example: `FILENAME_TEMPLATE="{activityStartDateTime}_{activityName}"` produces `2026-06-10_08-30-00_Morning Run.fit`.

### Folder Structure

| Variable | Default | Description |
|---|---|---|
| `SUBFOLDER_PER_FORMAT` | `false` | Create subfolders per format (`fit/`, `tcx/`) |
| `SUBFOLDER_PER_ACTIVITYTYPE` | `true` | Create subfolders per activity type (`running/`, `cycling/`) |

With both enabled and `DOWNLOAD_FORMAT=both`, files are organized like this:

```
data/
└── garmin_activities/
    ├── fit/
    │   ├── running/
    │   └── cycling/
    └── tcx/
        ├── running/
        └── cycling/
```

### Reorganizing Existing Files

If you change the filename template or folder structure after activities have already been downloaded, these settings migrate existing files to match the new configuration. Reset both to `false` once the migration is complete.

| Variable | Default | Description |
|---|---|---|
| `RENAME_EXISTING_FILES` | `false` | Rename existing files to match the current `FILENAME_TEMPLATE` |
| `REORDER_EXISTING_FILESTRUCTURE` | `false` | Move existing files into the current folder structure |

---

## Docker Configuration

The included `docker-compose.yml` sets up the container with a volume mount so all data persists across restarts:

```
data/
├── .garmin_tokens/     # Saved login tokens
├── garmin_activities/  # Downloaded activity files
└── garmin_downloader.log
```

### Scheduling

| Variable | Default | Description |
|---|---|---|
| `DOCKERMODE` | `true` | Run continuously; set to `false` to download once and exit |
| `DOWNLOADINTERVAL` | `86400` | Seconds between download runs (default: 24 hours) |
| `SCHEDULE_TIME` | *(not set)* | Optional fixed start time in `HH:MM` format (24-hour) |

The program always downloads immediately on startup. After that:

- **Without `SCHEDULE_TIME`:** waits `DOWNLOADINTERVAL` seconds, then repeats.
- **With `SCHEDULE_TIME`:** waits until the next occurrence of that time, then repeats every `DOWNLOADINTERVAL` seconds from that anchor.

Examples:

| Goal | Configuration |
|---|---|
| Daily at 18:00 | `SCHEDULE_TIME=18:00` + `DOWNLOADINTERVAL=86400` |
| Every 6 hours starting at 10:00 | `SCHEDULE_TIME=10:00` + `DOWNLOADINTERVAL=21600` |
| Weekly (same weekday, 10:00) | `SCHEDULE_TIME=10:00` + `DOWNLOADINTERVAL=604800` |

> **Note:** Garmin Connect enforces rate limits. Avoid setting `DOWNLOADINTERVAL` below a few hours.

### Browser Terminal

The container exposes a browser-based terminal at `http://localhost:9000`. This is used for the initial Garmin login and supports MFA. After logging in once, the session tokens are stored in the data volume and no further interaction is needed.
