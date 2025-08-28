#!/usr/bin/env python3
"""
Migration Status Dashboard
=========================

Simple web-based dashboard for monitoring migration progress in real-time.
Shows live statistics, progress, errors, and system status.

Usage:
python status_dashboard.py
Then open: http://localhost:5000
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify
import threading
import time
from migration_db import MigrationDB

app = Flask(__name__)

class StatusDashboard:
    """Status dashboard backend."""
    
    def __init__(self, db_path="migration_tracking.db"):
        self.db_path = db_path
        self.cache = {}
        self.cache_timestamp = None
        self.cache_ttl = 30  # Cache for 30 seconds
        
    def get_dashboard_data(self):
        """Get comprehensive dashboard data with caching."""
        now = datetime.now()
        
        # Use cache if it's fresh
        if (self.cache_timestamp and 
            (now - self.cache_timestamp).total_seconds() < self.cache_ttl):
            return self.cache
        
        try:
            with MigrationDB(self.db_path) as db:
                data = {
                    'timestamp': now.isoformat(),
                    'overview': self._get_overview_stats(db),
                    'progress': self._get_progress_data(db),
                    'recent_runs': self._get_recent_runs(db),
                    'errors': self._get_error_summary(db),
                    'accounts': self._get_top_accounts(db),
                    'system_info': self._get_system_info(),
                    'phase_status': self._get_phase_status(db)
                }
                
                # Update cache
                self.cache = data
                self.cache_timestamp = now
                
                return data
                
        except Exception as e:
            return {
                'timestamp': now.isoformat(),
                'error': f"Database error: {str(e)}",
                'overview': {},
                'progress': {},
                'recent_runs': [],
                'errors': [],
                'accounts': [],
                'system_info': {},
                'phase_status': {}
            }
    
    def _get_overview_stats(self, db):
        """Get overview statistics."""
        stats = db.get_migration_stats()
        file_stats = stats['files']
        
        return {
            'total_files': file_stats.get('total_files', 0),
            'backup_only': file_stats.get('backup_only', 0),
            'fully_migrated': file_stats.get('fully_migrated', 0),
            'unique_accounts': file_stats.get('unique_accounts', 0),
            'total_size_gb': round((file_stats.get('total_size_bytes', 0) or 0) / (1024**3), 2)
        }
    
    def _get_progress_data(self, db):
        """Get progress data for charts."""
        # Get progress by hour for the last 24 hours
        cursor = db.conn.execute('''
            SELECT 
                datetime(backup_timestamp, 'start of hour') as hour,
                COUNT(*) as files_count
            FROM file_migrations 
            WHERE backup_timestamp > datetime('now', '-24 hours')
            GROUP BY hour
            ORDER BY hour
        ''')
        
        hourly_progress = [{'hour': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # Get current running migration
        cursor = db.conn.execute('''
            SELECT * FROM migration_runs 
            WHERE status = 'running'
            ORDER BY start_time DESC
            LIMIT 1
        ''')
        
        current_run = cursor.fetchone()
        current_run_data = dict(current_run) if current_run else None
        
        return {
            'hourly_progress': hourly_progress,
            'current_run': current_run_data
        }
    
    def _get_recent_runs(self, db):
        """Get recent migration runs."""
        cursor = db.conn.execute('''
            SELECT * FROM migration_runs 
            ORDER BY start_time DESC 
            LIMIT 10
        ''')
        
        runs = []
        for row in cursor.fetchall():
            run_data = dict(row)
            
            # Calculate duration
            if run_data['end_time']:
                try:
                    start = datetime.fromisoformat(run_data['start_time'])
                    end = datetime.fromisoformat(run_data['end_time'])
                    run_data['duration'] = str(end - start).split('.')[0]
                except:
                    run_data['duration'] = 'Unknown'
            else:
                if run_data['status'] == 'running':
                    try:
                        start = datetime.fromisoformat(run_data['start_time'])
                        now = datetime.now()
                        run_data['duration'] = f"Running for {str(now - start).split('.')[0]}"
                    except:
                        run_data['duration'] = 'Running...'
                else:
                    run_data['duration'] = 'Unknown'
            
            runs.append(run_data)
        
        return runs
    
    def _get_error_summary(self, db):
        """Get error summary."""
        cursor = db.conn.execute('''
            SELECT 
                error_type,
                COUNT(*) as count,
                MAX(timestamp) as latest
            FROM migration_errors 
            WHERE timestamp > datetime('now', '-24 hours')
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
        ''')
        
        return [{'type': row[0], 'count': row[1], 'latest': row[2]} 
                for row in cursor.fetchall()]
    
    def _get_top_accounts(self, db):
        """Get top accounts by file count."""
        cursor = db.conn.execute('''
            SELECT 
                account_name,
                COUNT(*) as file_count,
                SUM(file_size_bytes) as total_size,
                SUM(CASE WHEN salesforce_updated = 1 THEN 1 ELSE 0 END) as migrated_count
            FROM file_migrations
            GROUP BY account_id, account_name
            ORDER BY file_count DESC
            LIMIT 10
        ''')
        
        accounts = []
        for row in cursor.fetchall():
            accounts.append({
                'name': row[0] or 'Unknown',
                'file_count': row[1],
                'total_size_mb': round((row[2] or 0) / (1024**2), 1),
                'migrated_count': row[3]
            })
        
        return accounts
    
    def _get_system_info(self):
        """Get system information."""
        try:
            db_path = Path(self.db_path)
            db_size = db_path.stat().st_size if db_path.exists() else 0
            
            return {
                'database_exists': db_path.exists(),
                'database_size_mb': round(db_size / (1024**2), 1),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return {
                'database_exists': False,
                'database_size_mb': 0,
                'last_updated': 'Error',
                'error': str(e)
            }
    
    def _get_phase_status(self, db):
        """Get migration phase status."""
        stats = db.get_migration_stats()
        file_stats = stats['files']
        
        total_files = file_stats.get('total_files', 0)
        backup_only = file_stats.get('backup_only', 0)
        fully_migrated = file_stats.get('fully_migrated', 0)
        
        if total_files == 0:
            phase = "Not Started"
            status = "No migration data found"
        elif backup_only > 0 and fully_migrated == 0:
            phase = "Phase 1 (Backup Only)"
            status = f"{backup_only:,} files backed up"
        elif fully_migrated > 0:
            phase = "Phase 2 (Full Migration)"
            status = f"{fully_migrated:,} files fully migrated"
        else:
            phase = "Unknown"
            status = "Unable to determine status"
        
        return {
            'current_phase': phase,
            'status_description': status,
            'backup_progress': round((backup_only / max(total_files, 1)) * 100, 1),
            'migration_progress': round((fully_migrated / max(total_files, 1)) * 100, 1)
        }

# Global dashboard instance
dashboard = StatusDashboard()

@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('dashboard.html')

@app.route('/api/status')
def api_status():
    """API endpoint for status data."""
    return jsonify(dashboard.get_dashboard_data())

@app.route('/api/health')
def api_health():
    """Health check endpoint."""
    try:
        data = dashboard.get_dashboard_data()
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'database_accessible': 'error' not in data
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'timestamp': datetime.now().isoformat(),
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("=" * 60)
    print("Migration Status Dashboard Starting")
    print("=" * 60)
    print("🌐 Dashboard URL: http://localhost:5000")
    print("🔄 Auto-refresh: Every 30 seconds")
    print("📊 Data source: migration_tracking.db")
    print("=" * 60)
    print()
    print("Press Ctrl+C to stop the dashboard")
    print()
    
    # Check if database exists
    db_path = Path("migration_tracking.db")
    if not db_path.exists():
        print("⚠️  WARNING: migration_tracking.db not found!")
        print("   Run Phase 1 migration first to create the database")
        print()
    
    app.run(host='localhost', port=5000, debug=False)