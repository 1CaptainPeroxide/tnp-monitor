# --- START: minimal fixes applied to your original script ---

import os
import hashlib
import time
import datetime
from datetime import timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import sqlite3
from flask import Flask, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import logging
import threading

# 🔹 Load environment variables
load_dotenv()

# 🔹 Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 🔹 Initialize Flask app
app = Flask(__name__)

# 🔹 Environment Variables
TP_USERNAME = os.getenv('TP_USERNAME')
TP_PASSWORD = os.getenv('TP_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DATABASE_URL = os.getenv('DATABASE_URL')

# 🔹 URLs
LOGIN_URL = "https://tp.bitmesra.co.in/auth/login.html"
NOTICES_URL = "https://tp.bitmesra.co.in/newsevents"
JOBS_URL = "https://tp.bitmesra.co.in"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"}

# 🔹 Global variables for job status
job_status = {
    "last_run": None,
    "last_success": None,
    "error_count": 0,
    "is_running": False
}

# 🔹 Session Management
def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    try:
        response = session.get(LOGIN_URL)
        response.raise_for_status()
        login_data = {'identity': TP_USERNAME, 'password': TP_PASSWORD, 'submit': 'Login'}
        login_response = session.post(LOGIN_URL, data=login_data)
        login_response.raise_for_status()
        logger.info("✅ Logged in successfully.")
    except Exception as e:
        raise Exception(f"❌ Login failed: {e}")

# 🔹 Fetch Data
def fetch_page(session, url):
    try:
        response = session.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"❌ Failed to fetch {url}: {e}")

# 🔹 Hashing
def compute_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

# 🔹 SQLite Database Handling
def get_sqlite_connection():
    """Get SQLite database connection"""
    db_path = os.getenv('SQLITE_DB_PATH', 'tnp_monitor.db')
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    conn.row_factory = sqlite3.Row
    return conn

