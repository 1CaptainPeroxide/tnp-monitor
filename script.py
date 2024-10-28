import os
import hashlib
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

        # Full response text to debug
        print("Full login response text:", login_response.text)  # Print entire response for debugging

        # Parse the login response to check for any error messages
        soup = BeautifulSoup(login_response.text, 'html.parser')
        error_message = soup.find(id="infoMessage")  # Check if an error message is displayed

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
    Parses the HTML content and extracts the latest notice title and link.
    """
    soup = BeautifulSoup(content, 'html.parser')
    
    # Find the table with id 'newsevents'
    notices_table = soup.find('table', {'id': 'newsevents'})
    if not notices_table:
        return "No notices table found."

    # Get the first row from the tbody, which represents the latest notice
    latest_row = notices_table.find('tbody').find('tr')
    if not latest_row:
        return "No notices found."

    # Extract the notice title and URL
    title_tag = latest_row.find('h6').find('a')
    title = title_tag.get_text(strip=True)
    link = title_tag['href']
    full_link = f"https://tp.bitmesra.co.in/{link}"  # Construct full URL
    
    # Extract the post date
    date_tag = latest_row.find_all('td')[1]
    post_date = date_tag.get_text(strip=True)

    # Construct the message
    message = f"Title: {title}\nLink: {full_link}\nDate: {post_date}"
    return message

def extract_latest_job(content):
    """
    Parses the HTML content to extract the latest job listing details.
    """
    soup = BeautifulSoup(content, 'html.parser')
    
    # Find the table with id 'job-listings'
    job_table = soup.find('table', {'id': 'job-listings'})
    if not job_table:
        return "No job listings table found."

    # Get the first row from tbody, which represents the latest job listing
    latest_row = job_table.find('tbody').find('tr')
    if not latest_row:
        return "No job listings found."

    # Extract the company name, deadline, and link to apply
    company_name = latest_row.find_all('td')[0].get_text(strip=True)
    deadline = latest_row.find_all('td')[1].get_text(strip=True)
    apply_link_tag = latest_row.find_all('a')[1]  # Adjusted to find the second link in the row for "View & Apply"
    apply_link = f"https://tp.bitmesra.co.in/{apply_link_tag['href']}" if apply_link_tag else "No link available"

    # Construct the message
    message = f"New Job Listing:\nCompany: {company_name}\nDeadline: {deadline}\nApply here: {apply_link}"
    return message

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
    session = get_session()
    conn = None  # Define conn at the start to ensure it's accessible in finally
    try:
        # Log into the website
        login(session)

        # Fetch the notices page
        notices_html = fetch_notices(session)
        new_notice_message = extract_latest_notice(notices_html)

        # Fetch the job listings page
        jobs_html = session.get("https://tp.bitmesra.co.in/index").text  # Adjust URL as needed
        new_job_message = extract_latest_job(jobs_html)

        # Initialize database connection for hash checking
        if DATABASE_URL:
            result = urlparse(DATABASE_URL)
            conn = psycopg2.connect(
                database=result.path[1:], user=result.username, password=result.password,
                host=result.hostname, port=result.port, sslmode='require'
            )

            # Hash and store notices if new
            notice_hash = compute_hash(new_notice_message)
            if notice_hash != get_last_hash(conn):
                send_whatsapp_message(f"📢 *New Notice on TNP Website:*\n{new_notice_message}")
                update_last_hash(conn, notice_hash)

            # Hash and store job listings if new
            job_hash = compute_hash(new_job_message)
            cur = conn.cursor()
            cur.execute("SELECT hash FROM hashes WHERE hash = %s LIMIT 1;", (job_hash,))
            if not cur.fetchone():
                send_whatsapp_message(f"📢 *New Job Listing on TNP Website:*\n{new_job_message}")
                update_last_hash(conn, job_hash)
            cur.close()

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
