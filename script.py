import os
import hashlib
import time
import requests
from bs4 import BeautifulSoup
from twilio.rest import Client
from dotenv import load_dotenv
import psycopg2
from urllib.parse import urlparse

# Load environment variables
load_dotenv()

# Environment Variables
TP_USERNAME = os.getenv('TP_USERNAME')
TP_PASSWORD = os.getenv('TP_PASSWORD')
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')
YOUR_WHATSAPP_NUMBER = os.getenv('YOUR_WHATSAPP_NUMBER')
DATABASE_URL = os.getenv('DATABASE_URL')

# Load Friends' WhatsApp numbers as a list
FRIENDS_WHATSAPP_NUMBERS = os.getenv('FRIENDS_WHATSAPP_NUMBERS', '').split(',')

# Initialize Twilio client
client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

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
        print("Fetched login page successfully.")
        
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

def initialize_database(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL,
                item_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS setup_status (
                id SERIAL PRIMARY KEY,
                initialized BOOLEAN DEFAULT FALSE
            );
        """)
        cur.execute("SELECT initialized FROM setup_status LIMIT 1;")
        result = cur.fetchone()
        if not result:
            cur.execute("INSERT INTO setup_status (initialized) VALUES (FALSE);")
            conn.commit()
        return result[0] if result else False

def set_initialization_complete(conn):
    with conn.cursor() as cur:
        cur.execute("UPDATE setup_status SET initialized = TRUE;")
        conn.commit()

def get_recent_hashes(conn, item_type, limit=5):
    with conn.cursor() as cur:
        cur.execute("SELECT hash FROM hashes WHERE item_type = %s ORDER BY timestamp DESC LIMIT %s;", (item_type, limit))
        results = cur.fetchall()
        return set(row[0] for row in results)

def store_hashes(conn, hashes, item_type):
    with conn.cursor() as cur:
        for hash_value in hashes:
            cur.execute("INSERT INTO hashes (hash, item_type) VALUES (%s, %s);", (hash_value, item_type))
        conn.commit()

def extract_all_notices(content):
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        print("No notices table found.")
        return notices

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            title_tag = row.find('h6').find('a')
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            full_link = f"https://tp.bitmesra.co.in/{link}"
            date_tag = row.find_all('td')[1]
            post_date = date_tag.get_text(strip=True)
            message = f"Title: {title}\nLink: {full_link}\nDate: {post_date}"
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))
        except Exception as e:
            print(f"Failed to extract a notice: {e}")
    return notices

def extract_all_jobs(content):
    jobs = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table', {'id': 'job-listings'})
    if not job_table:
        print("No job listings table found.")
        return jobs

    for row in job_table.find('tbody').find_all('tr'):
        try:
            company_name = row.find_all('td')[0].get_text(strip=True)
            deadline = row.find_all('td')[1].get_text(strip=True)
            apply_link_tag = row.find_all('a')[1]
            apply_link = f"https://tp.bitmesra.co.in/{apply_link_tag['href']}" if apply_link_tag else "No link available"
            message = f"New Job Listing:\nCompany: {company_name}\nDeadline: {deadline}\nApply here: {apply_link}"
            job_hash = compute_hash(message)
            jobs.append((message, job_hash))
        except Exception as e:
            print(f"Failed to extract a job listing: {e}")
    return jobs

def send_whatsapp_message(message):
    try:
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=YOUR_WHATSAPP_NUMBER
        )
        print("WhatsApp message sent to your number successfully.")

        for friend_number in FRIENDS_WHATSAPP_NUMBERS:
            friend_number = friend_number.strip()
            if friend_number:
                time.sleep(1.1)
                client.messages.create(
                    body=message,
                    from_=TWILIO_WHATSAPP_NUMBER,
                    to=friend_number
                )
                print(f"WhatsApp message sent to {friend_number} successfully.")
    except Exception as e:
        raise Exception(f"Failed to send WhatsApp message: {e}")

def main():
    session = get_session()
    conn = None
    try:
        login(session)

        notices_html = fetch_notices(session)
        jobs_html = fetch_jobs(session)

        notices = extract_all_notices(notices_html)
        jobs = extract_all_jobs(jobs_html)

        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            initialized = initialize_database(conn)

            # Retrieve recent hashes for notices and jobs
            recent_notice_hashes = get_recent_hashes(conn, 'notice')
            recent_job_hashes = get_recent_hashes(conn, 'job')

            if not initialized:
                # Store initial set of hashes (limit to the latest 5 notices/jobs)
                store_hashes(conn, [hash_value for _, hash_value in notices[:5]], 'notice')
                store_hashes(conn, [hash_value for _, hash_value in jobs[:5]], 'job')
                set_initialization_complete(conn)
                print("Database initialized with recent notices and jobs.")
            else:
                # Send new notices
                new_notice_hashes = set()
                for message, notice_hash in notices:
                    if notice_hash not in recent_notice_hashes:
                        send_whatsapp_message(f"📢 *New Notice on TNP Website:*\n{message}")
                        new_notice_hashes.add(notice_hash)
                store_hashes(conn, new_notice_hashes, 'notice')

                # Send new job listings
                new_job_hashes = set()
                for message, job_hash in jobs:
                    if job_hash not in recent_job_hashes:
                        send_whatsapp_message(f"📢 *New Job Listing on TNP Website:*\n{message}")
                        new_job_hashes.add(job_hash)
                store_hashes(conn, new_job_hashes, 'job')

    except Exception as e:
        error_message = f"❌ *Error in TNP Monitor:*\n{e}"
        print(error_message)
        try:
            send_whatsapp_message(error_message)
        except Exception as send_error:
            print(f"Failed to send error notification: {send_error}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
