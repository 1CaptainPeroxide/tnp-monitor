# Use the official Python image
FROM python:3.9-slim

# Install essential system dependencies and tools
RUN apt-get update && \
    apt-get install -y wget unzip curl gnupg gcc g++ make libpq-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev zlib1g-dev libgl1-mesa-glx && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Add Google Chrome repository and install the latest version of Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# Dynamically download ChromeDriver to match the installed Chrome version
RUN CHROME_VERSION=$(google-chrome --version | grep -oP '\d+\.\d+\.\d+') && \
    CHROMEDRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION) && \
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
