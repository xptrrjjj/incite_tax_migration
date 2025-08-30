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
                # Clean up stale "running" entries first
                self._cleanup_stale_running_entries(db)
                
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
    
    def _cleanup_stale_running_entries(self, db):
        """Clean up old 'running' entries that are clearly stale."""
        # Mark as failed any "running" entries older than 30 minutes that aren't the most recent
        cursor = db.conn.execute('''
            SELECT id, start_time FROM migration_runs 
            WHERE status = 'running'
            ORDER BY start_time DESC
        ''')
        
        running_entries = cursor.fetchall()
        if len(running_entries) > 1:
            # Keep only the most recent running entry, mark others as failed
            most_recent_id = running_entries[0]['id']
            
            for entry in running_entries[1:]:
                db.conn.execute('''
                    UPDATE migration_runs 
                    SET status = 'failed', 
                        end_time = ?, 
                        error_message = 'Marked as failed - stale running entry'
                    WHERE id = ?
                ''', (datetime.now().isoformat(), entry['id']))
            
            db.conn.commit()
            print(f"Cleaned up {len(running_entries) - 1} stale running entries")
    
    def _get_overview_stats(self, db):
        """Get overview statistics."""
        stats = db.get_migration_stats()
        file_stats = stats['files']
        
        # Safely handle None values
        total_size_bytes = file_stats.get('total_size_bytes') or 0
        total_size_gb = round(total_size_bytes / (1024**3), 2) if total_size_bytes else 0
        
        return {
            'total_files': file_stats.get('total_files', 0) or 0,
            'backup_only': file_stats.get('backup_only', 0) or 0,
            'fully_migrated': file_stats.get('fully_migrated', 0) or 0,
            'unique_accounts': file_stats.get('unique_accounts', 0) or 0,
            'total_size_gb': total_size_gb
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
        """Get recent migration runs with improved formatting."""
        cursor = db.conn.execute('''
            SELECT * FROM migration_runs 
            ORDER BY start_time DESC 
            LIMIT 10
        ''')
        
        runs = []
        for row in cursor.fetchall():
            run_data = dict(row)
            
            # Ensure data integrity and prevent corruption
            run_data['run_type'] = run_data.get('run_type', 'unknown') or 'unknown'
            run_data['status'] = run_data.get('status', 'unknown') or 'unknown'
            run_data['successful_files'] = run_data.get('successful_files', 0) or 0
            run_data['failed_files'] = run_data.get('failed_files', 0) or 0
            run_data['total_files'] = run_data.get('total_files', 0) or 0
            
            # Calculate duration with better formatting
            if run_data.get('end_time'):
                try:
                    start = datetime.fromisoformat(str(run_data['start_time']))
                    end = datetime.fromisoformat(str(run_data['end_time']))
                    duration = end - start
                    
                    # Format duration nicely
                    total_seconds = int(duration.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    
                    if hours > 0:
                        run_data['duration'] = f"{hours}h {minutes}m {seconds}s"
                    elif minutes > 0:
                        run_data['duration'] = f"{minutes}m {seconds}s"
                    else:
                        run_data['duration'] = f"{seconds}s"
                        
                except Exception as e:
                    run_data['duration'] = 'Unknown'
            else:
                if run_data['status'] == 'running' and run_data.get('start_time'):
                    try:
                        start = datetime.fromisoformat(str(run_data['start_time']))
                        now = datetime.now()
                        duration = now - start
                        
                        # Format running duration
                        total_seconds = int(duration.total_seconds())
                        days = total_seconds // 86400
                        hours = (total_seconds % 86400) // 3600
                        minutes = (total_seconds % 3600) // 60
                        
                        if days > 0:
                            run_data['duration'] = f"Running for {days}d {hours}h {minutes}m"
                        elif hours > 0:
                            run_data['duration'] = f"Running for {hours}h {minutes}m"
                        else:
                            run_data['duration'] = f"Running for {minutes}m"
                            
                    except Exception as e:
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
        """Get top accounts by file count with data integrity checks."""
        cursor = db.conn.execute('''
            SELECT 
                COALESCE(account_name, 'Unknown') as account_name,
                COUNT(*) as file_count,
                COALESCE(SUM(file_size_bytes), 0) as total_size,
                SUM(CASE WHEN salesforce_updated = 1 THEN 1 ELSE 0 END) as migrated_count
            FROM file_migrations
            WHERE account_name IS NOT NULL 
            AND account_name != ''
            GROUP BY account_id, account_name
            HAVING file_count > 0
            ORDER BY file_count DESC
            LIMIT 10
        ''')
        
        accounts = []
        for row in cursor.fetchall():
            # Safely handle data conversion with fallbacks
            account_name = str(row[0]) if row[0] else 'Unknown'
            file_count = int(row[1]) if row[1] and str(row[1]).isdigit() else 0
            total_size_bytes = float(row[2]) if row[2] and str(row[2]).replace('.','').isdigit() else 0
            migrated_count = int(row[3]) if row[3] and str(row[3]).isdigit() else 0
            
            # Convert bytes to MB safely
            try:
                total_size_mb = round(total_size_bytes / (1024**2), 1) if total_size_bytes > 0 else 0
            except:
                total_size_mb = 0
            
            # Clean account name to prevent corruption
            clean_name = ''.join(char for char in account_name if ord(char) < 128)[:50]  # ASCII only, max 50 chars
            if not clean_name.strip():
                clean_name = 'Unknown'
            
            accounts.append({
                'name': clean_name,
                'file_count': file_count,
                'total_size_mb': total_size_mb,
                'migrated_count': migrated_count
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
        """Get migration phase status with proper progress calculation."""
        stats = db.get_migration_stats()
        file_stats = stats['files']
        
        total_files = file_stats.get('total_files', 0) or 0
        backup_only = file_stats.get('backup_only', 0) or 0
        fully_migrated = file_stats.get('fully_migrated', 0) or 0
        
        # Check if there's a currently running migration
        cursor = db.conn.execute('''
            SELECT COUNT(*), SUM(successful_files), SUM(failed_files), SUM(total_files_processed)
            FROM migration_runs 
            WHERE status = 'running'
        ''')
        
        running_data = cursor.fetchone()
        is_running = running_data and running_data[0] > 0
        
        # Get total expected files from Salesforce (more accurate than just backed up files)
        try:
            cursor = db.conn.execute('''
                SELECT COUNT(DISTINCT doclist_entry_id) 
                FROM file_migrations 
            ''')
            actual_discovered_files = cursor.fetchone()[0] or 0
        except:
            actual_discovered_files = total_files
        
        # Determine phase and status
        if total_files == 0 and actual_discovered_files == 0:
            phase = "Not Started"
            status = "No migration data found"
            backup_progress = 0
            migration_progress = 0
        elif backup_only > 0 and fully_migrated == 0:
            if is_running:
                phase = "Phase 1 (Backup Only) - RUNNING"
                status = f"Actively backing up files... ({backup_only:,} files backed up so far)"
                # For running migrations, use realistic total estimate of 1.3M+ files
                # Don't use actual_discovered_files as it only shows what's been processed so far
                estimated_total = 1300000  # Known approximate total from previous analysis
                backup_progress = min(95.0, round((backup_only / estimated_total) * 100, 1)) if estimated_total > 0 else 0
            else:
                phase = "Phase 1 (Backup Only) - COMPLETE"
                status = f"{backup_only:,} files backed up and ready for migration"
                backup_progress = 100.0
            migration_progress = 0
        elif fully_migrated > 0:
            phase = "Phase 2 (Full Migration)"
            status = f"{fully_migrated:,} files fully migrated, {backup_only:,} backup-only"
            # Only show 100% if no migration is running
            if actual_discovered_files > 0:
                backup_progress = round((backup_only / actual_discovered_files) * 100, 1)
                migration_progress = round((fully_migrated / actual_discovered_files) * 100, 1)
            else:
                backup_progress = 100.0 if backup_only > 0 else 0
                migration_progress = 100.0 if fully_migrated > 0 else 0
        else:
            phase = "Unknown"
            status = "Unable to determine migration status"
            backup_progress = 0
            migration_progress = 0
        
        # Cap progress at reasonable levels if migration is running
        if is_running:
            backup_progress = min(backup_progress, 95.0)
            migration_progress = min(migration_progress, 95.0)
        
        return {
            'current_phase': phase,
            'status_description': status,
            'backup_progress': max(0, backup_progress),
            'migration_progress': max(0, migration_progress),
            'is_running': is_running,
            'actual_discovered_files': actual_discovered_files
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

@app.route('/api/recent-errors')
def api_recent_errors():
    """Get recent error details."""
    try:
        with MigrationDB(dashboard.db_path) as db:
            cursor = db.conn.execute('''
                SELECT 
                    doclist_entry_id,
                    error_type,
                    error_message,
                    original_url,
                    timestamp
                FROM migration_errors 
                WHERE timestamp > datetime('now', '-24 hours')
                ORDER BY timestamp DESC
                LIMIT 50
            ''')
            
            errors = []
            for row in cursor.fetchall():
                errors.append({
                    'doclist_entry_id': row[0],
                    'error_type': row[1], 
                    'error_message': row[2],
                    'original_url': row[3],
                    'timestamp': row[4]
                })
            
            return jsonify({'errors': errors})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
    
    app.run(host='0.0.0.0', port=5000, debug=False)