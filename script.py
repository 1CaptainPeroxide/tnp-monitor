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

# 🔹 Load environment variables
load_dotenv()

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
        print("✅ Logged in successfully.")
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

# 🔹 Database Handling
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
    print("✅ Hashes updated successfully.")

def cleanup_hashes(conn, cutoff):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hashes WHERE timestamp < %s;", (cutoff,))
        conn.commit()
        print("🗑 Old hashes cleaned up successfully.")

# 🔹 Notices Extraction
def extract_notices(content, cutoff, ist):
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    
    if not notices_table:
        print("❌ No notices table found!")
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
            print(f"❌ Error extracting notice: {e}")
    
    return notices

# 🔹 Companies Extraction
def extract_companies(content, cutoff, ist):
    companies = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table')  # ⚠️ Check job table manually if needed

    if not job_table:
        print("❌ No companies table found!")
        return companies

    print("✅ Companies table found!")

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
            print(f"❌ Error extracting company: {e}")

    return companies

# 🔹 Telegram Message
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    
    try:
        response = requests.post(url, params=params)
        response.raise_for_status()
        print("✅ Telegram message sent!")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

# 🔹 Main Function
def main():
    session = get_session()
    conn = None
    try:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(hours=24)

        login(session)
        notices_html = fetch_page(session, NOTICES_URL)
        companies_html = fetch_page(session, JOBS_URL)

        recent_notices = extract_notices(notices_html, cutoff, ist)
        recent_companies = extract_companies(companies_html, cutoff, ist)

        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            stored_hashes = get_recent_hashes(conn, cutoff)
            print(f"🗂 Stored Hashes: {stored_hashes}")

            new_hashes = set()
            for message, item_hash in recent_notices + recent_companies:
                if item_hash not in stored_hashes:
                    send_telegram_message(message)
                    new_hashes.add(item_hash)

            print(f"🆕 New Hashes: {new_hashes}")
            update_hashes(conn, new_hashes)
            cleanup_hashes(conn, cutoff)

    except Exception as e:
        print(f"❌ Error: {e}")
        send_telegram_message(f"❌ *Error in TNP Monitor:*\n{e}")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
