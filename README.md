# TNP Monitor API

A Flask-based API that monitors the Training and Placement (TNP) portal for new job postings and notices, sending notifications to Telegram.

## Features

- 🔄 **24/7 Monitoring**: Automatically checks for new jobs and notices every 30 minutes
- 📱 **Telegram Integration**: Sends notifications to Telegram channel/group
- 🗄️ **Database Storage**: Uses PostgreSQL to track processed items and avoid duplicates
- 🏥 **Health Checks**: Built-in health check endpoints to keep the app alive on Render
- 📊 **Status Monitoring**: API endpoints to check job status and health
- 🔧 **Manual Trigger**: Ability to manually trigger the monitoring job

## API Endpoints

- `GET /` - Home page with API information
- `GET /health` - Health check endpoint (used by cron jobs)
- `GET /ping` - Simple ping endpoint
- `GET /status` - Get current job status and environment info
- `POST /run` - Manually trigger the monitoring job

## Environment Variables

Create a `.env` file or set these environment variables in Render:

```env
TP_USERNAME=your_tnp_username
TP_PASSWORD=your_tnp_password
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
DATABASE_URL=your_postgresql_database_url
```

## Local Development

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your credentials
4. Run the application:
   ```bash
   python app.py
   ```

## Deployment on Render

### Step 1: Prepare Your Repository

1. Make sure all files are committed to your Git repository
2. Ensure you have the following files:
   - `app.py` (main Flask application)
   - `requirements.txt` (Python dependencies)
   - `Procfile` (tells Render how to run the app)
   - `runtime.txt` (Python version)

### Step 2: Deploy on Render

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New +" and select "Web Service"
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `tnp-monitor-api` (or your preferred name)
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: Free (for testing)

### Step 3: Set Environment Variables

In your Render service dashboard, go to "Environment" and add these variables:

- `TP_USERNAME`: Your TNP portal username
- `TP_PASSWORD`: Your TNP portal password
- `TELEGRAM_BOT_TOKEN`: Your Telegram bot token
- `TELEGRAM_CHAT_ID`: Your Telegram chat/group ID
- `DATABASE_URL`: Your PostgreSQL database URL

### Step 4: Set Up Database (Optional but Recommended)

1. Create a new PostgreSQL database on Render
2. Copy the database URL and set it as `DATABASE_URL` environment variable
3. The app will automatically create the required tables

### Step 5: Keep the App Alive

Since Render's free tier has a 15-minute inactivity timeout, you need to keep the app alive:

#### Option 1: Use cron-job.org (Recommended)

1. Go to [cron-job.org](https://cron-job.org/)
2. Create an account and add a new cron job
3. Set the URL to: `https://your-app-name.onrender.com/health`
4. Set the interval to every 5 minutes
5. Save the cron job

#### Option 2: Use UptimeRobot

1. Go to [UptimeRobot](https://uptimerobot.com/)
2. Create a new monitor
3. Set the URL to: `https://your-app-name.onrender.com/health`
4. Set the check interval to 5 minutes

## How It Works

1. **Scheduler**: The app uses APScheduler to run the monitoring job every 30 minutes
2. **Login**: Authenticates with the TNP portal using your credentials
3. **Scraping**: Fetches notices and job postings from the portal
4. **Deduplication**: Uses database hashes to avoid sending duplicate notifications
5. **Notifications**: Sends new items to Telegram
6. **Health Checks**: Internal scheduler pings the health endpoint every 5 minutes

## Monitoring and Logs

- Check the `/status` endpoint to see job status
- View logs in the Render dashboard
- Monitor error counts and last run times

## Troubleshooting

### Common Issues

1. **App goes to sleep**: Make sure you've set up the cron job to ping `/health`
2. **Login failures**: Check your TNP credentials
3. **Telegram errors**: Verify your bot token and chat ID
4. **Database errors**: Ensure your DATABASE_URL is correct

### Debug Endpoints

- `/status` - Check if all environment variables are set
- `/run` - Manually trigger a job to test functionality

## Security Notes

- Never commit your `.env` file to version control
- Use environment variables for all sensitive data
- Consider using a paid Render plan for production use

## License

This project is for educational purposes. Please respect the TNP portal's terms of service.
