import os
import hashlib
import datetime
from datetime import timedelta
import pytz
import requests
from bs4 import BeautifulSoup
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; TNPMonitor/1.0)"
}

def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session

def login(session):
    response = session.get(LOGIN_URL)
    response.raise_for_status()

    login_data = {'identity': TP_USERNAME, 'password': TP_PASSWORD, 'submit': 'Login'}
    login_response = session.post(LOGIN_URL, data=login_data)
    login_response.raise_for_status()

    if "Logout" not in login_response.text:
        raise Exception("Login failed, check credentials and website status.")

def fetch_notices(session):
    response = session.get(NOTICES_URL)
    response.raise_for_status()
    return response.text

def compute_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def process_notices(html_content, ist):
    soup = BeautifulSoup(html_content, 'html.parser')
    notices_table = soup.find('table', {'id': 'newsevents'})
    notices = []

    for row in notices_table.find('tbody').find_all('tr'):
        try:
            title_cell = row.find('h6').find('a')
            date_cell = row.find('td', class_="sorting_1")
            
            title = title_cell.text.strip()
            url = f"https://tp.bitmesra.co.in/{title_cell['href']}"
            date_str = date_cell['data-order']
            post_datetime = datetime.datetime.strptime(date_str, '%Y/%m/%d %H:%M:%S')
            post_datetime = ist.localize(post_datetime)
            
            if datetime.datetime.now(ist) - post_datetime > timedelta(hours=24):
                continue  # Skip notices older than 24 hours

            message = f"Title: {title}\nLink: {url}\nDate: {post_datetime.strftime('%d/%m/%Y %H:%M IST')}"
            notice_hash = compute_hash(message)
            notices.append((message, notice_hash))

        except Exception as e:
            print(f"Failed to extract a notice due to an error: {e}")

    return notices

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
    response = requests.post(url, data=payload)
    response.raise_for_status()

def main():
    session = get_session()
    login(session)
    ist = pytz.timezone('Asia/Kolkata')
    
    notices_html = fetch_notices(session)
    notices = process_notices(notices_html, ist)

    for message, _ in notices:
        send_telegram_message(message)

if __name__ == "__main__":
    main()
