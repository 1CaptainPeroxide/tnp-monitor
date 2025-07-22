# Deployment Checklist for TNP Monitor API

## Pre-Deployment Checklist

- [ ] All files are committed to Git repository
- [ ] `.env` file is NOT committed (it's in .gitignore)
- [ ] Environment variables are ready to be set in Render

## Required Files (Verify these exist)

- [ ] `app.py` - Main Flask application
- [ ] `requirements.txt` - Python dependencies
- [ ] `Procfile` - Tells Render how to run the app
- [ ] `runtime.txt` - Python version specification
- [ ] `README.md` - Documentation
- [ ] `.gitignore` - Excludes sensitive files

## Environment Variables to Set in Render

- [ ] `TP_USERNAME` - Your TNP portal username
- [ ] `TP_PASSWORD` - Your TNP portal password
- [ ] `TELEGRAM_BOT_TOKEN` - Your Telegram bot token
- [ ] `TELEGRAM_CHAT_ID` - Your Telegram chat/group ID
- [ ] `DATABASE_URL` - PostgreSQL database URL (optional but recommended)

## Render Deployment Steps

1. [ ] Go to [Render Dashboard](https://dashboard.render.com/)
2. [ ] Click "New +" → "Web Service"
3. [ ] Connect your GitHub repository
4. [ ] Configure service:
   - Name: `tnp-monitor-api`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python app.py`
   - Plan: Free
5. [ ] Set environment variables in Render dashboard
6. [ ] Deploy the service

## Post-Deployment Setup

### Database Setup (Optional)
- [ ] Create PostgreSQL database on Render
- [ ] Copy database URL to environment variables
- [ ] Verify database connection

### Keep App Alive Setup (Required for Free Tier)
- [ ] Go to [cron-job.org](https://cron-job.org/)
- [ ] Create account
- [ ] Add new cron job:
  - URL: `https://your-app-name.onrender.com/health`
  - Interval: Every 5 minutes
  - Method: GET
- [ ] Test the cron job

## Testing Your Deployment

- [ ] Visit `https://your-app-name.onrender.com/` - Should show API info
- [ ] Visit `https://your-app-name.onrender.com/health` - Should return healthy status
- [ ] Visit `https://your-app-name.onrender.com/status` - Should show job status
- [ ] Test manual job trigger: `POST https://your-app-name.onrender.com/run`

## Monitoring

- [ ] Check Render logs for any errors
- [ ] Monitor `/status` endpoint for job execution
- [ ] Verify Telegram notifications are working
- [ ] Check cron job is pinging the health endpoint

## Troubleshooting

### Common Issues:
- **App goes to sleep**: Ensure cron job is set up correctly
- **Login failures**: Check TNP credentials
- **Telegram errors**: Verify bot token and chat ID
- **Database errors**: Check DATABASE_URL format

### Debug Commands:
```bash
# Check app status
curl https://your-app-name.onrender.com/status

# Test health endpoint
curl https://your-app-name.onrender.com/health

# Manually trigger job
curl -X POST https://your-app-name.onrender.com/run
```

## Security Notes

- [ ] Never commit `.env` file
- [ ] Use environment variables for all secrets
- [ ] Consider upgrading to paid plan for production use
- [ ] Regularly rotate credentials

## Success Indicators

- [ ] App responds to health checks
- [ ] Jobs run every 30 minutes automatically
- [ ] New jobs/notices are sent to Telegram
- [ ] No duplicate notifications
- [ ] Error count stays low 