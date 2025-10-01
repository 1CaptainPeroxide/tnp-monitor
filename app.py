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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def get_recent_hashes(conn, cutoff):
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT NOT NULL UNIQUE,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor = conn.execute("SELECT hash FROM hashes;")
        results = cursor.fetchall()
        return set(row[0] for row in results) if results else set()

def update_hashes(conn, new_hashes):
    with conn:
        for new_hash in new_hashes:
            try:
                conn.execute("INSERT OR IGNORE INTO hashes (hash) VALUES (?);", (new_hash,))
            except:
                pass
    logger.info("✅ Hashes updated successfully.")

def cleanup_hashes(conn, cutoff):
    with conn:
        conn.execute("DELETE FROM hashes WHERE timestamp < ?;", (cutoff,))
    logger.info("🗑 Old hashes cleaned up successfully.")

# 🔹 Notices Extraction
def extract_notices(content, cutoff, ist):
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    
    if not notices_table:
        logger.warning("❌ No notices table found!")
        return notices

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            date_td = row.find_all('td')[1]
            data_order = date_td.get('data-order')
            if not data_order:
                continue

            post_datetime = ist.localize(datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S'))
            if post_datetime < cutoff:
                continue

            title_tag = row.find('h6').find('a')
            title = title_tag.get_text(strip=True)
            full_link = f"https://tp.bitmesra.co.in/{title_tag['href']}"
            
            message = f"📢 *New Notice:*\n🔹 {title}\n🔗 {full_link}\n📅 {post_datetime.strftime('%d/%m/%Y %H:%M')}"
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))

        except Exception as e:
            logger.error(f"❌ Error extracting notice: {e}")
    
    return notices

# 🔹 Companies Extraction
def extract_companies(content, cutoff, ist):
    companies = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table')

    if not job_table:
        logger.warning("❌ No companies table found!")
        return companies

    logger.info("✅ Companies table found!")

    for row in job_table.find('tbody').find_all('tr'):
        try:
            date_td = row.find_all('td')[1]
            post_date = datetime.datetime.strptime(date_td['data-order'], '%Y/%m/%d').date()
            post_datetime = ist.localize(datetime.datetime.combine(post_date, datetime.time.min))

            if post_datetime < cutoff:
                continue

            company_name = row.find_all('td')[0].get_text(strip=True)
            apply_link = "No link available"
            for link_tag in row.find_all('a'):
                if "Apply" in link_tag.get_text():
                    apply_link = f"https://tp.bitmesra.co.in/{link_tag['href']}"
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
        response = requests.post(url, params=params)
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
        conn = get_sqlite_connection()
        
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(days=7)  # keep hashes 7 days

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
            send_telegram_message(f"❌ *Error in TNP Monitor:*\n{e}")
        except:
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
    except:
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
    
    # ❌ Removed immediate run job to prevent duplicate messages
    
    # Health check every 5 minutes
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
    return scheduler

# 🔹 Global scheduler variable
scheduler = None

# 🔹 Application startup
if __name__ == '__main__':
    scheduler = init_scheduler()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
