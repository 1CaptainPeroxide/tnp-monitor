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

# Load environment variables from .env file
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

# HTTP headers to mimic a real browser
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"
}

def get_session():
    """
    Creates a new HTTP session with predefined headers.
    """
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    """
    Logs into the TNP portal using provided credentials.
    """
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
    """
    Fetches the HTML content of the notices page.
    """
    try:
        response = session.get(NOTICES_URL)
        response.raise_for_status()
        return response.text
    except Exception as e:
        raise Exception(f"An error occurred while fetching notices: {e}")

def compute_hash(content):
    """
    Computes an MD5 hash of the given content.
    """
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_recent_hashes(conn, cutoff):
    """
    Retrieves hashes from the database that are newer than the cutoff datetime.
    """
    with conn.cursor() as cur:
        # Create the hashes table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        # Select hashes within the retention period (e.g., last 7 days)
        cur.execute("SELECT hash FROM hashes WHERE timestamp >= %s;", (cutoff,))
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
    print("Hashes updated successfully.")

def cleanup_hashes(conn, cleanup_cutoff):
    """
    Deletes hashes older than the cleanup cutoff datetime to manage database size.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM hashes WHERE timestamp < %s;", (cleanup_cutoff,))
        conn.commit()
        print("Old hashes cleaned up successfully.")

def extract_all_notices(content, cutoff):
    """
    Extracts all notices from the HTML content, including jobs and general notices,
    that were posted within the last 24 hours.
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
            # Extract all 'td' elements
            td_list = row.find_all('td')
            if len(td_list) < 2:
                print(f"Row {idx + 1} does not have enough 'td' elements. Skipping.")
                continue

            # Extract the date from 'data-order' attribute
            date_td = td_list[1]
            data_order = date_td.get('data-order')
            if data_order:
                try:
                    # Parse 'data-order' as naive datetime (IST)
                    post_datetime = datetime.datetime.strptime(data_order, '%Y/%m/%d %H:%M:%S')
                except ValueError as ve:
                    print(f"Row {idx + 1}: Failed to parse date from data-order '{data_order}': {ve}")
                    continue
            else:
                # Fallback to parsing visible date text if 'data-order' is missing
                visible_date_text = date_td.get_text(strip=True)
                if visible_date_text.endswith(' IST'):
                    visible_date_text = visible_date_text[:-4].strip()
                try:
                    post_datetime = datetime.datetime.strptime(visible_date_text, '%d/%m/%Y %H:%M')
                except ValueError as ve:
                    print(f"Row {idx + 1}: Failed to parse date from visible text '{visible_date_text}': {ve}")
                    continue

            # Skip notices older than the cutoff (24 hours)
            if post_datetime < cutoff:
                print(f"Row {idx + 1}: Notice date {post_datetime} is older than cutoff {cutoff}. Skipping.")
                continue

            # Extract the notice title and URL
            h6_tag = row.find('h6')
            if not h6_tag:
                print(f"Row {idx + 1}: No 'h6' tag found. Skipping.")
                continue
            title_tag = h6_tag.find('a')
            if not title_tag:
                print(f"Row {idx + 1}: No 'a' tag found in 'h6'. Skipping.")
                continue
            title = title_tag.get_text(strip=True)
            link = title_tag.get('href', '')
            if link.startswith('/'):
                full_link = f"https://tp.bitmesra.co.in{link}"
            else:
                full_link = f"https://tp.bitmesra.co.in/{link}"

            # Capture additional description from 'small' tag
            small_tag = row.find('small')
            if small_tag:
                additional_info = small_tag.get_text(" ", strip=True)
            else:
                additional_info = ''

            # Determine the type of notice based on 'additional_info'
            if 'job' in additional_info.lower():
                message_type = "New Job Listing on TNP Website"
            else:
                message_type = "New Notice on TNP Website"

            # Construct the Telegram message
            message = (
                f"📢 *{message_type}:*\n"
                f"**Title:** {title}\n"
                f"**Link:** {full_link}\n"
                f"**Date:** {post_datetime.strftime('%d/%m/%Y %H:%M')}\n"
                f"**Details:** {additional_info}"
            )
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))
            print(f"Row {idx + 1}: Notice extracted and added.")

        except Exception as e:
            print(f"Row {idx + 1}: Failed to extract a notice: {e}")
            print(f"Row {idx + 1} HTML: {row}")
    return notices

def send_telegram_message(message):
    """
    Sends a message to the specified Telegram chat.
    """
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
        # Make 'now' naive by removing timezone info
        now_naive = now.replace(tzinfo=None)
        cutoff = now_naive - timedelta(hours=24)
        print(f"Current time (IST): {now_naive}")
        print(f"Cutoff time (24 hours ago): {cutoff}")

        # Log into the TNP portal
        login(session)

        # Fetch notices HTML
        notices_html = fetch_notices(session)

        # Extract recent notices
        recent_notices = extract_all_notices(notices_html, cutoff)
        print(f"Total recent notices extracted: {len(recent_notices)}")

        if DATABASE_URL:
            # Parse the DATABASE_URL
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], 
                user=result.username, 
                password=result.password,
                host=result.hostname, 
                port=result.port, 
                sslmode='require'
            )

            # Define cleanup cutoff for hashes (e.g., retain hashes for 7 days)
            cleanup_cutoff = now_naive - timedelta(days=7)
            print(f"Hash cleanup cutoff (7 days ago): {cleanup_cutoff}")

            # Retrieve recent hashes to prevent duplicates
            stored_hashes = get_recent_hashes(conn, cleanup_cutoff)
            print(f"Stored hashes retrieved: {len(stored_hashes)}")

            new_hashes = set()
            for message, notice_hash in recent_notices:
                if notice_hash not in stored_hashes:
                    send_telegram_message(message)
                    new_hashes.add(notice_hash)
                else:
                    print("Notice already sent. Skipping.")

            # Update the database with new hashes
            if new_hashes:
                update_hashes(conn, new_hashes)
            else:
                print("No new notices to update.")

            # Clean up old hashes
            cleanup_hashes(conn, cleanup_cutoff)

        else:
            print("DATABASE_URL not set. Cannot store or retrieve hashes.")

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
            print("Database connection closed.")

if __name__ == "__main__":
    main()