def get_recent_hashes(conn, cutoff):
    # cutoff is expected to be a timezone-aware datetime (IST) in our code,
    # convert to UTC string format matching SQLite CURRENT_TIMESTAMP (YYYY-MM-DD HH:MM:SS)
    if isinstance(cutoff, datetime.datetime):
        cutoff_utc_str = cutoff.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    else:
        cutoff_utc_str = str(cutoff)

    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT (datetime('now'))
            );
        """)
        cursor = conn.execute("SELECT hash FROM hashes WHERE timestamp >= ?;", (cutoff_utc_str,))
        results = cursor.fetchall()
        return set(row[0] for row in results) if results else set()

def update_hashes(conn, new_hashes):
    with conn:
        for new_hash in new_hashes:
            conn.execute("INSERT INTO hashes (hash) VALUES (?);", (new_hash,))
    logger.info("✅ Hashes updated successfully.")

def cleanup_hashes(conn, cutoff):
    # cutoff is expected to be timezone-aware datetime; convert to UTC string
    if isinstance(cutoff, datetime.datetime):
        cutoff_utc_str = cutoff.astimezone(pytz.UTC).strftime('%Y-%m-%d %H:%M:%S')
    else:
        cutoff_utc_str = str(cutoff)

    with conn:
        conn.execute("DELETE FROM hashes WHERE timestamp < ?;", (cutoff_utc_str,))
    logger.info("🗑 Old hashes cleaned up successfully.")

# 🔹 Notices Extraction
def extract_notices(content, cutoff, ist):
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    
    if not notices_table:
        logger.warning("❌ No notices table found!")
        return notices

    tbody = notices_table.find('tbody')
    if not tbody:
        logger.warning("❌ Notices tbody not found!")
        return notices

    for row in tbody.find_all('tr'):
        try:
            tds = row.find_all('td')
            if len(tds) < 2:
                continue
            date_td = tds[1]
            data_order = date_td.get('data-order')
            if not data_order:
                # fallback: try visible text
                visible_date_text = date_td.get_text(strip=True)
                try:
                    post_datetime = datetime.datetime.strptime(visible_date_text, '%d/%m/%Y %H:%M')
                    post_datetime = ist.localize(post_datetime)
                except Exception:
                    logger.debug("Skipping notice with unparseable date")
                    continue
            else:
                # parse data-order which in notices seems to be 'YYYY/MM/DD HH:MM:SS'
                try:
                    post_datetime = datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S')
                    post_datetime = ist.localize(post_datetime)
                except Exception:
                    logger.debug("Failed parsing data-order for notice, skipping")
                    continue

            if post_datetime < cutoff:
                continue

            title_h6 = row.find('h6')
            if not title_h6:
                logger.debug("No h6 in notice row; skipping")
                continue
            title_tag = title_h6.find('a')
            if not title_tag:
                logger.debug("No link in notice h6; skipping")
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get('href', '')
            if href.startswith('/'):
                full_link = f"https://tp.bitmesra.co.in{href}"
            else:
                full_link = f"https://tp.bitmesra.co.in/{href}"

            message = f"📢 *New Notice:*\n🔹 {title}\n🔗 {full_link}\n📅 {post_datetime.strftime('%d/%m/%Y %H:%M')}"
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))

        except Exception as e:
            logger.error(f"❌ Error extracting notice: {e}")
    
    return notices

# 🔹 Companies (Jobs) Extraction — fixed to select correct table id
def extract_companies(content, cutoff, ist):
    companies = []
    soup = BeautifulSoup(content, 'html.parser')
    # select the job listings table explicitly
    job_table = soup.find('table', {'id': 'job-listings'})

    if not job_table:
        logger.warning("❌ No companies (job-listings) table found!")
        return companies

    tbody = job_table.find('tbody')
    if not tbody:
        logger.warning("❌ job-listings tbody not found!")
        return companies

    logger.info("✅ Companies table found!")

    for row in tbody.find_all('tr'):
        try:
            tds = row.find_all('td')
            if len(tds) < 3:
                continue

            date_td = tds[1]
            data_order = date_td.get('data-order')
            if not data_order:
                logger.debug("Skipping job row with no data-order")
                continue

            # data_order in job table is like 'YYYY/MM/DD' or 'YYYY/MM/DD HH:MM:SS' — handle both
            try:
                post_date = datetime.datetime.strptime(data_order, '%Y/%m/%d').date()
            except ValueError:
                try:
                    post_datetime_tmp = datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S')
                    post_date = post_datetime_tmp.date()
                except Exception:
                    logger.debug("Unparseable job data-order; skipping row")
                    continue

            post_datetime = ist.localize(datetime.datetime.combine(post_date, datetime.time.min))

            if post_datetime < cutoff:
                continue

            company_name = tds[0].get_text(strip=True)

            apply_link = "No link available"
            # find link that contains 'apply' (case-insensitive)
            for link_tag in row.find_all('a'):
                if 'apply' in link_tag.get_text(strip=True).lower():
                    href = link_tag.get('href', '')
                    if href.startswith('/'):
                        apply_link = f"https://tp.bitmesra.co.in{href}"
                    else:
                        apply_link = f"https://tp.bitmesra.co.in/{href}"
                    break

            message = f"🏢 *New Company Listed:*\n🔹 {company_name}\n📅 {post_date.strftime('%d/%m/%Y')}\n🔗 {apply_link}"
            company_hash = compute_hash(message)
            companies.append((message, company_hash))

        except Exception as e:
            logger.error(f"❌ Error extracting company: {e}")

    return companies

# 🔹 Telegram Message
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    
    try:
        # use data= for POST form data (safer / more consistent than params=)
        response = requests.post(url, data=params, timeout=15)
        response.raise_for_status()
        logger.info("✅ Telegram message sent!")
    except Exception as e:
        logger.error(f"❌ Failed to send Telegram message: {e}")

# 🔹 Main Job Function
def run_tnp_monitor():
    """Main function to run the TNP monitoring job"""
    if job_status["is_running"]:
        logger.info("Job already running, skipping...")
        return
    
    job_status["is_running"] = True
    job_status["last_run"] = datetime.datetime.now().isoformat()
    
    try:
        session = get_session()
        conn = None
        
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(hours=24)

        login(session)
        notices_html = fetch_page(session, NOTICES_URL)
        companies_html = fetch_page(session, JOBS_URL)

        recent_notices = extract_notices(notices_html, cutoff, ist)
        recent_companies = extract_companies(companies_html, cutoff, ist)

        # Use SQLite for local development
        conn = get_sqlite_connection()

        # For SQLite comparisons we must pass cutoff as UTC formatted string
        stored_hashes = get_recent_hashes(conn, cutoff)
        logger.info(f"🗂 Stored Hashes: {len(stored_hashes)}")

        new_hashes = set()
        for message, item_hash in recent_notices + recent_companies:
            if item_hash not in stored_hashes:
                send_telegram_message(message)
                new_hashes.add(item_hash)

        logger.info(f"🆕 New items found: {len(new_hashes)}")
        if new_hashes:
            update_hashes(conn, new_hashes)
        # cleanup: keep last 7 days
        cleanup_cutoff = now - timedelta(days=7)
        cleanup_hashes(conn, cleanup_cutoff)

        job_status["last_success"] = datetime.datetime.now().isoformat()
        job_status["error_count"] = 0
        logger.info("✅ TNP Monitor job completed successfully")

    except Exception as e:
        job_status["error_count"] += 1
        error_msg = f"❌ Error in TNP Monitor: {e}"
        logger.error(error_msg)
        try:
            send_telegram_message(f"❌ *Error in TNP Monitor:*\n{e}")
        except Exception:
            logger.error("Failed to send error message to Telegram")

    finally:
        if 'conn' in locals() and conn:
            conn.close()
        job_status["is_running"] = False

# 🔹 Flask Routes
@app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        "message": "TNP Monitor API (SQLite Version)",
        "status": "running",
        "version": "1.0.0",
        "database": "SQLite",
        "endpoints": {
            "/": "This help message",
            "/health": "Health check endpoint",
            "/status": "Job status information",
            "/run": "Manually trigger job (POST)",
            "/ping": "Simple ping endpoint"
        }
    })

@app.route('/health')
def health():
    """Health check endpoint for keeping the app alive"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "uptime": "running",
        "database": "SQLite"
    })

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return jsonify({
        "message": "pong",
        "timestamp": datetime.datetime.now().isoformat()
    })

