import os
import hashlib
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

        print("Logged in successfully.")

    except Exception as e:
        raise Exception(f"An error occurred during login: {e}")

def fetch_notices(session):
    try:
        response = session.get(NOTICES_URL)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"An error occurred while fetching notices: {e}")

def fetch_jobs(session):
    try:
        response = session.get(JOBS_URL)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"An error occurred while fetching job listings: {e}")

def compute_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_recent_hashes(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT hash FROM hashes;")
        results = cur.fetchall()
        return set(row[0] for row in results) if results else set()

def update_hashes(conn, new_hashes):
    with conn.cursor() as cur:
        for new_hash in new_hashes:
            cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()
    print("Hashes updated successfully.")

def cleanup_hashes(conn, cutoff):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hashes WHERE timestamp < %s;", (cutoff,))
        conn.commit()
        print("Old hashes cleaned up successfully.")

def extract_all_notices(content, cutoff, ist):
    """
    Extracts all notices from the HTML content, including all types like "Job", "Job Final Result", "News", etc.
    """
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        print("No notices table found.")
        return notices

    tbody = notices_table.find('tbody')
    if not tbody:
        print("No tbody in notices table.")
        return notices

    for idx, row in enumerate(tbody.find_all('tr')):
        try:
            print(f"\nProcessing row {idx + 1}:")
            # Extract all 'td' elements
            td_list = row.find_all('td')
            if len(td_list) < 2:
                print("Row does not have enough 'td' elements.")
                continue

            # Extract the date
            date_td = td_list[1]
            data_order = date_td.get('data-order')
            if data_order:
                try:
                    # Parse data_order as IST time
                    post_datetime = datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S')
                    post_datetime = ist.localize(post_datetime)
                    print(f"Parsed date from data-order: {post_datetime}")
                except ValueError as ve:
                    print(f"Failed to parse date from data-order '{data_order}': {ve}")
                    continue
            else:
                visible_date_text = date_td.get_text(strip=True)
                # Remove ' IST' from the date text if present
                if visible_date_text.endswith(' IST'):
                    visible_date_text = visible_date_text[:-4].strip()
                try:
                    post_datetime = datetime.datetime.strptime(visible_date_text, '%d/%m/%Y %H:%M')
                    post_datetime = ist.localize(post_datetime)
                    print(f"Parsed date from visible text: {post_datetime}")
                except ValueError as ve:
                    print(f"Failed to parse date from visible text '{visible_date_text}': {ve}")
                    continue

            # Skip notices older than the cutoff
            if post_datetime < cutoff:
                print(f"Notice date {post_datetime} is older than cutoff {cutoff}. Skipping.")
                continue

            # Extract the notice title and URL
            h6_tag = row.find('h6')
            if not h6_tag:
                print("No 'h6' tag found in row.")
                continue
            title_tag = h6_tag.find('a')
            if not title_tag:
                print("No 'a' tag found in 'h6' tag.")
                continue
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href', '')
            if link.startswith('/'):
                full_link = f"https://tp.bitmesra.co.in{link}"
            else:
                full_link = f"https://tp.bitmesra.co.in/{link}"
            print(f"Extracted title: {title}")
            print(f"Extracted link: {full_link}")

            # Capture additional description
            small_tag = row.find('small')
            if small_tag:
                additional_info = small_tag.get_text(" ", strip=True)
                print(f"Extracted additional info: {additional_info}")
            else:
                additional_info = ''
                print("No 'small' tag found for additional info.")

            # Construct the message
            message = f"Title: {title}\nLink: {full_link}\nDate: {post_datetime.strftime('%d/%m/%Y %H:%M')}\nDetails: {additional_info}"
            notice_hash = compute_hash(message)
            print(f"Computed hash: {notice_hash}")
            notices.append((message, notice_hash))

        except Exception as e:
            print(f"Failed to extract a notice: {e}")
            print(f"Row HTML: {row}")
    return notices

def extract_recent_jobs(content, cutoff, ist):
    jobs = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table', {'id': 'job-listings'})
    if not job_table:
        print("No job listings table found.")
        return jobs

    for idx, row in enumerate(job_table.find('tbody').find_all('tr')):
        try:
            print(f"\nProcessing job row {idx + 1}:")
            date_td = row.find_all('td')[1]
            data_order = date_td.get('data-order')
            if not data_order:
                print("No 'data-order' attribute in date_td.")
                continue
            post_date = datetime.datetime.strptime(data_order, '%Y/%m/%d').date()
            post_datetime = ist.localize(datetime.datetime.combine(post_date, datetime.time.min))
            print(f"Parsed job date: {post_datetime}")
            if post_datetime < cutoff:
                print(f"Job date {post_datetime} is older than cutoff {cutoff}. Skipping.")
                continue

            company_name = row.find_all('td')[0].get_text(strip=True)
            apply_link_tag = row.find_all('a')
            apply_link = "No link available"
            for link_tag in apply_link_tag:
                if "Apply" in link_tag.get_text():
                    href = link_tag.get('href', '')
                    if href.startswith('/'):
                        apply_link = f"https://tp.bitmesra.co.in{href}"
                    else:
                        apply_link = f"https://tp.bitmesra.co.in/{href}"
                    break
            print(f"Extracted company name: {company_name}")
            print(f"Extracted apply link: {apply_link}")
            message = f"New Job Listing:\nCompany: {company_name}\nDate: {post_date.strftime('%d/%m/%Y')}\nApply here: {apply_link}"
            job_hash = compute_hash(message)
            print(f"Computed job hash: {job_hash}")
            jobs.append((message, job_hash))
        except Exception as e:
            print(f"Failed to extract a job listing: {e}")
    return jobs

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'  # Enable Markdown parsing
        }
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print("Telegram message sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def main():
    session = get_session()
    conn = None
    try:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(hours=24)
        print(f"Current time: {now}")
        print(f"Cutoff time: {cutoff}")

        login(session)

        notices_html = fetch_notices(session)
        jobs_html = fetch_jobs(session)

        recent_notices = extract_all_notices(notices_html, cutoff, ist)
        recent_jobs = extract_recent_jobs(jobs_html, cutoff, ist)

        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            stored_hashes = get_recent_hashes(conn)

            new_notice_hashes = set()
            for message, notice_hash in recent_notices:
                if notice_hash not in stored_hashes:
                    send_telegram_message(f"📢 *New Notice on TNP Website:*\n{message}")
                    new_notice_hashes.add(notice_hash)
                else:
                    print("Notice already sent. Skipping.")

            new_job_hashes = set()
            for message, job_hash in recent_jobs:
                if job_hash not in stored_hashes:
                    send_telegram_message(f"📢 *New Job Listing on TNP Website:*\n{message}")
                    new_job_hashes.add(job_hash)
                else:
                    print("Job listing already sent. Skipping.")

            update_hashes(conn, new_notice_hashes.union(new_job_hashes))
            cutoff_for_cleanup = now - timedelta(days=7)  # Keep hashes for 7 days
            cleanup_hashes(conn, cutoff_for_cleanup)

    except Exception as e:
        error_message = f"❌ *Error in TNP Monitor:*\n{e}"
        print(error_message)
        try:
            send_telegram_message(error_message)
        except Exception as send_error:
            print(f"Failed to send error notification: {send_error}")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
