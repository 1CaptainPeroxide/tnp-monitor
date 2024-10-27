# Use the official Python image
FROM python:3.9-slim

# Install essential system dependencies
RUN apt-get update && \
    apt-get install -y wget unzip curl gnupg gcc g++ make libpq-dev libffi-dev libssl-dev libxml2-dev libxslt1-dev zlib1g-dev libgl1-mesa-glx && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install a specific compatible version of Chrome (version 114)
RUN wget https://dl.google.com/linux/chrome/deb/pool/main/g/google-chrome-stable/google-chrome-stable_114.0.5735.90-1_amd64.deb && \
    apt-get update && \
    apt-get install -y ./google-chrome-stable_114.0.5735.90-1_amd64.deb && \
    rm ./google-chrome-stable_114.0.5735.90-1_amd64.deb

# Install ChromeDriver version 114 to match Chrome version 114
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
