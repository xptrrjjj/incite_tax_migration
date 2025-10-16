#!/usr/bin/env python3
"""
Check Migration Status
======================

Quick status check script to see current migration state without starting the dashboard.
Useful for troubleshooting and understanding migration progress.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

def format_number(num):
    """Format number with thousand separators."""
    return f"{num:,}" if num else "0"

def format_bytes(bytes_val):
    """Format bytes to human readable."""
    if not bytes_val:
        return "0 B"

    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"

def check_status():
    """Check and display migration status."""
    db_path = Path("migration_tracking.db")

    if not db_path.exists():
        print("❌ Database not found: migration_tracking.db")
        print("   Run a migration first to create data.")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        print("=" * 70)
        print("MIGRATION STATUS CHECK")
        print("=" * 70)
        print()

        # File Statistics
        print("📊 FILE STATISTICS:")
        print("-" * 70)

        cursor = conn.execute('''
            SELECT
                COUNT(*) as total_files,
                SUM(CASE WHEN salesforce_updated = 0 THEN 1 ELSE 0 END) as backup_only,
                SUM(CASE WHEN salesforce_updated = 1 THEN 1 ELSE 0 END) as fully_migrated,
                SUM(file_size_bytes) as total_size,
                COUNT(DISTINCT account_id) as unique_accounts,
                MIN(backup_timestamp) as first_backup,
                MAX(backup_timestamp) as last_backup
            FROM file_migrations
        ''')

        file_stats = cursor.fetchone()

        print(f"Total Files Tracked:     {format_number(file_stats['total_files'])}")
        print(f"Backup Only (Phase 1):   {format_number(file_stats['backup_only'])}")
        print(f"Fully Migrated (Phase 2): {format_number(file_stats['fully_migrated'])}")
        print(f"Unique Accounts:         {format_number(file_stats['unique_accounts'])}")
        print(f"Total Data Size:         {format_bytes(file_stats['total_size'])}")
        print(f"First Backup:            {file_stats['first_backup']}")
        print(f"Last Backup:             {file_stats['last_backup']}")
        print()

        # Migration Progress
        known_total = 1344438  # Known total from Salesforce
        backup_only = file_stats['backup_only'] or 0
        fully_migrated = file_stats['fully_migrated'] or 0

        if backup_only > 0:
            backup_pct = (backup_only / known_total) * 100
            print(f"📈 BACKUP PROGRESS:")
            print(f"   {backup_pct:.1f}% complete ({format_number(backup_only)} / {format_number(known_total)})")
            print()

        # Running Migrations
        print("🔄 MIGRATION RUNS:")
        print("-" * 70)

        cursor = conn.execute('''
            SELECT * FROM migration_runs
            WHERE status = 'running'
            ORDER BY start_time DESC
        ''')

        running = cursor.fetchall()

        if running:
            print(f"⚠️  Found {len(running)} migration(s) with 'running' status:")
            print()

            for run in running:
                print(f"   Run ID: {run['id']}")
                print(f"   Type: {run['run_type']}")
                print(f"   Started: {run['start_time']}")

                if run['start_time']:
                    try:
                        start = datetime.fromisoformat(run['start_time'])
                        duration = datetime.now() - start
                        hours = duration.total_seconds() / 3600
                        print(f"   Running for: {hours:.1f} hours")

                        if hours > 2:
                            print(f"   ⚠️  WARNING: This looks like a stale entry!")
                    except:
                        pass

                print(f"   Files Processed: {format_number(run['total_files_processed'])}")
                print(f"   Successful: {format_number(run['successful_files'])}")
                print(f"   Failed: {format_number(run['failed_files'])}")
                print()

            print("💡 TIP: Run 'python fix_stale_migration.py' to mark these as complete")
            print()
        else:
            print("✅ No running migrations")
            print()

        # Recent Completed Runs
        cursor = conn.execute('''
            SELECT * FROM migration_runs
            WHERE status IN ('completed', 'failed')
            ORDER BY start_time DESC
            LIMIT 3
        ''')

        recent = cursor.fetchall()

        if recent:
            print("📋 RECENT COMPLETED RUNS:")
            print("-" * 70)

            for run in recent:
                status_emoji = "✅" if run['status'] == 'completed' else "❌"
                print(f"{status_emoji} {run['run_type']} - {run['status']}")
                print(f"   Started: {run['start_time']}")
                print(f"   Ended: {run['end_time']}")
                print(f"   Files: {format_number(run['total_files_processed'])} processed, "
                      f"{format_number(run['successful_files'])} successful, "
                      f"{format_number(run['failed_files'])} failed")

                if run['start_time'] and run['end_time']:
                    try:
                        start = datetime.fromisoformat(run['start_time'])
                        end = datetime.fromisoformat(run['end_time'])
                        duration = end - start
                        hours = duration.total_seconds() / 3600
                        print(f"   Duration: {hours:.1f} hours")
                    except:
                        pass

                print()

        # Error Summary
        cursor = conn.execute('''
            SELECT
                error_type,
                COUNT(*) as count
            FROM migration_errors
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 5
        ''')

        errors = cursor.fetchall()

        if errors:
            print("⚠️  ERROR SUMMARY (Top 5):")
            print("-" * 70)

            for error in errors:
                print(f"   {error['error_type']}: {format_number(error['count'])} occurrences")

            print()

        # Phase Status
        print("🎯 MIGRATION PHASE:")
        print("-" * 70)

        if fully_migrated > 0:
            print("   Phase 2 (Full Migration) - IN PROGRESS or COMPLETE")
            print(f"   {format_number(fully_migrated)} files fully migrated")
        elif backup_only > 0:
            if running:
                print("   Phase 1 (Backup Only) - RUNNING")
            else:
                print("   Phase 1 (Backup Only) - COMPLETE")
                print()
                print("   ✅ Backup complete! Ready for Phase 2 when you are.")
                print("   💡 Run: python full_migration.py --dry-run")
        else:
            print("   Not Started")

        print()
        print("=" * 70)

        # Database Info
        db_size = db_path.stat().st_size
        print(f"Database Size: {format_bytes(db_size)}")
        print(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

    except Exception as e:
        print(f"❌ Error reading database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    check_status()
