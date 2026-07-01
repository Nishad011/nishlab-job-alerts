"""
NISHLAB CREATIONS - Automated Job Alert Forwarder
---------------------------------------------------
What this does:
1. Searches Adzuna's job API (free tier) for mechanical/CAD/CAE roles in India
2. Compares results against a local "seen_jobs.json" file so the same job
   is never sent twice
3. Sends any brand-new job postings to a Telegram channel/group as a
   formatted message

This script is meant to be triggered automatically by GitHub Actions on a
schedule (see .github/workflows/job-alerts.yml) - so once it's set up,
nobody has to run it by hand.

Required environment variables (set as GitHub Actions "secrets"):
  ADZUNA_APP_ID       - from https://developer.adzuna.com/
  ADZUNA_APP_KEY      - from https://developer.adzuna.com/
  TELEGRAM_BOT_TOKEN  - from @BotFather on Telegram
  TELEGRAM_CHAT_ID    - the channel/group ID the bot should post to
"""

import os
import sys
import json
import requests
from pathlib import Path

# ---------- CONFIG ----------

ADZUNA_COUNTRY = "in"          # India
SEARCH_LOCATION = "India"      # can narrow to "Mumbai" if you only want local jobs
RESULTS_PER_PAGE = 20

# Keywords relevant to NISHLAB students (SolidWorks, ANSYS, AutoCAD, CAD/CAE roles)
KEYWORDS = "SolidWorks ANSYS AutoCAD CAD CAE \"mechanical design\" \"design engineer\""

SEEN_JOBS_FILE = Path(__file__).parent / "seen_jobs.json"

# ---------- HELPERS ----------

def load_seen_jobs():
    if SEEN_JOBS_FILE.exists():
        try:
            return set(json.loads(SEEN_JOBS_FILE.read_text()))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()


def save_seen_jobs(seen_ids):
    # Keep the file from growing forever - cap at last 500 job ids
    trimmed = list(seen_ids)[-500:]
    SEEN_JOBS_FILE.write_text(json.dumps(trimmed, indent=2))


def fetch_jobs(app_id, app_key):
    url = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": RESULTS_PER_PAGE,
        "what_or": KEYWORDS,
        "where": SEARCH_LOCATION,
        "content-type": "application/json",
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("results", [])


def format_message(job):
    title = job.get("title", "Untitled role").strip()
    company = job.get("company", {}).get("display_name", "Unknown company")
    location = job.get("location", {}).get("display_name", "Location not listed")
    url = job.get("redirect_url", "")
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    salary_line = ""
    if salary_min and salary_max:
        salary_line = f"\nSalary: ₹{int(salary_min):,} - ₹{int(salary_max):,}"

    return (
        f"*New job alert - NISHLAB CREATIONS*\n\n"
        f"*{title}*\n"
        f"Company: {company}\n"
        f"Location: {location}"
        f"{salary_line}\n\n"
        f"Apply: {url}"
    )


def send_telegram_message(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=30)
    if not resp.ok:
        print(f"Telegram send failed: {resp.status_code} {resp.text}", file=sys.stderr)
    return resp.ok


# ---------- MAIN ----------

def main():
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    missing = [name for name, val in [
        ("ADZUNA_APP_ID", app_id),
        ("ADZUNA_APP_KEY", app_key),
        ("TELEGRAM_BOT_TOKEN", bot_token),
        ("TELEGRAM_CHAT_ID", chat_id),
    ] if not val]

    if missing:
        print(f"Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    seen_ids = load_seen_jobs()

    try:
        jobs = fetch_jobs(app_id, app_key)
    except requests.RequestException as e:
        print(f"Failed to fetch jobs from Adzuna: {e}", file=sys.stderr)
        sys.exit(1)

    new_jobs = [job for job in jobs if str(job.get("id")) not in seen_ids]

    if not new_jobs:
        print("No new jobs found this run.")
        return

    sent_count = 0
    for job in new_jobs:
        job_id = str(job.get("id"))
        message = format_message(job)
        success = send_telegram_message(bot_token, chat_id, message)
        if success:
            seen_ids.add(job_id)
            sent_count += 1

    save_seen_jobs(seen_ids)
    print(f"Sent {sent_count} new job alert(s) out of {len(new_jobs)} found.")


if __name__ == "__main__":
    main()
