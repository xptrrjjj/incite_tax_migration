#!/usr/bin/env python3
"""
API Activity Analysis Script
=============================

Analyzes migration metadata to estimate daily API call patterns based on
LastModifiedDate from Salesforce records.

This helps predict:
- Peak activity days/periods
- API rate limit requirements
- Optimal migration windows
- Expected API costs

Usage:
python analyze_api_activity.py --days 30
python analyze_api_activity.py --date-range 2024-01-01 2024-12-31
python analyze_api_activity.py --by-account
"""

import sqlite3
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from pathlib import Path
import sys

class APIActivityAnalyzer:
    """Analyze API activity patterns from migration metadata."""

    def __init__(self, db_path: str = "migration_tracker.db"):
        """Initialize analyzer with database path."""
        self.db_path = db_path
        self.conn = None

    def connect(self):
        """Connect to migration database."""
        if not Path(self.db_path).exists():
            print(f"❌ Database not found: {self.db_path}")
            print("Run backup_chunked_migration.py first to generate metadata.")
            sys.exit(1)

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def get_activity_by_day(self, days: int = 30, start_date: str = None, end_date: str = None):
        """Get file modification activity grouped by day."""
        cursor = self.conn.cursor()

        if start_date and end_date:
            # Use specific date range
            query = """
                SELECT
                    DATE(last_modified_sf) as activity_date,
                    COUNT(*) as file_count,
                    SUM(file_size_bytes) as total_size
                FROM file_migrations
                WHERE last_modified_sf IS NOT NULL
                AND DATE(last_modified_sf) BETWEEN ? AND ?
                GROUP BY DATE(last_modified_sf)
                ORDER BY activity_date DESC
            """
            cursor.execute(query, (start_date, end_date))
        elif days:
            # Use relative days from now
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            query = """
                SELECT
                    DATE(last_modified_sf) as activity_date,
                    COUNT(*) as file_count,
                    SUM(file_size_bytes) as total_size
                FROM file_migrations
                WHERE last_modified_sf IS NOT NULL
                AND DATE(last_modified_sf) >= ?
                GROUP BY DATE(last_modified_sf)
                ORDER BY activity_date DESC
            """
            cursor.execute(query, (cutoff_date,))
        else:
            # All time
            query = """
                SELECT
                    DATE(last_modified_sf) as activity_date,
                    COUNT(*) as file_count,
                    SUM(file_size_bytes) as total_size
                FROM file_migrations
                WHERE last_modified_sf IS NOT NULL
                GROUP BY DATE(last_modified_sf)
                ORDER BY activity_date DESC
            """
            cursor.execute(query)

        return cursor.fetchall()

    def get_activity_by_account(self, days: int = 30):
        """Get activity breakdown by account."""
        cursor = self.conn.cursor()
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                account_name,
                account_id,
                COUNT(*) as file_count,
                SUM(file_size_bytes) as total_size,
                MIN(DATE(last_modified_sf)) as earliest_activity,
                MAX(DATE(last_modified_sf)) as latest_activity
            FROM file_migrations
            WHERE last_modified_sf IS NOT NULL
            AND DATE(last_modified_sf) >= ?
            GROUP BY account_id, account_name
            ORDER BY file_count DESC
        """

        cursor.execute(query, (cutoff_date,))
        return cursor.fetchall()

    def get_hourly_patterns(self, days: int = 30):
        """Get activity patterns by hour of day."""
        cursor = self.conn.cursor()
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        query = """
            SELECT
                CAST(strftime('%H', last_modified_sf) AS INTEGER) as hour,
                COUNT(*) as file_count,
                SUM(file_size_bytes) as total_size
            FROM file_migrations
            WHERE last_modified_sf IS NOT NULL
            AND DATE(last_modified_sf) >= ?
            GROUP BY hour
            ORDER BY hour
        """

        cursor.execute(query, (cutoff_date,))
        return cursor.fetchall()

    def get_summary_stats(self):
        """Get overall summary statistics."""
        cursor = self.conn.cursor()

        query = """
            SELECT
                COUNT(*) as total_files,
                SUM(file_size_bytes) as total_size,
                MIN(DATE(last_modified_sf)) as earliest_date,
                MAX(DATE(last_modified_sf)) as latest_date,
                COUNT(DISTINCT account_id) as account_count
            FROM file_migrations
            WHERE last_modified_sf IS NOT NULL
        """

        cursor.execute(query)
        return cursor.fetchone()

    def estimate_api_calls(self, file_count: int):
        """
        Estimate API calls needed for a given number of files.

        Assumptions:
        - 1 API call to generate pre-signed URL
        - 1 HTTP request to download file (not counted as SF API)
        - 1 API call to update DocListEntry__c (Phase 2 only)
        """
        backup_only_calls = file_count  # Just pre-signed URL generation
        full_migration_calls = file_count * 2  # Pre-signed URL + Salesforce update

        return {
            'files': file_count,
            'backup_only': backup_only_calls,
            'full_migration': full_migration_calls
        }

    def format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"

    def print_daily_activity(self, days: int = 30, start_date: str = None, end_date: str = None):
        """Print daily activity report."""
        print("=" * 80)
        print("DAILY API ACTIVITY ANALYSIS")
        print("=" * 80)

        if start_date and end_date:
            print(f"📅 Date Range: {start_date} to {end_date}")
        elif days:
            print(f"📅 Last {days} days")
        else:
            print(f"📅 All time")
        print()

        rows = self.get_activity_by_day(days, start_date, end_date)

        if not rows:
            print("❌ No activity data found for the specified period.")
            return

        print(f"{'Date':<12} {'Files':<10} {'Data Size':<15} {'API Calls (Backup)':<20} {'API Calls (Full)':<20}")
        print("-" * 80)

        total_files = 0
        total_size = 0

        for row in rows:
            date = row['activity_date']
            file_count = row['file_count']
            size = row['total_size'] or 0

            api_estimate = self.estimate_api_calls(file_count)

            print(f"{date:<12} {file_count:<10,} {self.format_size(size):<15} "
                  f"{api_estimate['backup_only']:<20,} {api_estimate['full_migration']:<20,}")

            total_files += file_count
            total_size += size

        print("-" * 80)
        total_api_estimate = self.estimate_api_calls(total_files)
        print(f"{'TOTAL':<12} {total_files:<10,} {self.format_size(total_size):<15} "
              f"{total_api_estimate['backup_only']:<20,} {total_api_estimate['full_migration']:<20,}")
        print()

        # Calculate averages
        if len(rows) > 0:
            avg_files_per_day = total_files / len(rows)
            avg_api_calls_backup = total_api_estimate['backup_only'] / len(rows)
            avg_api_calls_full = total_api_estimate['full_migration'] / len(rows)

            print("📊 DAILY AVERAGES")
            print(f"   Files per day: {avg_files_per_day:,.1f}")
            print(f"   API calls per day (backup): {avg_api_calls_backup:,.1f}")
            print(f"   API calls per day (full): {avg_api_calls_full:,.1f}")
            print()

    def print_account_breakdown(self, days: int = 30):
        """Print activity breakdown by account."""
        print("=" * 80)
        print("ACCOUNT-LEVEL API ACTIVITY")
        print("=" * 80)
        print(f"📅 Last {days} days")
        print()

        rows = self.get_activity_by_account(days)

        if not rows:
            print("❌ No activity data found.")
            return

        print(f"{'Account Name':<30} {'Files':<10} {'Data Size':<15} {'Date Range':<25}")
        print("-" * 80)

        for row in rows:
            account_name = row['account_name'][:28]
            file_count = row['file_count']
            size = row['total_size'] or 0
            date_range = f"{row['earliest_activity']} to {row['latest_activity']}"

            print(f"{account_name:<30} {file_count:<10,} {self.format_size(size):<15} {date_range:<25}")

        print()

    def print_hourly_patterns(self, days: int = 30):
        """Print hourly activity patterns."""
        print("=" * 80)
        print("HOURLY ACTIVITY PATTERNS")
        print("=" * 80)
        print(f"📅 Last {days} days")
        print()

        rows = self.get_hourly_patterns(days)

        if not rows:
            print("❌ No activity data found.")
            return

        print(f"{'Hour (UTC)':<12} {'Files':<10} {'Data Size':<15} {'Visual':<30}")
        print("-" * 80)

        max_count = max(row['file_count'] for row in rows) if rows else 1

        for row in rows:
            hour = row['hour']
            file_count = row['file_count']
            size = row['total_size'] or 0

            # Create visual bar
            bar_length = int((file_count / max_count) * 30)
            bar = '█' * bar_length

            print(f"{hour:02d}:00{' ':<7} {file_count:<10,} {self.format_size(size):<15} {bar}")

        print()

    def print_summary(self):
        """Print overall summary statistics."""
        stats = self.get_summary_stats()

        if not stats or stats['total_files'] == 0:
            print("❌ No migration data found in database.")
            return

        print("=" * 80)
        print("MIGRATION METADATA SUMMARY")
        print("=" * 80)
        print()

        api_estimate = self.estimate_api_calls(stats['total_files'])

        print(f"📁 Total Files: {stats['total_files']:,}")
        print(f"💾 Total Size: {self.format_size(stats['total_size'])}")
        print(f"🏢 Accounts: {stats['account_count']:,}")
        print(f"📅 Date Range: {stats['earliest_date']} to {stats['latest_date']}")
        print()
        print(f"🔌 Estimated API Calls:")
        print(f"   Backup Only (Phase 1): {api_estimate['backup_only']:,} calls")
        print(f"   Full Migration (Phase 2): {api_estimate['full_migration']:,} calls")
        print()

        # Calculate date range
        if stats['earliest_date'] and stats['latest_date']:
            earliest = datetime.strptime(stats['earliest_date'], '%Y-%m-%d')
            latest = datetime.strptime(stats['latest_date'], '%Y-%m-%d')
            days_span = (latest - earliest).days + 1

            if days_span > 0:
                avg_files_per_day = stats['total_files'] / days_span
                avg_api_backup = api_estimate['backup_only'] / days_span
                avg_api_full = api_estimate['full_migration'] / days_span

                print(f"📊 Historical Averages (over {days_span} days):")
                print(f"   Files per day: {avg_files_per_day:,.1f}")
                print(f"   API calls per day (backup): {avg_api_backup:,.1f}")
                print(f"   API calls per day (full): {avg_api_full:,.1f}")
                print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze API activity from migration metadata")
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Number of days to analyze (default: 30)'
    )
    parser.add_argument(
        '--date-range',
        nargs=2,
        metavar=('START', 'END'),
        help='Specific date range (YYYY-MM-DD YYYY-MM-DD)'
    )
    parser.add_argument(
        '--by-account',
        action='store_true',
        help='Show breakdown by account'
    )
    parser.add_argument(
        '--hourly',
        action='store_true',
        help='Show hourly activity patterns'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show summary statistics only'
    )
    parser.add_argument(
        '--db',
        default='migration_tracker.db',
        help='Path to migration database (default: migration_tracker.db)'
    )

    args = parser.parse_args()

    analyzer = APIActivityAnalyzer(args.db)

    try:
        analyzer.connect()

        if args.summary:
            analyzer.print_summary()
        elif args.by_account:
            analyzer.print_summary()
            analyzer.print_account_breakdown(args.days)
        elif args.hourly:
            analyzer.print_summary()
            analyzer.print_hourly_patterns(args.days)
        else:
            analyzer.print_summary()
            if args.date_range:
                analyzer.print_daily_activity(start_date=args.date_range[0], end_date=args.date_range[1])
            else:
                analyzer.print_daily_activity(days=args.days)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        analyzer.close()


if __name__ == "__main__":
    main()
