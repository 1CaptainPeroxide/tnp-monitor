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
YOUR_WHATSAPP_NUMBER = os.getenv('YOUR_WHATSAPP_NUMBER')
DATABASE_URL = os.getenv('DATABASE_URL')

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
    """Logs into the TNP website and checks if login was successful."""
    try:
        response = session.get(LOGIN_URL)
        response.raise_for_status()
        login_data = {'identity': TP_USERNAME, 'password': TP_PASSWORD, 'submit': 'Login'}
        login_response = session.post(LOGIN_URL, data=login_data)
        login_response.raise_for_status()
        soup = BeautifulSoup(login_response.text, 'html.parser')
        if "Logout" not in login_response.text:
            raise Exception("Login failed.")
        print("Logged in successfully.")
    except Exception as e:
        raise Exception(f"An error occurred during login: {e}")

def fetch_notices(session):
    """Fetches the notices page and returns the HTML content."""
    try:
        response = session.get(NOTICES_URL)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"An error occurred while fetching notices: {e}")

def compute_hash(content):
    """Computes the MD5 hash of the given content."""
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_recent_hashes(conn, cutoff):
    """Retrieves all stored hashes from the database that are newer than the cutoff time."""
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
    """Inserts new hashes into the database."""
    with conn.cursor() as cur:
        for new_hash in new_hashes:
            cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()

def cleanup_hashes(conn, cutoff):
    """Deletes hashes older than the cutoff time (24 hours)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hashes WHERE timestamp < %s;", (cutoff,))
        conn.commit()
        print("Old hashes cleaned up successfully.")

def extract_recent_notices(content, cutoff, ist):
    """
    Parses the HTML content and extracts all notices from the past 24 hours based on the IST timezone.
    """
    notices = []
    soup = BeautifulSoup(content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        print("No notices table found.")
        return notices

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            # Extract title and link
            title_tag = row.find('h6').find('a')
            if not title_tag:
                print("No title found in this row.")
                continue
            title = title_tag.get_text(strip=True)
            link = title_tag['href']
            full_link = f"https://tp.bitmesra.co.in/{link}"

            # Extract date from 'data-order'
            date_td = row.find_all('td')[1]
            data_order = date_td.get('data-order')
            if not data_order:
                print("No 'data-order' attribute found for date.")
                continue
            
            post_datetime = datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S')
            post_datetime = ist.localize(post_datetime)

            # Skip notices older than cutoff
            if post_datetime < cutoff:
                continue

            # Construct message
            message = f"Title: {title}\nLink: {full_link}\nDate: {post_datetime.strftime('%d/%m/%Y %H:%M')}"
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))

        except Exception as e:
            print(f"Failed to extract a notice: {e}")

    return notices

def main():
    session = get_session()
    conn = None
    try:
        # Define IST timezone and cutoff time
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.datetime.now(ist)
        cutoff = now - timedelta(hours=24)

        # Log in and fetch notices
        login(session)
        notices_html = fetch_notices(session)

        # Extract recent notices
        recent_notices = extract_recent_notices(notices_html, cutoff, ist)

        # Initialize database connection for hash checking
        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            # Retrieve stored hashes and process recent notices
            stored_hashes = get_recent_hashes(conn, cutoff)
            new_notice_hashes = set()
            for message, notice_hash in recent_notices:
                if notice_hash not in stored_hashes:
                    print(f"New Notice:\n{message}")
                    new_notice_hashes.add(notice_hash)

            # Update database with new hashes and clean up old ones
            update_hashes(conn, new_notice_hashes)
            cleanup_hashes(conn, cutoff)

    except Exception as e:
        print(f"Error in TNP Monitor: {e}")

    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
