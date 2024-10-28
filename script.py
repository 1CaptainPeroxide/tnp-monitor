import os
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from twilio.rest import Client
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

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

# Initialize Twilio client
client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

# URL Configuration
LOGIN_URL = "https://tp.bitmesra.co.in/login"  # Replace with the actual login URL
NOTICES_URL = "https://tp.bitmesra.co.in/notices"  # Replace with the actual notices URL

# Headers (Optional: Modify if needed)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"
}

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    """
    Logs into the TNP website using the provided credentials.
    """
    try:
        # Fetch the login page to get any necessary tokens (if required)
        response = session.get(LOGIN_URL)
        response.raise_for_status()

        # Parse the login page for CSRF tokens or other hidden fields (if any)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Example: Extract CSRF token (Modify based on actual form)
        csrf_token = soup.find('input', {'name': 'csrf_token'})['value'] if soup.find('input', {'name': 'csrf_token'}) else ''

        # Prepare login data
        login_data = {
            'username': TP_USERNAME,
            'password': TP_PASSWORD,
            'csrf_token': csrf_token  # Include if required
        }

        # Submit the login form
        login_response = session.post(LOGIN_URL, data=login_data)
        login_response.raise_for_status()

        # Verify login by checking the presence of a logout link or user dashboard
        if "Logout" not in login_response.text:
            raise Exception("Login failed. Please check your credentials or the login process.")

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

def compute_hash(content):
    """
    Computes the MD5 hash of the given content.
    """
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def get_last_hash(conn):
    """
    Retrieves the last stored hash from the database.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS hashes (
                id SERIAL PRIMARY KEY,
                hash TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("SELECT hash FROM hashes ORDER BY id DESC LIMIT 1;")
        result = cur.fetchone()
        return result[0] if result else ''

def update_last_hash(conn, new_hash):
    """
    Inserts the new hash into the database.
    """
    with conn.cursor() as cur:
        cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()

def extract_latest_notice(content):
    """
    Parses the HTML content and extracts the latest notice.
    Modify the selectors based on the actual HTML structure of the notices page.
    """
    soup = BeautifulSoup(content, 'html.parser')
    # Example: Assuming notices are within <div class="notice">
    notices = soup.find_all('div', class_='notice')
    if not notices:
        return "No notices found."

    latest_notice = notices[0].get_text(strip=True)
    return latest_notice

def send_whatsapp_message(message):
    """
    Sends a WhatsApp message using Twilio.
    """
    try:
        client.messages.create(
            body=message,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=YOUR_WHATSAPP_NUMBER
        )
        print("WhatsApp message sent successfully.")
    except Exception as e:
        raise Exception(f"Failed to send WhatsApp message: {e}")

def main():
    # Initialize session
    session = get_session()

    try:
        # Log into the website
        login(session)

        # Fetch the notices page
        notices_html = fetch_notices(session)

        # Compute hash of the current content
        new_hash = compute_hash(notices_html)

        # Connect to the PostgreSQL database
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')

        # Retrieve the last stored hash
        old_hash = get_last_hash(conn)

        if new_hash != old_hash:
            # Content has changed
            latest_notice = extract_latest_notice(notices_html)
            message = f"📢 *New Update on TNP Website:*\n{latest_notice}"
            send_whatsapp_message(message)

            # Update the hash in the database
            update_last_hash(conn, new_hash)
        else:
            print("No changes detected.")

    except Exception as e:
        error_message = f"❌ *Error in TNP Monitor:*\n{e}"
        print(error_message)
        try:
            send_whatsapp_message(error_message)
        except Exception as send_error:
            print(f"Failed to send error notification: {send_error}")

    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
