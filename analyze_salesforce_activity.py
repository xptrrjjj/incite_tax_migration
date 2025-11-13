#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Salesforce Activity Analysis Script
====================================

Analyzes DocListEntry__c records directly from Salesforce to identify:
- Peak vs Off-Peak seasons
- Daily/Monthly file modification patterns
- API call estimates for migration planning
- Optimal migration windows

Usage:
python analyze_salesforce_activity.py --days 365
python analyze_salesforce_activity.py --peak-analysis
python analyze_salesforce_activity.py --monthly
"""

import sys
import io
from datetime import datetime, timedelta
from collections import defaultdict
import argparse
from simple_salesforce import Salesforce
import calendar

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


class SalesforceActivityAnalyzer:
    """Analyze activity patterns directly from Salesforce."""

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

    def query_date_distribution(self, days: int = None):
        """Query LastModifiedDate distribution from Salesforce."""
        print(f"🔍 Querying DocListEntry__c records from Salesforce...")

        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
            query = f"""
                SELECT Id, LastModifiedDate, CreatedDate
                FROM DocListEntry__c
                WHERE LastModifiedDate >= {cutoff_date}
                ORDER BY LastModifiedDate DESC
            """
        else:
            # All time - just get dates
            query = """
                SELECT Id, LastModifiedDate, CreatedDate
                FROM DocListEntry__c
                ORDER BY LastModifiedDate DESC
            """

        results = []
        response = self.sf.query_all(query)
        results = response['records']

        print(f"✅ Retrieved {len(results):,} records")
        return results

    def analyze_by_day(self, records):
        """Analyze activity grouped by day."""
        daily_counts = defaultdict(int)

        for record in records:
            if record.get('LastModifiedDate'):
                date_str = record['LastModifiedDate'][:10]  # YYYY-MM-DD
                daily_counts[date_str] += 1

        return dict(sorted(daily_counts.items(), reverse=True))

    def analyze_by_month(self, records):
        """Analyze activity grouped by month."""
        monthly_counts = defaultdict(int)

        for record in records:
            if record.get('LastModifiedDate'):
                date_str = record['LastModifiedDate'][:7]  # YYYY-MM
                monthly_counts[date_str] += 1

        return dict(sorted(monthly_counts.items(), reverse=True))

    def analyze_by_year(self, records):
        """Analyze activity grouped by year."""
        yearly_counts = defaultdict(int)

        for record in records:
            if record.get('LastModifiedDate'):
                year = record['LastModifiedDate'][:4]  # YYYY
                yearly_counts[year] += 1

        return dict(sorted(yearly_counts.items(), reverse=True))

    def identify_peak_seasons(self, records):
        """Identify peak and off-peak seasons."""
        monthly_data = self.analyze_by_month(records)

        if not monthly_data:
            return None

        # Calculate statistics
        values = list(monthly_data.values())
        total = sum(values)
        avg = total / len(values) if values else 0
        max_val = max(values) if values else 0
        min_val = min(values) if values else 0

        # Define peak as >150% of average, off-peak as <75% of average
        peak_threshold = avg * 1.5
        offpeak_threshold = avg * 0.75

        peak_months = []
        offpeak_months = []
        normal_months = []

        for month, count in monthly_data.items():
            if count >= peak_threshold:
                peak_months.append((month, count))
            elif count <= offpeak_threshold:
                offpeak_months.append((month, count))
            else:
                normal_months.append((month, count))

        return {
            'total_months': len(monthly_data),
            'average': avg,
            'max': max_val,
            'min': min_val,
            'peak_threshold': peak_threshold,
            'offpeak_threshold': offpeak_threshold,
            'peak_months': sorted(peak_months, key=lambda x: x[1], reverse=True),
            'offpeak_months': sorted(offpeak_months, key=lambda x: x[1]),
            'normal_months': sorted(normal_months, key=lambda x: x[1], reverse=True)
        }

    def estimate_api_calls(self, file_count: int):
        """Estimate API calls for migration."""
        return {
            'files': file_count,
            'backup_only': file_count,  # 1 call per file for pre-signed URL
            'full_migration': file_count * 2  # Pre-signed URL + Salesforce update
        }

    def format_number(self, num):
        """Format number with commas."""
        return f"{num:,}"

    def print_daily_report(self, daily_data, limit=30):
        """Print daily activity report."""
        print("=" * 90)
        print("DAILY ACTIVITY ANALYSIS (Salesforce LastModifiedDate)")
        print("=" * 90)
        print()

        if not daily_data:
            print("❌ No activity data found")
            return

        print(f"{'Date':<12} {'Files Modified':<15} {'API Calls (Backup)':<20} {'API Calls (Full)':<20}")
        print("-" * 90)

        shown = 0
        for date, count in daily_data.items():
            if shown >= limit:
                break

            api_est = self.estimate_api_calls(count)
            print(f"{date:<12} {count:<15,} {api_est['backup_only']:<20,} {api_est['full_migration']:<20,}")
            shown += 1

        if len(daily_data) > limit:
            print(f"... ({len(daily_data) - limit} more days not shown)")
        print()

    def print_monthly_report(self, monthly_data):
        """Print monthly activity report."""
        print("=" * 90)
        print("MONTHLY ACTIVITY ANALYSIS")
        print("=" * 90)
        print()

        if not monthly_data:
            print("❌ No activity data found")
            return

        print(f"{'Month':<12} {'Files Modified':<15} {'API Calls (Backup)':<20} {'API Calls (Full)':<20}")
        print("-" * 90)

        for month, count in monthly_data.items():
            api_est = self.estimate_api_calls(count)
            print(f"{month:<12} {count:<15,} {api_est['backup_only']:<20,} {api_est['full_migration']:<20,}")

        print()

    def print_peak_analysis(self, peak_data):
        """Print peak season analysis."""
        print("=" * 90)
        print("PEAK SEASON ANALYSIS")
        print("=" * 90)
        print()

        if not peak_data:
            print("❌ No seasonal data available")
            return

        print(f"📊 Statistical Summary:")
        print(f"   Total Months Analyzed: {peak_data['total_months']}")
        print(f"   Average Files/Month: {peak_data['average']:,.1f}")
        print(f"   Max Files/Month: {peak_data['max']:,}")
        print(f"   Min Files/Month: {peak_data['min']:,}")
        print()

        print(f"🎯 Thresholds:")
        print(f"   Peak Season: ≥ {peak_data['peak_threshold']:,.0f} files/month (≥150% of avg)")
        print(f"   Off-Peak: ≤ {peak_data['offpeak_threshold']:,.0f} files/month (≤75% of avg)")
        print()

        # Peak Months
        if peak_data['peak_months']:
            print(f"🔥 PEAK SEASON MONTHS ({len(peak_data['peak_months'])} months):")
            print(f"   {'Month':<12} {'Files':<15} {'% of Average':<15}")
            print(f"   {'-'*42}")
            for month, count in peak_data['peak_months']:
                pct = (count / peak_data['average']) * 100
                print(f"   {month:<12} {count:<15,} {pct:<15.1f}%")
            print()

        # Off-Peak Months
        if peak_data['offpeak_months']:
            print(f"❄️  OFF-PEAK SEASON MONTHS ({len(peak_data['offpeak_months'])} months):")
            print(f"   {'Month':<12} {'Files':<15} {'% of Average':<15}")
            print(f"   {'-'*42}")
            for month, count in peak_data['offpeak_months']:
                pct = (count / peak_data['average']) * 100
                print(f"   {month:<12} {count:<15,} {pct:<15.1f}%")
            print()

        # Recommendations
        print("💡 MIGRATION RECOMMENDATIONS:")
        if peak_data['offpeak_months']:
            print(f"   ✅ Best migration window: Off-peak months above")
            offpeak_avg = sum(c for _, c in peak_data['offpeak_months']) / len(peak_data['offpeak_months'])
            api_est = self.estimate_api_calls(int(offpeak_avg))
            print(f"   📊 Expected daily API calls (off-peak avg): {api_est['backup_only'] / 30:,.0f} (backup) | {api_est['full_migration'] / 30:,.0f} (full)")
        if peak_data['peak_months']:
            print(f"   ⚠️  Avoid migration during: Peak months above")
            peak_avg = sum(c for _, c in peak_data['peak_months']) / len(peak_data['peak_months'])
            api_est = self.estimate_api_calls(int(peak_avg))
            print(f"   📊 Expected daily API calls (peak avg): {api_est['backup_only'] / 30:,.0f} (backup) | {api_est['full_migration'] / 30:,.0f} (full)")
        print()

    def print_yearly_summary(self, yearly_data):
        """Print yearly summary."""
        print("=" * 90)
        print("YEARLY ACTIVITY SUMMARY")
        print("=" * 90)
        print()

        if not yearly_data:
            print("❌ No activity data found")
            return

        print(f"{'Year':<12} {'Files Modified':<15} {'API Calls (Backup)':<20} {'API Calls (Full)':<20}")
        print("-" * 90)

        for year, count in yearly_data.items():
            api_est = self.estimate_api_calls(count)
            print(f"{year:<12} {count:<15,} {api_est['backup_only']:<20,} {api_est['full_migration']:<20,}")

        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Analyze Salesforce DocListEntry__c activity patterns")
    parser.add_argument(
        '--days',
        type=int,
        help='Analyze last N days (default: all time)'
    )
    parser.add_argument(
        '--daily',
        action='store_true',
        help='Show daily breakdown'
    )
    parser.add_argument(
        '--monthly',
        action='store_true',
        help='Show monthly breakdown'
    )
    parser.add_argument(
        '--yearly',
        action='store_true',
        help='Show yearly breakdown'
    )
    parser.add_argument(
        '--peak-analysis',
        action='store_true',
        help='Identify peak and off-peak seasons'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all reports'
    )

    args = parser.parse_args()

    # Default to all if nothing specified
    if not any([args.daily, args.monthly, args.yearly, args.peak_analysis]):
        args.all = True

    print("=" * 90)
    print("SALESFORCE ACTIVITY ANALYZER")
    print("=" * 90)
    print()

    analyzer = SalesforceActivityAnalyzer()

    try:
        # Query Salesforce
        records = analyzer.query_date_distribution(args.days)

        if not records:
            print("❌ No records found")
            sys.exit(0)

        # Generate reports
        if args.all or args.yearly:
            yearly_data = analyzer.analyze_by_year(records)
            analyzer.print_yearly_summary(yearly_data)

        if args.all or args.monthly:
            monthly_data = analyzer.analyze_by_month(records)
            analyzer.print_monthly_report(monthly_data)

        if args.all or args.peak_analysis:
            peak_data = analyzer.identify_peak_seasons(records)
            analyzer.print_peak_analysis(peak_data)

        if args.daily:
            daily_data = analyzer.analyze_by_day(records)
            analyzer.print_daily_report(daily_data, limit=30)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
