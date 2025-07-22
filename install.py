#!/usr/bin/env python3
"""
Installation script for TNP Monitor API
This script helps install the correct dependencies based on your system.
"""

import os
import sys
import subprocess
import platform

def run_command(command):
    """Run a command and return success status"""
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {command}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {command}")
        print(f"Error: {e.stderr}")
        return False

def detect_system():
    """Detect the operating system"""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "darwin":
        return "macos"
    else:
        return "linux"

def install_dependencies():
    """Install dependencies based on the system"""
    system = detect_system()
    print(f"🔍 Detected system: {system}")
    
    # Try the main requirements first
    print("\n📦 Installing main dependencies...")
    if run_command("pip install -r requirements.txt"):
        print("✅ Main dependencies installed successfully!")
        return True
    
    # If that fails, try the Windows alternative
    if system == "windows":
        print("\n🔄 Main installation failed. Trying Windows-compatible version...")
        if run_command("pip install -r requirements-windows.txt"):
            print("✅ Windows-compatible dependencies installed successfully!")
            print("\n💡 Note: Using SQLite version for local development.")
            print("   For production deployment on Render, use the PostgreSQL version.")
            return True
    
    print("\n❌ Installation failed. Please try manually:")
    print("   pip install requests beautifulsoup4 python-dotenv Flask APScheduler pytz")
    
    if system == "windows":
        print("\n   For Windows users, you can also try:")
        print("   pip install -r requirements-windows.txt")
    
    return False

def create_env_template():
    """Create a template .env file"""
    env_template = """# TNP Monitor API Environment Variables
# Copy this file to .env and fill in your actual values

# TNP Portal Credentials
TP_USERNAME=your_tnp_username
TP_PASSWORD=your_tnp_password

# Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Database Configuration (for production)
# DATABASE_URL=postgresql://username:password@host:port/database

# SQLite Database Path (for local development)
SQLITE_DB_PATH=tnp_monitor.db
"""
    
    if not os.path.exists('.env'):
        with open('.env', 'w') as f:
            f.write(env_template)
        print("✅ Created .env template file")
        print("📝 Please edit .env with your actual credentials")
    else:
        print("ℹ️  .env file already exists")

def main():
    """Main installation function"""
    print("🚀 TNP Monitor API - Installation Script")
    print("=" * 50)
    
    # Check Python version
    python_version = sys.version_info
    if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
        print("❌ Python 3.8 or higher is required")
        print(f"   Current version: {python_version.major}.{python_version.minor}")
        return
    
    print(f"✅ Python version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    # Install dependencies
    if install_dependencies():
        # Create environment template
        create_env_template()
        
        print("\n🎉 Installation completed!")
        print("\n📋 Next steps:")
        print("1. Edit .env file with your credentials")
        print("2. Run: python app.py (for PostgreSQL version)")
        print("   or: python app-sqlite.py (for SQLite version)")
        print("3. Visit: http://localhost:5000")
        
        print("\n🔧 For deployment on Render:")
        print("1. Use the PostgreSQL version (app.py)")
        print("2. Set up environment variables in Render dashboard")
        print("3. Set up cron job at cron-job.org")
        
    else:
        print("\n❌ Installation failed. Please check the errors above.")

if __name__ == "__main__":
    main() 