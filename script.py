import os
import time
import hashlib
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from twilio.rest import Client
from dotenv import load_dotenv
import psycopg2

# Load environment variables
load_dotenv()

TP_USERNAME = os.getenv('TP_USERNAME')
TP_PASSWORD = os.getenv('TP_PASSWORD')
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_NUMBER')
YOUR_WHATSAPP_NUMBER = os.getenv('YOUR_WHATSAPP_NUMBER')
DATABASE_URL = os.getenv('DATABASE_URL')

# Initialize Twilio client
client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

# URL of the TNP website
URL = "https://tp.bitmesra.co.in/"

def get_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # Uncomment to run headless
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Specify the Chrome binary location if needed
    chrome_options.binary_location = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    driver_path = "C:\\Users\\mohit\\Downloads\\chromedriver-win64\\chromedriver-win64\\chromedriver.exe"

    # Use Service to set the executable path
    service = Service(driver_path)
    return webdriver.Chrome(service=service, options=chrome_options)

def login(driver):
    driver.get(URL)
    
    try:
        # Locate the username field
        username_field = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.NAME, "identity"))
        )
        password_field = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.NAME, "password"))
        )
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "submit"))
        )

        # Enter credentials
        username_field.send_keys(TP_USERNAME)
        password_field.send_keys(TP_PASSWORD)
        login_button.click()
        print("Credentials entered and login attempted")

        # Wait for login to complete
        time.sleep(5)

    except Exception as e:
        print(f"An error occurred during login: {e}")

def fetch_latest_notification(driver):
    try:
        # Locate the notification table by ID
        notices_table = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "newseventsx1"))
        )
        print("Notification table found.")

        # Use XPath to directly locate the <a> tag within the first <tr> row
        notification_link = notices_table.find_element(By.XPATH, ".//tr[1]//a")
        notification_text = notification_link.text
        notification_url = notification_link.get_attribute("href")

        # Construct the full URL and formatted message
        full_url = f"{notification_url}"
        formatted_message = f"{notification_text}, Link: {full_url}"

        # Print and return the formatted message
        print("Formatted Message:", formatted_message)
        return formatted_message

    except Exception as e:
        print(f"An error occurred while fetching notifications: {e}")
        return None



def compute_hash(content):
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def send_whatsapp_message(message):
    client.messages.create(
        body=message,
        from_=TWILIO_WHATSAPP_NUMBER,
        to=YOUR_WHATSAPP_NUMBER
    )

def get_last_hash(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS hashes (id SERIAL PRIMARY KEY, hash TEXT);")
        cur.execute("SELECT hash FROM hashes ORDER BY id DESC LIMIT 1;")
        result = cur.fetchone()
        return result[0] if result else ''

def update_last_hash(conn, new_hash):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO hashes (hash) VALUES (%s);", (new_hash,))
        conn.commit()

def main():
    driver = get_driver()
    try:
        login(driver)
        notification_content = fetch_latest_notification(driver)

        if notification_content:
            # Compute the hash of the notification content
            new_hash = compute_hash(notification_content)

            # Connect to the database
            conn = psycopg2.connect(DATABASE_URL, sslmode='require')
            old_hash = get_last_hash(conn)

            # Check if the notification content has changed
            if new_hash != old_hash:
                # Send a WhatsApp message with the formatted notification content
                send_whatsapp_message(notification_content)
                print("New notification sent via WhatsApp.")

                # Update the hash in the database
                update_last_hash(conn, new_hash)
            else:
                print("No new notifications detected.")

            conn.close()

    except Exception as e:
        print(f"An error occurred: {e}")
        send_whatsapp_message(f"Error in TNP Monitor: {e}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
