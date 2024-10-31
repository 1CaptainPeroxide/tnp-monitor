import os
import hashlib
import time
import datetime
import pytz
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"
}

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    """
    Logs into the TNP website and checks if login was successful.
    """
    try:
        # Get the login page
        response = session.get(LOGIN_URL)
        response.raise_for_status()
        print("Fetched login page successfully.")

        # Prepare login data
        login_data = {
            'identity': TP_USERNAME,
            'password': TP_PASSWORD,
            'submit': 'Login'
        }

        # Attempt to login
        login_response = session.post(LOGIN_URL, data=login_data)
        login_response.raise_for_status()

        # Parse the login response to check for any error messages
        soup = BeautifulSoup(login_response.text, 'html.parser')
        error_message = soup.find(id="infoMessage")

        # Check if the page still shows a login form or error message, indicating failure
        if "Logout" not in login_response.text and (error_message or "login" in login_response.text.lower()):
            error_text = error_message.get_text(strip=True) if error_message else "Unknown login error."
            raise Exception(f"Login failed. Server message: {error_text}")

        print("Logged in successfully.")

    except Exception as e:
        raise Exception(f"An error occurred during login: {e}")

def fetch_notices(session):
    """
    Fetches the notices page and returns the HTML content.
    """
    try:
        response = session.get(NOTICES_URL)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"An error occurred while fetching notices: {e}")

def fetch_jobs(session):
    """
    Fetches the jobs page and returns the HTML content.
    """
    try:
        response = session.get("https://tp.bitmesra.co.in/index")
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"An error occurred while fetching job listings: {e}")

def compute_hash(content):
    """
    Computes the MD5 hash of the given content.
    """
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def parse_date(post_date_str):
    """
    Tries to parse the date string using multiple formats.
    """
    date_formats = ['%d/%m/%Y %H:%M %Z', '%d/%m/%Y']
    for fmt in date_formats:
        try:
            dt = datetime.datetime.strptime(post_date_str, fmt)
            if '%Z' in fmt:
                dt = dt.replace(tzinfo=pytz.timezone('Asia/Kolkata'))
            return dt.date()
        except ValueError:
            continue
    raise ValueError(f"time data '{post_date_str}' does not match any expected format")

def get_last_hashes(conn):
    """
    Retrieves all stored hashes from the database.
    """
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
    """
    Inserts new hashes into the database.
    """
    with conn.cursor() as cur:
        for new_hash in new_hashes:
            cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()

def extract_today_notices(content):
    """
    Parses the HTML content and extracts all notices from the current day.
    """
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        print("No notices table found.")
        return notices

    today = datetime.datetime.now().date()  # Today's date

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            # Extract the post date
            date_tag = row.find_all('td')[1]
            post_date_str = date_tag.get_text(strip=True)
            # Parse the date
            post_date = parse_date(post_date_str)
            if post_date != today:
                continue  # Skip notices not from today

            # Extract the notice title and URL
            title_tag = row.find('h6').find('a')
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            full_link = f"https://tp.bitmesra.co.in/{link}"

            # Construct the message
            message = f"Title: {title}\nLink: {full_link}\nDate: {post_date_str}"
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))
        except Exception as e:
            print(f"Failed to extract a notice: {e}")
    return notices

def extract_today_jobs(content):
    """
    Parses the HTML content to extract all job listings from the current day.
    """
    jobs = []
    soup = BeautifulSoup(content, 'html.parser')
    job_table = soup.find('table', {'id': 'job-listings'})
    if not job_table:
        print("No job listings table found.")
        return jobs

    today = datetime.datetime.now().date()  # Today's date

    for row in job_table.find('tbody').find_all('tr'):
        try:
            # Extract the post date
            date_tag = row.find_all('td')[1]
            post_date_str = date_tag.get_text(strip=True)
            # Parse the date
            post_date = parse_date(post_date_str)
            if post_date != today:
                continue  # Skip job listings not from today

            # Extract the company name and link to apply
            company_name = row.find_all('td')[0].get_text(strip=True)
            apply_link_tag = row.find_all('a')
            apply_link = "No link available"
            for link_tag in apply_link_tag:
                if "Apply" in link_tag.get_text():
                    apply_link = f"https://tp.bitmesra.co.in/{link_tag['href']}"
                    break

            # Construct the message
            message = f"New Job Listing:\nCompany: {company_name}\nDate: {post_date_str}\nApply here: {apply_link}"
            job_hash = compute_hash(message)
            jobs.append((message, job_hash))
        except Exception as e:
            print(f"Failed to extract a job listing: {e}")
    return jobs

def send_whatsapp_message(message):
    """
    Sends a WhatsApp message using Twilio to your number and a list of friends' numbers.
    Adds a delay between messages to avoid rate limits.
    """
    try:
        # Send to your WhatsApp number
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=YOUR_WHATSAPP_NUMBER
        )
        print("WhatsApp message sent to your number successfully.")

        # Send to each friend's WhatsApp number with a delay to avoid rate limiting
        for friend_number in FRIENDS_WHATSAPP_NUMBERS:
            friend_number = friend_number.strip()  # Clean up any extra spaces
            if friend_number:
                time.sleep(1.1)  # 1.1 seconds delay to stay within Twilio's 1 rps limit
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
        # Log into the website
        login(session)

        # Fetch the notices and jobs pages
        notices_html = fetch_notices(session)
        jobs_html = fetch_jobs(session)

        # Extract today's notices and jobs
        today_notices = extract_today_notices(notices_html)
        today_jobs = extract_today_jobs(jobs_html)

        # Initialize database connection for hash checking
        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            # Retrieve stored hashes
            stored_hashes = get_last_hashes(conn)

            # Process today's notices
            new_notice_hashes = set()
            for message, notice_hash in today_notices:
                if notice_hash not in stored_hashes:
                    send_whatsapp_message(f"📢 *New Notice on TNP Website:*\n{message}")
                    new_notice_hashes.add(notice_hash)

            # Process today's jobs
            new_job_hashes = set()
            for message, job_hash in today_jobs:
                if job_hash not in stored_hashes:
                    send_whatsapp_message(f"📢 *New Job Listing on TNP Website:*\n{message}")
                    new_job_hashes.add(job_hash)

            # Update hashes in the database
            update_hashes(conn, new_notice_hashes.union(new_job_hashes))

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
