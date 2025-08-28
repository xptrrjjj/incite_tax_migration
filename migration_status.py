#!/usr/bin/env python3
"""
Migration Status and Statistics Tool
===================================

This utility script provides comprehensive information about your migration
status, including backup progress, statistics, and system health.

Usage:
python migration_status.py [options]
"""

import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from migration_db import MigrationDB

def format_size(size_bytes):
    """Format file size in human readable format."""
    if size_bytes is None:
        return "Unknown"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def format_datetime(dt_string):
    """Format datetime string for display."""
    if not dt_string:
        return "Never"
    
    try:
        dt = datetime.fromisoformat(dt_string.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_string

def print_overview(db):
    """Print migration overview."""
    stats = db.get_migration_stats()
    
    print("=" * 80)
    print("MIGRATION STATUS OVERVIEW")
    print("=" * 80)
    
    # File statistics
    file_stats = stats['files']
    total_files = file_stats.get('total_files', 0)
    backup_only = file_stats.get('backup_only', 0)
    fully_migrated = file_stats.get('fully_migrated', 0)
    total_size = file_stats.get('total_size_bytes', 0)
    unique_accounts = file_stats.get('unique_accounts', 0)
    
    print(f"Total Files Tracked:     {total_files:,}")
    print(f"  └─ Backup Only:        {backup_only:,} files")
    print(f"  └─ Fully Migrated:     {fully_migrated:,} files")
    print(f"Total Data Size:         {format_size(total_size)}")
    print(f"Unique Accounts:         {unique_accounts:,}")
    
    if total_files > 0:
        backup_pct = (backup_only / total_files) * 100
        migration_pct = (fully_migrated / total_files) * 100
        print(f"Backup Progress:         {backup_pct:.1f}%")
        print(f"Full Migration Progress: {migration_pct:.1f}%")
    
    print()

def print_recent_runs(db):
    """Print recent migration runs."""
    print("RECENT MIGRATION RUNS")
    print("-" * 80)
    
    runs = db.conn.execute('''
        SELECT * FROM migration_runs 
        ORDER BY start_time DESC 
        LIMIT 10
    ''').fetchall()
    
    if not runs:
        print("No migration runs found.")
        return
    
    print(f"{'Type':<15} {'Status':<12} {'Start Time':<20} {'Duration':<12} {'Files':<8} {'Success':<8}")
    print("-" * 80)
    
    for run in runs:
        run_type = run['run_type']
        status = run['status']
        start_time = format_datetime(run['start_time'])[:19]  # Truncate seconds
        
        # Calculate duration
        if run['end_time']:
            try:
                start_dt = datetime.fromisoformat(run['start_time'])
                end_dt = datetime.fromisoformat(run['end_time'])
                duration = str(end_dt - start_dt).split('.')[0]  # Remove microseconds
            except:
                duration = "Unknown"
        else:
            duration = "Running..." if status == 'running' else "Unknown"
        
        total_files = run['total_files_processed'] or 0
        successful = run['successful_files'] or 0
        
        print(f"{run_type:<15} {status:<12} {start_time:<20} {duration:<12} {total_files:<8} {successful:<8}")
    
    print()

def print_account_breakdown(db, limit=20):
    """Print account-wise file breakdown."""
    print(f"TOP {limit} ACCOUNTS BY FILE COUNT")
    print("-" * 80)
    
    accounts = db.conn.execute('''
        SELECT 
            account_id,
            account_name,
            COUNT(*) as file_count,
            SUM(file_size_bytes) as total_size,
            MAX(backup_timestamp) as last_backup,
            SUM(CASE WHEN salesforce_updated = 1 THEN 1 ELSE 0 END) as migrated_count
        FROM file_migrations
        GROUP BY account_id, account_name
        ORDER BY file_count DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    
    if not accounts:
        print("No account data found.")
        return
    
    print(f"{'Account Name':<30} {'Files':<8} {'Size':<12} {'Migrated':<10} {'Last Backup':<20}")
    print("-" * 80)
    
    for account in accounts:
        name = account['account_name'][:29] if account['account_name'] else 'Unknown'
        file_count = account['file_count']
        size = format_size(account['total_size'])
        migrated = account['migrated_count']
        last_backup = format_datetime(account['last_backup'])[:19]
        
        print(f"{name:<30} {file_count:<8} {size:<12} {migrated:<10} {last_backup:<20}")
    
    print()

def print_error_summary(db):
    """Print error summary."""
    print("ERROR SUMMARY")
    print("-" * 80)
    
    errors = db.conn.execute('''
        SELECT 
            error_type,
            COUNT(*) as error_count,
            MAX(timestamp) as latest_error
        FROM migration_errors
        GROUP BY error_type
        ORDER BY error_count DESC
    ''').fetchall()
    
    if not errors:
        print("No errors found. ✅")
        return
    
    print(f"{'Error Type':<25} {'Count':<8} {'Latest Occurrence':<20}")
    print("-" * 80)
    
    for error in errors:
        error_type = error['error_type']
        count = error['error_count']
        latest = format_datetime(error['latest_error'])[:19]
        
        print(f"{error_type:<25} {count:<8} {latest:<20}")
    
    print()

def print_recent_errors(db, limit=10):
    """Print recent errors with details."""
    print(f"RECENT ERRORS (Last {limit})")
    print("-" * 80)
    
    errors = db.conn.execute('''
        SELECT * FROM migration_errors
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,)).fetchall()
    
    if not errors:
        print("No recent errors found. ✅")
        return
    
    for error in errors:
        print(f"Time: {format_datetime(error['timestamp'])}")
        print(f"Type: {error['error_type']}")
        print(f"DocList ID: {error['doclist_entry_id'] or 'N/A'}")
        print(f"Message: {error['error_message']}")
        if error['original_url']:
            print(f"URL: {error['original_url']}")
        print("-" * 40)
    
    print()

