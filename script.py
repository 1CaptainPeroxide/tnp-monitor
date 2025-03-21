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

# Load environment variables
load_dotenv()

# Environment Variables
TP_USERNAME = os.getenv('TP_USERNAME')
TP_PASSWORD = os.getenv('TP_PASSWORD')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
DATABASE_URL = os.getenv('DATABASE_URL')

# URLs
LOGIN_URL = "https://tp.bitmesra.co.in/auth/login.html"
NOTICES_URL = "https://tp.bitmesra.co.in/newsevents"
COMPANIES_URL = "https://tp.bitmesra.co.in/index"  # Jobs/Companies Listing

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"}

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
        print("Logged in successfully.")
    except Exception as e:
        raise Exception(f"Login failed: {e}")

def fetch_page(session, url):
    try:
        response = session.get(url)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"Failed to fetch {url}: {e}")

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
        return set(row[0] for row in cur.fetchall()) if cur.rowcount else set()

def update_hashes(conn, new_hashes):
    with conn.cursor() as cur:
        for new_hash in new_hashes:
            cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()

def cleanup_hashes(conn, cutoff):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hashes WHERE timestamp < %s;", (cutoff,))
        conn.commit()

def extract_notices(content, cutoff, ist):
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        return notices

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            date_td = row.find_all('td')[1]
            post_datetime = ist.localize(datetime.datetime.strptime(date_td['data-order'], '%Y/%m/%d %H:%M:%S'))
            if post_datetime < cutoff:
                continue
            title_tag = row.find('h6').find('a')
            title = title_tag.get_text(strip=True)
            full_link = f"https://tp.bitmesra.co.in/{title_tag['href']}"
            message = f"📢 <b>New Notice:</b> {title}\n🔗 {full_link}\n🗓 {post_datetime.strftime('%d/%m/%Y %H:%M')}"
            notices.append((message, compute_hash(message)))
        except Exception:
            pass
    return notices

def extract_companies(content, cutoff, ist):
    companies = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table', {'id': 'job-listings'})
    if not job_table:
        return companies

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
            message = f"🏢 <b>New Company Listed:</b> {company_name}\n🗓 {post_date.strftime('%d/%m/%Y')}\n🔗 {apply_link}"
            companies.append((message, compute_hash(message)))
        except Exception:
            pass
    return companies

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, params=params).raise_for_status()
    except Exception as e:
        print(f"Telegram send failed: {e}")

def main():
    session = get_session()
    conn = None
    try:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(hours=24)

        login(session)

        notices_html = fetch_page(session, NOTICES_URL)
        companies_html = fetch_page(session, COMPANIES_URL)

        recent_notices = extract_notices(notices_html, cutoff, ist)
        recent_companies = extract_companies(companies_html, cutoff, ist)

        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            stored_hashes = get_recent_hashes(conn, cutoff)

            new_hashes = set()
            for message, item_hash in recent_notices + recent_companies:
                if item_hash not in stored_hashes:
                    send_telegram_message(message)
                    new_hashes.add(item_hash)

            update_hashes(conn, new_hashes)
            cleanup_hashes(conn, cutoff)

    except Exception as e:
        send_telegram_message(f"❌ <b>Error in TNP Monitor:</b>\n{e}")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
