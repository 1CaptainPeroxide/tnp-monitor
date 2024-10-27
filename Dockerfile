# Use a lightweight Python image
FROM python:3.9-slim

# Install essential packages and add Google Chrome's signing key and repository
RUN apt-get update && \
    apt-get install -y wget gnupg unzip curl && \
    # Add Google Chrome’s public key
    curl -fsSL https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    # Add Google Chrome's repository
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    # Install the latest stable version of Chrome
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Specify the compatible version of ChromeDriver
RUN CHROMEDRIVER_VERSION=$(curl -sS chromedriver.storage.googleapis.com/LATEST_RELEASE) && \
    wget -N https://chromedriver.storage.googleapis.com/$CHROMEDRIVER_VERSION/chromedriver_linux64.zip -P /tmp && \
    unzip /tmp/chromedriver_linux64.zip -d /usr/bin/ && \
    rm /tmp/chromedriver_linux64.zip

# Set environment variable for display to enable headless mode
ENV DISPLAY=:99

# Set the working directory in the container
WORKDIR /app

# Copy the project files into the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Command to run the script
CMD ["python", "script.py"]
