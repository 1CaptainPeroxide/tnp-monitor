import requests
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import pytz
import logging
from flask import Flask, jsonify
import hashlib
import datetime
import os
import psycopg2
import urllib.parse as up
from datetime import timedelta

# ------------------- Configuration -------------------
LOGIN_URL = "https://tp.bitmesra.co.in/login"
NOTICES_URL = "https://tp.bitmesra.co.in/newsevents"
JOBS_URL = "https://tp.bitmesra.co.in/index.html"

USERNAME = os.getenv("TNP_USERNAME", "")
PASSWORD = os.getenv("TNP_PASSWORD", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DATABASE_URL = os.getenv("DATABASE_URL", "")

# ------------------- Logging -------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------- Flask App -------------------
app = Flask(__name__)

# ------------------- Job Status -------------------
job_status = {
    "last_run": None,
    "last_success": None,
    "error_count": 0,
    "is_running": False
}

# ------------------- DB Connection -------------------
def get_sqlite_connection():
    up.uses_netloc.append("postgres")
    url = up.urlparse(DATABASE_URL)

    conn = psycopg2.connect(
        database=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    return conn

# ------------------- Hash Storage -------------------
def get_recent_hashes(conn, cutoff):
    with conn.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL UNIQUE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cursor.execute("SELECT hash FROM hashes;")
        results = cursor.fetchall()
        return set(row[0] for row in results) if results else set()

def update_hashes(conn, new_hashes):
    with conn.cursor() as cursor:
        for new_hash in new_hashes:
            cursor.execute(
                "INSERT OR IGNORE INTO hashes (hash) VALUES (%s);",
                (new_hash,)
            )
        conn.commit()
    logger.info("✅ Hashes updated successfully.")

def cleanup_hashes(conn, cutoff):
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM hashes WHERE timestamp < %s;", (cutoff,))
        conn.commit()
    logger.info("🗑 Old hashes cleaned up successfully.")

# ------------------- Scraping -------------------
def get_session():
    session = requests.Session()
    return session

def login(session):
    payload = {"username": USERNAME, "password": PASSWORD}
    session.post(LOGIN_URL, data=payload)

def fetch_page(session, url):
    response = session.get(url)
    response.raise_for_status()
    return response.text

def extract_notices(html, cutoff, ist):
    soup = BeautifulSoup(html, "html.parser")
    notices = []
    for div in soup.find_all("div", class_="event-box"):
        title = div.find("h3").text.strip()
        date_str = div.find("p").text.strip().split(":")[-1].strip()
        try:
            date_obj = datetime.datetime.strptime(date_str, "%d-%b-%Y")
            date_obj = ist.localize(date_obj)
            if date_obj >= cutoff:
                item_hash = hashlib.sha256(title.encode()).hexdigest()
                message = f"📢 *Notice:* {title}\n📅 {date_str}"
                notices.append((message, item_hash))
        except Exception as e:
            logger.error(f"Error parsing notice date: {e}")
    return notices

def extract_companies(html, cutoff, ist):
    soup = BeautifulSoup(html, "html.parser")
    companies = []
    for div in soup.find_all("div", class_="company-box"):
        title = div.find("h3").text.strip()
        deadline_tag = div.find("p", class_="deadline")
        deadline = deadline_tag.text.strip() if deadline_tag else "N/A"
        try:
            if deadline != "N/A":
                date_obj = datetime.datetime.strptime(deadline, "Deadline: %d-%b-%Y")
                date_obj = ist.localize(date_obj)
                if date_obj >= cutoff:
                    item_hash = hashlib.sha256(title.encode()).hexdigest()
                    message = f"🏢 *New Job Listing:* {title}\n⏳ {deadline}"
                    companies.append((message, item_hash))
        except Exception as e:
            logger.error(f"Error parsing company deadline: {e}")
    return companies

# ------------------- Telegram -------------------
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
        logger.info("📨 Message sent to Telegram")
    except Exception as e:
        logger.error(f"Error sending Telegram message: {e}")

# ------------------- Main Job -------------------
def run_tnp_monitor():
    if job_status["is_running"]:
        logger.info("Job already running, skipping...")
        return
    
    job_status["is_running"] = True
    job_status["last_run"] = datetime.datetime.now().isoformat()
    
    try:
        session = get_session()
        conn = get_sqlite_connection()
        
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(days=7)  # ✅ Changed from 1 day → 7 days

        login(session)
        notices_html = fetch_page(session, NOTICES_URL)
        companies_html = fetch_page(session, JOBS_URL)

        recent_notices = extract_notices(notices_html, cutoff, ist)
        recent_companies = extract_companies(companies_html, cutoff, ist)

        stored_hashes = get_recent_hashes(conn, cutoff)
        logger.info(f"🗂 Stored Hashes: {len(stored_hashes)}")

        new_hashes = set()
        for message, item_hash in recent_notices + recent_companies:
            if item_hash not in stored_hashes:
                send_telegram_message(message)
                new_hashes.add(item_hash)

        logger.info(f"🆕 New items found: {len(new_hashes)}")
        update_hashes(conn, new_hashes)
        cleanup_hashes(conn, cutoff)

        job_status["last_success"] = datetime.datetime.now().isoformat()
        job_status["error_count"] = 0
        logger.info("✅ TNP Monitor job completed successfully")

    except Exception as e:
        job_status["error_count"] += 1
        error_msg = f"❌ Error in TNP Monitor: {e}"
        logger.error(error_msg)
        try:
            send_telegram_message(error_msg)
        except:
            logger.error("Failed to send error message to Telegram")

    finally:
        conn.close()
        job_status["is_running"] = False

# ------------------- Scheduler -------------------
def init_scheduler():
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(
        func=run_tnp_monitor,
        trigger=IntervalTrigger(minutes=10),
        id='tnp_monitor_job',
        name='TNP Monitor Job',
        replace_existing=True
    )
    
    # ❌ Removed tnp_monitor_immediate job
    
    scheduler.add_job(
        func=lambda: logger.info("Internal health check - app is running"),
        trigger=IntervalTrigger(minutes=5),
        id='health_check_job',
        name='Health Check Job',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Scheduler started successfully")
    logger.info("📅 TNP Monitor job scheduled to run every 10 minutes")
    return scheduler

# ------------------- Flask Routes -------------------
@app.route("/")
def home():
    return jsonify({"status": "running", "job_status": job_status})

@app.route("/run")
def run_now():
    run_tnp_monitor()
    return jsonify({"status": "Job triggered manually"})

# ------------------- Main -------------------
if __name__ == "__main__":
    scheduler = init_scheduler()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