def print_phase_readiness(db):
    """Print Phase 2 readiness status."""
    print("PHASE 2 MIGRATION READINESS")
    print("-" * 80)
    
    stats = db.get_migration_stats()
    file_stats = stats['files']
    
    total_files = file_stats.get('total_files', 0)
    backup_only = file_stats.get('backup_only', 0)
    
    if total_files == 0:
        print("❌ No backup data found. Run Phase 1 backup first.")
        return
    
    print(f"✅ Phase 1 backup completed: {total_files:,} files backed up")
    print(f"📋 Files ready for Phase 2:  {backup_only:,} files")
    
    if backup_only > 0:
        print("✅ Ready for Phase 2 full migration")
        print()
        print("Next steps:")
        print("1. python full_migration.py --dry-run    # Test the migration")
        print("2. python full_migration.py --execute    # Execute when ready")
    else:
        print("ℹ️  All files already fully migrated")
    
    print()

def export_status_report(db, output_file=None):
    """Export detailed status report to JSON."""
    if not output_file:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"migration_status_report_{timestamp}.json"
    
    # Gather comprehensive data
    stats = db.get_migration_stats()
    
    # Recent runs
    runs = db.conn.execute('''
        SELECT * FROM migration_runs 
        ORDER BY start_time DESC 
        LIMIT 50
    ''').fetchall()
    
    # Account breakdown
    accounts = db.conn.execute('''
        SELECT 
            account_id, account_name,
            COUNT(*) as file_count,
            SUM(file_size_bytes) as total_size,
            MAX(backup_timestamp) as last_backup,
            SUM(CASE WHEN salesforce_updated = 1 THEN 1 ELSE 0 END) as migrated_count
        FROM file_migrations
        GROUP BY account_id, account_name
        ORDER BY file_count DESC
    ''').fetchall()
    
    # Recent errors
    errors = db.conn.execute('''
        SELECT * FROM migration_errors
        ORDER BY timestamp DESC
        LIMIT 100
    ''').fetchall()
    
    # Create report
    report = {
        'report_timestamp': datetime.now().isoformat(),
        'overview': stats,
        'recent_runs': [dict(row) for row in runs],
        'account_breakdown': [dict(row) for row in accounts],
        'recent_errors': [dict(row) for row in errors],
        'database_path': str(db.db_path),
        'total_accounts': len(accounts),
        'phase_2_ready': stats['files'].get('backup_only', 0) > 0
    }
    
    # Write to file
    with open(output_file, 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"✅ Status report exported to: {output_file}")
    return output_file

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Migration status and statistics")
    parser.add_argument('--overview', action='store_true', help='Show overview (default)')
    parser.add_argument('--runs', action='store_true', help='Show recent migration runs')
    parser.add_argument('--accounts', action='store_true', help='Show account breakdown')
    parser.add_argument('--errors', action='store_true', help='Show error summary')
    parser.add_argument('--recent-errors', type=int, metavar='N', help='Show N recent errors')
    parser.add_argument('--readiness', action='store_true', help='Show Phase 2 readiness status')
    parser.add_argument('--export', metavar='FILE', help='Export detailed report to JSON file')
    parser.add_argument('--all', action='store_true', help='Show all information')
    parser.add_argument('--db-path', default='migration_tracking.db', help='Database file path')
    
    args = parser.parse_args()
    
    # Check if database exists
    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"❌ Migration database not found: {db_path}")
        print("Run Phase 1 backup to create the database.")
        sys.exit(1)
    
    try:
        with MigrationDB(str(db_path)) as db:
            # Default to overview if no specific option
            if not any([args.runs, args.accounts, args.errors, args.recent_errors, 
                       args.readiness, args.export, args.all]):
                args.overview = True
            
            if args.overview or args.all:
                print_overview(db)
            
            if args.runs or args.all:
                print_recent_runs(db)
            
            if args.accounts or args.all:
                print_account_breakdown(db)
            
            if args.errors or args.all:
                print_error_summary(db)
            
            if args.recent_errors or args.all:
                limit = args.recent_errors if args.recent_errors else 10
                print_recent_errors(db, limit)
            
            if args.readiness or args.all:
                print_phase_readiness(db)
            
            if args.export:
                export_status_report(db, args.export)
    
    except Exception as e:
        print(f"❌ Error reading migration status: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()