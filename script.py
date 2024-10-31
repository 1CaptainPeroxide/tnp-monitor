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
NOTICES_URL = "https://tp.bitmesra.co.in/newsevents"  # Replace with actual notices URL

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"
}

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    # The login function remains the same
    ...

def fetch_notices(session):
    # Fetches the notices page and returns the HTML content.
    ...

def compute_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_last_hashes(conn, item_type):
    """
    Retrieves the last stored hashes for notices or jobs from the database.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL,
                item_type TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT hash FROM hashes WHERE item_type = %s;", (item_type,))
        return {row[0] for row in cur.fetchall()}  # Return as a set for quick lookup

def update_hashes(conn, new_hashes, item_type):
    """
    Inserts new hashes into the database.
    """
    with conn.cursor() as cur:
        for new_hash in new_hashes:
            cur.execute("INSERT INTO hashes (hash, item_type) VALUES (%s, %s);", (new_hash, item_type))
        conn.commit()

def extract_notices(content):
    # Extracts all notices on the page, returning them as a list of (title, link, post_date, hash) tuples.
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        return notices

    for row in notices_table.find('tbody').find_all('tr'):
        title_tag = row.find('h6').find('a')
        title = title_tag.get_text(strip=True)
        link = title_tag['href']
        full_link = f"https://tp.bitmesra.co.in/{link}"
        date_tag = row.find_all('td')[1]
        post_date = date_tag.get_text(strip=True)
        message = f"Title: {title}\nLink: {full_link}\nDate: {post_date}"
        notices.append((message, compute_hash(message)))
    return notices

def extract_jobs(content):
    # Extracts all job listings, returning as a list of (company_name, deadline, apply_link, hash) tuples.
    jobs = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table', {'id': 'job-listings'})
    if not job_table:
        return jobs

    for row in job_table.find('tbody').find_all('tr'):
        company_name = row.find_all('td')[0].get_text(strip=True)
        deadline = row.find_all('td')[1].get_text(strip=True)
        apply_link_tag = row.find_all('a')[1]
        apply_link = f"https://tp.bitmesra.co.in/{apply_link_tag['href']}" if apply_link_tag else "No link available"
        message = f"New Job Listing:\nCompany: {company_name}\nDeadline: {deadline}\nApply here: {apply_link}"
        jobs.append((message, compute_hash(message)))
    return jobs

def send_whatsapp_message(message):
    # Sends a WhatsApp message to you and your friends, with a delay to avoid rate limiting
    ...

def main():
    session = get_session()
    conn = None
    try:
        login(session)
        
        # Fetch notices and jobs
        notices_html = fetch_notices(session)
        jobs_html = session.get("https://tp.bitmesra.co.in/index").text  # Adjust URL as needed
        notices = extract_notices(notices_html)
        jobs = extract_jobs(jobs_html)
        
        # Database connection
        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            # Retrieve stored hashes
            last_notice_hashes = get_last_hashes(conn, 'notice')
            last_job_hashes = get_last_hashes(conn, 'job')

            # Check and send new notices
            new_notice_hashes = set()
            for message, notice_hash in notices:
                if notice_hash not in last_notice_hashes:
                    send_whatsapp_message(f"📢 *New Notice on TNP Website:*\n{message}")
                    new_notice_hashes.add(notice_hash)
            update_hashes(conn, new_notice_hashes, 'notice')

            # Check and send new jobs
            new_job_hashes = set()
            for message, job_hash in jobs:
                if job_hash not in last_job_hashes:
                    send_whatsapp_message(f"📢 *New Job Listing on TNP Website:*\n{message}")
                    new_job_hashes.add(job_hash)
            update_hashes(conn, new_job_hashes, 'job')

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
