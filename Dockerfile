# Use the official Python image
FROM python:3.9-slim

# Install essential system dependencies and tools
RUN apt-get update && \
    apt-get install -y wget unzip curl gnupg gcc g++ make libpq-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev zlib1g-dev libgl1-mesa-glx && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Download and install the latest Google Chrome stable version
RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && \
    apt-get update && \
    apt-get install -y ./google-chrome-stable_current_amd64.deb && \
    rm ./google-chrome-stable_current_amd64.deb

# Check installed Chrome version
RUN google-chrome --version || echo "Google Chrome failed to install."

# Dynamically fetch and install the compatible ChromeDriver version, with fallback
RUN CHROME_VERSION=$(google-chrome --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+') && \
    echo "Detected Chrome version: $CHROME_VERSION" && \
    CHROMEDRIVER_VERSION=$(curl -sS https://chromedriver.storage.googleapis.com/LATEST_RELEASE_$CHROME_VERSION || echo "114.0.5735.90") && \
    echo "Using ChromeDriver version: $CHROMEDRIVER_VERSION" && \
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
