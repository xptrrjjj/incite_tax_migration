#!/usr/bin/env python3
"""
Fix Stale Migration Entry
=========================

Marks stale "running" migration entries as completed when migration is actually done.
Useful when migration script completed but didn't properly update the database status.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

def fix_stale_running_entries():
    """Mark stale running entries as completed."""
    db_path = Path("migration_tracking.db")

    if not db_path.exists():
        print("❌ Database not found: migration_tracking.db")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Get all "running" entries
        cursor = conn.execute('''
            SELECT id, run_type, start_time, total_files_processed, successful_files, failed_files
            FROM migration_runs
            WHERE status = 'running'
            ORDER BY start_time DESC
        ''')

        running_entries = cursor.fetchall()

        if not running_entries:
            print("✅ No stale running entries found - database is clean!")
            return

        print(f"Found {len(running_entries)} running migration(s):")
        print()

        for idx, entry in enumerate(running_entries, 1):
            print(f"Entry {idx}:")
            print(f"  ID: {entry['id']}")
            print(f"  Type: {entry['run_type']}")
            print(f"  Start: {entry['start_time']}")
            print(f"  Files Processed: {entry['total_files_processed']:,}")
            print(f"  Successful: {entry['successful_files']:,}")
            print(f"  Failed: {entry['failed_files']:,}")
            print()

        # Ask for confirmation
        response = input("Mark these entries as 'completed'? (yes/no): ").strip().lower()

        if response not in ['yes', 'y']:
            print("❌ Aborted - no changes made")
            return

        # Update all running entries to completed
        now = datetime.now().isoformat()

        for entry in running_entries:
            conn.execute('''
                UPDATE migration_runs
                SET status = 'completed',
                    end_time = ?
                WHERE id = ?
            ''', (now, entry['id']))

        conn.commit()

        print(f"✅ Marked {len(running_entries)} migration(s) as completed")
        print()
        print("🔄 Refresh your dashboard to see the updated progress!")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Fix Stale Migration Entry")
    print("=" * 60)
    print()

    fix_stale_running_entries()
