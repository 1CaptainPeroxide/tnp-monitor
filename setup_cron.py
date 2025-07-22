#!/usr/bin/env python3
"""
Helper script to generate the cron job URL for keeping the TNP Monitor API alive on Render.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def generate_cron_url():
    """Generate the cron job URL for health checks"""
    
    # Get the app name from environment or prompt user
    app_name = os.getenv('RENDER_APP_NAME')
    
    if not app_name:
        print("🔧 TNP Monitor API - Cron Job Setup")
        print("=" * 50)
        print("\nTo keep your app alive on Render's free tier, you need to set up a cron job.")
        print("\nFollow these steps:")
        print("\n1. Go to https://cron-job.org/")
        print("2. Create an account")
        print("3. Add a new cron job")
        print("4. Use the URL below:")
        
        app_name = input("\nEnter your Render app name (e.g., tnp-monitor-api): ").strip()
        
        if not app_name:
            print("❌ App name is required!")
            return
    
    # Generate the health check URL
    health_url = f"https://{app_name}.onrender.com/health"
    
    print(f"\n✅ Use this URL for your cron job:")
    print(f"   {health_url}")
    print(f"\n📋 Cron job settings:")
    print(f"   - Interval: Every 5 minutes")
    print(f"   - Method: GET")
    print(f"   - Timeout: 30 seconds")
    
    print(f"\n🔗 Alternative services:")
    print(f"   - UptimeRobot: https://uptimerobot.com/")
    print(f"   - Pingdom: https://www.pingdom.com/")
    print(f"   - StatusCake: https://www.statuscake.com/")
    
    print(f"\n📊 Monitor your app:")
    print(f"   - Status: https://{app_name}.onrender.com/status")
    print(f"   - Health: https://{app_name}.onrender.com/health")
    print(f"   - Manual run: POST https://{app_name}.onrender.com/run")

if __name__ == "__main__":
    generate_cron_url() 