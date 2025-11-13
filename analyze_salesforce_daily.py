#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Salesforce Daily Activity Analysis
===================================

Provides detailed daily breakdown of file modifications using aggregate queries.
Shows exact dates within peak/off-peak periods to identify optimal migration windows.

Usage:
python analyze_salesforce_daily.py --month 2025-03
python analyze_salesforce_daily.py --date-range 2025-03-01 2025-03-31
python analyze_salesforce_daily.py --days 30
python analyze_salesforce_daily.py --peak-months  # Analyze all peak months
"""

import sys
import io
from datetime import datetime, timedelta
from collections import defaultdict
import argparse
from simple_salesforce import Salesforce

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Import config
try:
    import config
except ImportError:
    print("❌ Error: config.py not found. Copy config_template.py to config.py and configure.")
    sys.exit(1)


class DailyActivityAnalyzer:
    """Analyze daily activity patterns from Salesforce."""

    def __init__(self):
        """Initialize Salesforce connection."""
        self.sf = None
        self.connect_salesforce()

    def connect_salesforce(self):
        """Connect to Salesforce API."""
        try:
            sf_config = config.SALESFORCE_CONFIG
            self.sf = Salesforce(
                username=sf_config['username'],
                password=sf_config['password'],
                security_token=sf_config['security_token'],
                domain=sf_config['domain']
            )
            print("✅ Connected to Salesforce")
        except Exception as e:
            print(f"❌ Failed to connect to Salesforce: {e}")
            sys.exit(1)

    def get_daily_aggregates(self, start_date: str, end_date: str):
        """Get daily aggregates using GROUP BY."""
        print(f"🔍 Querying daily activity from {start_date} to {end_date}...", end='', flush=True)

        # Convert to Salesforce datetime format
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').strftime('%Y-%m-%dT00:00:00Z')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d').strftime('%Y-%m-%dT23:59:59Z')

        query = f"""
            SELECT
                CALENDAR_YEAR(LastModifiedDate) year,
                CALENDAR_MONTH(LastModifiedDate) month,
                DAY_IN_MONTH(LastModifiedDate) day,
                COUNT(Id) file_count
            FROM DocListEntry__c
            WHERE LastModifiedDate >= {start_dt}
            AND LastModifiedDate <= {end_dt}
            GROUP BY CALENDAR_YEAR(LastModifiedDate), CALENDAR_MONTH(LastModifiedDate), DAY_IN_MONTH(LastModifiedDate)
            ORDER BY CALENDAR_YEAR(LastModifiedDate) DESC, CALENDAR_MONTH(LastModifiedDate) DESC, DAY_IN_MONTH(LastModifiedDate) DESC
        """

        result = self.sf.query(query)
        records = result['records']
        print(f" ✅ {len(records)} days found")
        return records

    def get_hourly_aggregates(self, date: str):
        """Get hourly breakdown for a specific date."""
        print(f"🔍 Querying hourly activity for {date}...", end='', flush=True)

        # Convert to Salesforce datetime format
        start_dt = datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m-%dT00:00:00Z')
        end_dt = datetime.strptime(date, '%Y-%m-%d').strftime('%Y-%m-%dT23:59:59Z')

        query = f"""
            SELECT
                HOUR_IN_DAY(LastModifiedDate) hour,
                COUNT(Id) file_count
            FROM DocListEntry__c
            WHERE LastModifiedDate >= {start_dt}
            AND LastModifiedDate <= {end_dt}
            GROUP BY HOUR_IN_DAY(LastModifiedDate)
            ORDER BY HOUR_IN_DAY(LastModifiedDate)
        """

        result = self.sf.query(query)
        records = result['records']
        print(f" ✅ {len(records)} hours found")
        return records

    def format_daily_data(self, records):
        """Format daily aggregates into readable structure."""
        daily_data = {}
        for record in records:
            if record['year'] and record['month'] and record['day']:
                date_key = f"{record['year']}-{record['month']:02d}-{record['day']:02d}"
                daily_data[date_key] = record['file_count']
        return daily_data

    def get_day_of_week(self, date_str):
        """Get day of week name from date string."""
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%A')

    def estimate_api_calls(self, file_count: int):
        """Estimate API calls for migration."""
        return {
            'files': file_count,
            'backup_only': file_count,
            'full_migration': file_count * 2
        }

    def print_daily_report(self, daily_data, show_recommendations=True):
        """Print detailed daily report."""
        print("=" * 110)
        print("DAILY ACTIVITY BREAKDOWN")
        print("=" * 110)
        print()

        if not daily_data:
            print("❌ No activity data found")
            return

        print(f"{'Date':<12} {'Day':<10} {'Files':<12} {'API (Backup)':<15} {'API (Full)':<15} {'Activity Level':<20}")
        print("-" * 110)

        # Calculate statistics
        values = list(daily_data.values())
        avg = sum(values) / len(values) if values else 0
        max_val = max(values) if values else 0
        min_val = min(values) if values else 0

        # Define thresholds
        high_threshold = avg * 1.5
        low_threshold = avg * 0.5

        total_files = 0
        high_activity_days = []
        low_activity_days = []

        for date, count in sorted(daily_data.items()):
            day_name = self.get_day_of_week(date)
            api_est = self.estimate_api_calls(count)

            # Determine activity level
            if count >= high_threshold:
                level = "🔥 HIGH"
                high_activity_days.append((date, count, day_name))
            elif count <= low_threshold:
                level = "❄️  LOW (optimal)"
                low_activity_days.append((date, count, day_name))
            else:
                level = "⚖️  NORMAL"

            print(f"{date:<12} {day_name:<10} {count:<12,} {api_est['backup_only']:<15,} "
                  f"{api_est['full_migration']:<15,} {level:<20}")

            total_files += count

        print("-" * 110)
        total_api = self.estimate_api_calls(total_files)
        print(f"{'TOTAL':<12} {'':<10} {total_files:<12,} {total_api['backup_only']:<15,} "
              f"{total_api['full_migration']:<15,}")
        print()

        # Statistics
        print("📊 STATISTICAL SUMMARY:")
        print(f"   Total Days: {len(daily_data)}")
        print(f"   Average Files/Day: {avg:,.1f}")
        print(f"   Max Files/Day: {max_val:,}")
        print(f"   Min Files/Day: {min_val:,}")
        print(f"   Total Files: {total_files:,}")
        print()

        if show_recommendations:
            # Recommendations
            print("💡 MIGRATION RECOMMENDATIONS:")
            print()

            if low_activity_days:
                print(f"   ✅ BEST DAYS FOR MIGRATION ({len(low_activity_days)} days):")
                print(f"      Low activity days (≤50% of daily average):")
                print(f"      {'Date':<12} {'Day':<10} {'Files':<12} {'Est. API Calls (Full)':<20}")
                for date, count, day_name in sorted(low_activity_days):
                    api_calls = count * 2
                    print(f"      {date:<12} {day_name:<10} {count:<12,} {api_calls:<20,}")
                print()

            if high_activity_days:
                print(f"   ⚠️  AVOID THESE DAYS ({len(high_activity_days)} days):")
                print(f"      High activity days (≥150% of daily average):")
                print(f"      {'Date':<12} {'Day':<10} {'Files':<12} {'Est. API Calls (Full)':<20}")
                for date, count, day_name in sorted(high_activity_days):
                    api_calls = count * 2
                    print(f"      {date:<12} {day_name:<10} {count:<12,} {api_calls:<20,}")
                print()

            # Weekend vs Weekday analysis
            weekend_counts = []
            weekday_counts = []
            for date, count in daily_data.items():
                day_name = self.get_day_of_week(date)
                if day_name in ['Saturday', 'Sunday']:
                    weekend_counts.append(count)
                else:
                    weekday_counts.append(count)

            if weekend_counts and weekday_counts:
                weekend_avg = sum(weekend_counts) / len(weekend_counts)
                weekday_avg = sum(weekday_counts) / len(weekday_counts)
                print(f"   📅 WEEKEND vs WEEKDAY:")
                print(f"      Weekend average: {weekend_avg:,.1f} files/day")
                print(f"      Weekday average: {weekday_avg:,.1f} files/day")
                if weekend_avg < weekday_avg * 0.75:
                    print(f"      ✅ Weekends are {((1 - weekend_avg/weekday_avg) * 100):.0f}% quieter - OPTIMAL for migration")
                elif weekend_avg > weekday_avg * 1.25:
                    print(f"      ⚠️  Weekends are {((weekend_avg/weekday_avg - 1) * 100):.0f}% busier - AVOID migration")
                else:
                    print(f"      ℹ️  Weekend/weekday activity is similar")
                print()

    def print_hourly_report(self, hourly_data, date):
        """Print hourly breakdown for a specific date."""
        print("=" * 90)
        print(f"HOURLY BREAKDOWN FOR {date}")
        print("=" * 90)
        print()

        if not hourly_data:
            print("❌ No activity data found")
            return

        hourly_dict = {}
        for record in hourly_data:
            if record.get('hour') is not None:
                hourly_dict[record['hour']] = record['file_count']

        print(f"{'Hour (UTC)':<12} {'Files':<12} {'API (Backup)':<15} {'API (Full)':<15} {'Visual':<30}")
        print("-" * 90)

        max_count = max(hourly_dict.values()) if hourly_dict else 1
        total_files = 0

        for hour in range(24):
            count = hourly_dict.get(hour, 0)
            api_est = self.estimate_api_calls(count)

            # Visual bar
            bar_length = int((count / max_count) * 30) if max_count > 0 else 0
            bar = '█' * bar_length

            print(f"{hour:02d}:00{' ':<7} {count:<12,} {api_est['backup_only']:<15,} "
                  f"{api_est['full_migration']:<15,} {bar}")

            total_files += count

        print("-" * 90)
        total_api = self.estimate_api_calls(total_files)
        print(f"{'TOTAL':<12} {total_files:<12,} {total_api['backup_only']:<15,} "
              f"{total_api['full_migration']:<15,}")
        print()

        # Find quiet hours
        quiet_hours = [(h, hourly_dict.get(h, 0)) for h in range(24) if hourly_dict.get(h, 0) < total_files / 24 * 0.5]
        if quiet_hours:
            print("💡 QUIETEST HOURS (best for migration):")
            for hour, count in quiet_hours:
                print(f"   {hour:02d}:00 - {count:,} files")
            print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Daily activity analysis from Salesforce"
    )
    parser.add_argument(
        '--month',
        type=str,
        help='Analyze specific month (YYYY-MM), e.g., 2025-03'
    )
    parser.add_argument(
        '--date-range',
        nargs=2,
        metavar=('START', 'END'),
        help='Date range (YYYY-MM-DD YYYY-MM-DD), e.g., 2025-03-01 2025-03-31'
    )
    parser.add_argument(
        '--days',
        type=int,
        help='Last N days from today'
    )
    parser.add_argument(
        '--peak-months',
        action='store_true',
        help='Analyze peak months (March and April 2025)'
    )
    parser.add_argument(
        '--hourly',
        type=str,
        metavar='DATE',
        help='Show hourly breakdown for specific date (YYYY-MM-DD)'
    )

    args = parser.parse_args()

    print("=" * 110)
    print("SALESFORCE DAILY ACTIVITY ANALYZER")
    print("=" * 110)
    print()

    analyzer = DailyActivityAnalyzer()

    try:
        if args.hourly:
            # Hourly breakdown for specific date
            hourly_data = analyzer.get_hourly_aggregates(args.hourly)
            analyzer.print_hourly_report(hourly_data, args.hourly)

        elif args.peak_months:
            # Analyze March 2025
            print("🔥 ANALYZING PEAK MONTH: MARCH 2025")
            print()
            records = analyzer.get_daily_aggregates('2025-03-01', '2025-03-31')
            daily_data = analyzer.format_daily_data(records)
            analyzer.print_daily_report(daily_data)

            print("\n")

            # Analyze April 2025
            print("🔥 ANALYZING PEAK MONTH: APRIL 2025")
            print()
            records = analyzer.get_daily_aggregates('2025-04-01', '2025-04-30')
            daily_data = analyzer.format_daily_data(records)
            analyzer.print_daily_report(daily_data)

        elif args.month:
            # Analyze specific month
            year, month = args.month.split('-')
            start_date = f"{year}-{month}-01"
            # Calculate last day of month
            if month == '12':
                end_date = f"{year}-12-31"
            else:
                next_month = int(month) + 1
                end_date = (datetime.strptime(f"{year}-{next_month:02d}-01", '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')

            records = analyzer.get_daily_aggregates(start_date, end_date)
            daily_data = analyzer.format_daily_data(records)
            analyzer.print_daily_report(daily_data)

        elif args.date_range:
            # Analyze specific date range
            start_date, end_date = args.date_range
            records = analyzer.get_daily_aggregates(start_date, end_date)
            daily_data = analyzer.format_daily_data(records)
            analyzer.print_daily_report(daily_data)

        elif args.days:
            # Analyze last N days
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
            records = analyzer.get_daily_aggregates(start_date, end_date)
            daily_data = analyzer.format_daily_data(records)
            analyzer.print_daily_report(daily_data)

        else:
            print("❌ Please specify --month, --date-range, --days, --peak-months, or --hourly")
            print("\nExamples:")
            print("  python analyze_salesforce_daily.py --month 2025-03")
            print("  python analyze_salesforce_daily.py --date-range 2025-03-01 2025-03-15")
            print("  python analyze_salesforce_daily.py --days 30")
            print("  python analyze_salesforce_daily.py --peak-months")
            print("  python analyze_salesforce_daily.py --hourly 2025-03-15")
            sys.exit(1)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