@app.route('/status')
def status():
    """Get current job status"""
    # Get scheduler information
    scheduler_info = []
    try:
        for job in scheduler.get_jobs():
            scheduler_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
    except Exception:
        scheduler_info = "Scheduler not available"
    
    return jsonify({
        "job_status": job_status,
        "scheduler_jobs": scheduler_info,
        "environment": {
            "has_telegram_token": bool(TELEGRAM_BOT_TOKEN),
            "has_telegram_chat_id": bool(TELEGRAM_CHAT_ID),
            "has_tp_credentials": bool(TP_USERNAME and TP_PASSWORD),
            "database_type": "SQLite"
        }
    })

@app.route('/run', methods=['POST'])
def manual_run():
    """Manually trigger the TNP monitor job"""
    try:
        # Run the job in a separate thread to avoid blocking
        thread = threading.Thread(target=run_tnp_monitor)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            "message": "Job triggered successfully",
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "timestamp": datetime.datetime.now().isoformat()
        }), 500

# 🔹 Initialize Scheduler
def init_scheduler():
    """Initialize the background scheduler"""
    scheduler = BackgroundScheduler()
    
    # Schedule the job to run every 10 minutes
    scheduler.add_job(
        func=run_tnp_monitor,
        trigger=IntervalTrigger(minutes=10),
        id='tnp_monitor_job',
        name='TNP Monitor Job',
        replace_existing=True
    )
    
    # Also schedule an immediate run to test
    scheduler.add_job(
        func=run_tnp_monitor,
        trigger='date',  # Run immediately
        id='tnp_monitor_immediate',
        name='TNP Monitor Immediate Test',
        replace_existing=True
    )
    
    # internal health check
    def internal_health_check():
        try:
            logger.info("Internal health check - app is running")
        except Exception as e:
            logger.error(f"Health check error: {e}")
    
    scheduler.add_job(
        func=internal_health_check,
        trigger=IntervalTrigger(minutes=5),
        id='health_check_job',
        name='Health Check Job',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ Scheduler started successfully")
    logger.info("📅 TNP Monitor job scheduled to run every 10 minutes")
    logger.info("🚀 Immediate test job scheduled to run now")
    return scheduler

# 🔹 Global scheduler variable
scheduler = None

# 🔹 Application startup
if __name__ == '__main__':
    # Initialize the scheduler
    scheduler = init_scheduler()
    
    # Run the app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

# --- END: minimal fixes applied ---
