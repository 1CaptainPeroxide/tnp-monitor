# Use a lightweight Python image
FROM python:3.9-slim

# Install essential tools and dependencies
RUN apt-get update && \
    apt-get install -y wget gnupg unzip curl gcc g++ make python3-dev libpq-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev zlib1g-dev libgl1-mesa-glx && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Add Google Chrome's signing key and repository, then install Google Chrome (version 114)
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable=114.0.5735.90-1 && \
    rm -rf /var/lib/apt/lists/*

# Download ChromeDriver version 114 to match Google Chrome version 114
RUN wget -N https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip -P /tmp && \
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
