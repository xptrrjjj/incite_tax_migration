#!/usr/bin/env python3
"""
Dashboard Launcher
=================

Simple launcher for the migration status dashboard.
Checks dependencies and provides helpful startup information.
"""

import sys
import subprocess
from pathlib import Path

def check_flask_installed():
    """Check if Flask is installed."""
    try:
        import flask
        return True
    except ImportError:
        return False

def install_flask():
    """Install Flask if missing."""
    print("Flask not found. Installing...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "flask>=2.3.0"])
        print("✅ Flask installed successfully")
        return True
    except subprocess.CalledProcessError:
        print("❌ Failed to install Flask")
        return False

def main():
    """Main launcher function."""
    print("🚀 Starting Migration Status Dashboard")
    print("=" * 50)
    
    # Check if database exists
    db_path = Path("migration_tracking.db")
    if not db_path.exists():
        print("⚠️  WARNING: No migration database found!")
        print("   Run a migration first to create data:")
        print("   python backup_only_migration.py --full")
        print()
    else:
        db_size = db_path.stat().st_size / (1024**2)  # MB
        print(f"✅ Database found: {db_size:.1f} MB")
    
    # Check Flask dependency
    if not check_flask_installed():
        print("📦 Installing Flask dependency...")
        if not install_flask():
            print("❌ Cannot start dashboard without Flask")
            print("   Try manually: pip install flask>=2.3.0")
            return
    
    print()
    print("🌐 Dashboard starting at: http://localhost:5000")
    print("🔄 Auto-refresh: Every 30 seconds")
    print("⏹️  Press Ctrl+C to stop")
    print("=" * 50)
    print()
    
    # Start dashboard
    try:
        from status_dashboard import app
        app.run(host='localhost', port=5000, debug=False)
    except ImportError as e:
        print(f"❌ Error importing dashboard: {e}")
        print("   Make sure status_dashboard.py is in the current directory")
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped by user")
    except Exception as e:
        print(f"❌ Error starting dashboard: {e}")

if __name__ == "__main__":
    main()