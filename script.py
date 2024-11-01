import os
import hashlib
import time
import datetime
from datetime import timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse
import logging

# Configure logging
logging.basicConfig(
    filename='tnp_monitor.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# Load environment variables
load_dotenv()

# Environment Variables
TP_USERNAME = os.getenv('TP_USERNAME')
TP_PASSWORD = os.getenv('TP_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DATABASE_URL = os.getenv('DATABASE_URL')

# URLs for login and notices
LOGIN_URL = "https://tp.bitmesra.co.in/auth/login.html"
NOTICES_URL = "https://tp.bitmesra.co.in/newsevents"
JOBS_URL = "https://tp.bitmesra.co.in/index"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"
}

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    try:
        response = session.get(LOGIN_URL)
        response.raise_for_status()
        login_data = {
            'identity': TP_USERNAME,
            'password': TP_PASSWORD,
            'submit': 'Login'
        }
        login_response = session.post(LOGIN_URL, data=login_data)
        login_response.raise_for_status()

        soup = BeautifulSoup(login_response.text, 'html.parser')
        error_message = soup.find(id="infoMessage")
        if "Logout" not in login_response.text and (error_message or "login" in login_response.text.lower()):
            error_text = error_message.get_text(strip=True) if error_message else "Unknown login error."
            raise Exception(f"Login failed. Server message: {error_text}")

        logging.info("Logged in successfully.")

    except Exception as e:
        logging.error(f"An error occurred during login: {e}")
        raise

def fetch_all_notices(session):
    all_notices = []
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.datetime.now(ist)
    cutoff = now - timedelta(hours=24)
    
    # Initial parameters for DataTables
    params = {
        'draw': 1,
        'start': 0,
        'length': 100,  # Adjust based on server capabilities
        'search[value]': '',
        'search[regex]': 'false'
    }
    
    while True:
        try:
            response = session.post(NOTICES_URL, data=params)
            response.raise_for_status()
            data = response.json()  # Adjust based on actual response
            notices_html = data.get('html', '')  # Adjust accordingly
            notices, jobs = extract_all_notices(notices_html, cutoff, ist)
            if not notices and not jobs:
                break
            all_notices.extend(notices)
            all_jobs.extend(jobs)
            
            # Check if there are more pages
            if len(notices) + len(jobs) < params['length']:
                break
            params['start'] += params['length']
            params['draw'] += 1
            logging.info(f"Fetched page {params['draw']} with start {params['start']}")
            time.sleep(1)  # Politeness delay
        except Exception as e:
            logging.error(f"An error occurred while fetching notices: {e}")
            break
    return all_notices, all_jobs

def compute_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_recent_hashes(conn, cutoff):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT hash FROM hashes WHERE timestamp >= %s;", (cutoff,))
        results = cur.fetchall()
        return set(row[0] for row in results) if results else set()

def update_hashes(conn, new_hashes):
    with conn.cursor() as cur:
        for new_hash in new_hashes:
            cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()
    logging.info("Hashes updated successfully.")

def cleanup_hashes(conn, cutoff):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hashes WHERE timestamp < %s;", (cutoff,))
        conn.commit()
        logging.info("Old hashes cleaned up successfully.")

def extract_all_notices(content, cutoff, ist):
    notices = []
    jobs = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        logging.warning("No notices table found.")
        return notices, jobs

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            # Extract the date from the 'data-order' attribute if available
            date_td = row.find_all('td')[1]
            data_order = date_td.get('data-order')
            if data_order:
                post_datetime = datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S')
            else:
                visible_date_text = date_td.get_text(strip=True)
                post_datetime = datetime.datetime.strptime(visible_date_text, '%d/%m/%Y %H:%M')
            post_datetime = ist.localize(post_datetime)

            if post_datetime < cutoff:
                continue

            # Extract the notice title and URL
            title_tag = row.find('h6').find('a')
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            full_link = f"https://tp.bitmesra.co.in/{link}"

            # Capture additional description (like "Job", "Job Final Result", etc.)
            small_tag = row.find('small')
            additional_info = small_tag.get_text(" ", strip=True) if small_tag else "No additional info"

            # Construct the message with title, link, date, and additional description
            message = (
                f"Title: {title}\n"
                f"Link: {full_link}\n"
                f"Date: {post_datetime.strftime('%d/%m/%Y %H:%M')}\n"
                f"Details: {additional_info}"
            )
            notice_hash = compute_hash(message)

            # Determine if it's a job-related notice
            if "Job" in additional_info:
                jobs.append((message, notice_hash))
            else:
                notices.append((message, notice_hash))

        except Exception as e:
            logging.error(f"Failed to extract a notice: {e}")
    return notices, jobs

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logging.info("Telegram message sent successfully.")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

def main():
    session = get_session()
    conn = None
    try:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(hours=24)

        login(session)

        # Fetch all notices and jobs across all pages
        all_notices, all_jobs = fetch_all_notices(session)

        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            stored_hashes = get_recent_hashes(conn, cutoff)

            new_notice_hashes = set()
            for message, notice_hash in all_notices:
                if notice_hash not in stored_hashes:
                    send_telegram_message(f"📢 *New Notice on TNP Website:*\n{message}")
                    new_notice_hashes.add(notice_hash)

            new_job_hashes = set()
            for message, job_hash in all_jobs:
                if job_hash not in stored_hashes:
                    send_telegram_message(f"📢 *New Job Listing on TNP Website:*\n{message}")
                    new_job_hashes.add(job_hash)

            update_hashes(conn, new_notice_hashes.union(new_job_hashes))
            cleanup_hashes(conn, cutoff)

    except Exception as e:
        error_message = f"❌ *Error in TNP Monitor:*\n{e}"
        logging.error(error_message)
        try:
            send_telegram_message(error_message)
        except Exception as send_error:
            logging.error(f"Failed to send error notification: {send_error}")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
