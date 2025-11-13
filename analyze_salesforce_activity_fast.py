#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast Salesforce Activity Analysis (Aggregate Queries)
======================================================

Uses Salesforce aggregate queries (GROUP BY) to analyze patterns WITHOUT
fetching all individual records. This is 100x faster than full table scan.

Query time: ~30 seconds instead of 15+ minutes

Usage:
python analyze_salesforce_activity_fast.py
python analyze_salesforce_activity_fast.py --days 730
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


class FastSalesforceAnalyzer:
    """Fast activity analysis using aggregate queries."""

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

    def get_total_count(self):
        """Get total record count."""
        print("📊 Counting total records...", end='', flush=True)
        query = "SELECT COUNT(Id) total FROM DocListEntry__c"
        result = self.sf.query(query)
        total = result['records'][0]['total']
        print(f" {total:,} records found")
        return total

    def get_date_range(self):
        """Get earliest and latest modification dates."""
        print("📅 Finding date range...", end='', flush=True)
        query = """
            SELECT
                MIN(LastModifiedDate) earliest,
                MAX(LastModifiedDate) latest
            FROM DocListEntry__c
        """
        result = self.sf.query(query)
        record = result['records'][0]
        earliest = record['earliest'][:10] if record['earliest'] else 'N/A'
        latest = record['latest'][:10] if record['latest'] else 'N/A'
        print(f" {earliest} to {latest}")
        return record['earliest'], record['latest']

    def get_monthly_aggregates(self, days: int = None):
        """Get monthly aggregates using GROUP BY (FAST!)."""
        if days:
            print(f"🔍 Querying monthly aggregates (last {days} days)...", end='', flush=True)
        else:
            print("🔍 Querying monthly aggregates (all time)...", end='', flush=True)

        if days:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%dT%H:%M:%SZ')
            query = f"""
                SELECT
                    CALENDAR_YEAR(LastModifiedDate) year,
                    CALENDAR_MONTH(LastModifiedDate) month,
                    COUNT(Id) file_count
                FROM DocListEntry__c
                WHERE LastModifiedDate >= {cutoff_date}
                GROUP BY CALENDAR_YEAR(LastModifiedDate), CALENDAR_MONTH(LastModifiedDate)
                ORDER BY CALENDAR_YEAR(LastModifiedDate) DESC, CALENDAR_MONTH(LastModifiedDate) DESC
            """
        else:
            query = """
                SELECT
                    CALENDAR_YEAR(LastModifiedDate) year,
                    CALENDAR_MONTH(LastModifiedDate) month,
                    COUNT(Id) file_count
                FROM DocListEntry__c
                GROUP BY CALENDAR_YEAR(LastModifiedDate), CALENDAR_MONTH(LastModifiedDate)
                ORDER BY CALENDAR_YEAR(LastModifiedDate) DESC, CALENDAR_MONTH(LastModifiedDate) DESC
            """

        result = self.sf.query(query)
        records = result['records']
        print(f" ✅ {len(records)} months found")
        return records

    def get_yearly_aggregates(self):
        """Get yearly aggregates."""
        print("📊 Querying yearly aggregates...", end='', flush=True)
        query = """
            SELECT
                CALENDAR_YEAR(LastModifiedDate) year,
                COUNT(Id) file_count
            FROM DocListEntry__c
            GROUP BY CALENDAR_YEAR(LastModifiedDate)
            ORDER BY CALENDAR_YEAR(LastModifiedDate) DESC
        """
        result = self.sf.query(query)
        records = result['records']
        print(f" ✅ {len(records)} years found")
        return records

    def format_monthly_data(self, records):
        """Format monthly aggregates into readable structure."""
        monthly_data = {}
        for record in records:
            if record['year'] and record['month']:
                month_key = f"{record['year']}-{record['month']:02d}"
                monthly_data[month_key] = record['file_count']
        return monthly_data

    def identify_peak_seasons(self, monthly_data):
        """Identify peak and off-peak seasons."""
        print("🔍 Analyzing seasonal patterns...", end='', flush=True)

        if not monthly_data:
            print(" ❌ No data")
            return None

        values = list(monthly_data.values())
        total = sum(values)
        avg = total / len(values) if values else 0
        max_val = max(values) if values else 0
        min_val = min(values) if values else 0

        # Peak = >150% avg, Off-peak = <75% avg
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

        print(f" ✅ Found {len(peak_months)} peak, {len(offpeak_months)} off-peak months")

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
            'backup_only': file_count,
            'full_migration': file_count * 2
        }

    def print_summary(self):
        """Print summary statistics."""
        print("=" * 90)
        print("SALESFORCE DATA SUMMARY")
        print("=" * 90)
        print()

        total = self.get_total_count()
        earliest, latest = self.get_date_range()

        print(f"📁 Total Records: {total:,}")
        print(f"📅 Date Range: {earliest[:10] if earliest else 'N/A'} to {latest[:10] if latest else 'N/A'}")
        print()

        if earliest and latest:
            earliest_dt = datetime.fromisoformat(earliest.replace('Z', '+00:00'))
            latest_dt = datetime.fromisoformat(latest.replace('Z', '+00:00'))
            days_span = (latest_dt - earliest_dt).days

            if days_span > 0:
                avg_per_day = total / days_span
                print(f"📊 Historical Average: {avg_per_day:,.1f} files/day over {days_span:,} days")
                print()

        api_est = self.estimate_api_calls(total)
        print(f"🔌 Estimated API Calls for Full Migration:")
        print(f"   Backup Only (Phase 1): {api_est['backup_only']:,} calls")
        print(f"   Full Migration (Phase 2): {api_est['full_migration']:,} calls")
        print()

    def print_yearly_report(self, yearly_data):
        """Print yearly breakdown."""
        print("=" * 90)
        print("YEARLY ACTIVITY")
        print("=" * 90)
        print()

        if not yearly_data:
            print("❌ No data found")
            return

        print(f"{'Year':<12} {'Files Modified':<15} {'API Calls (Backup)':<20} {'API Calls (Full)':<20}")
        print("-" * 90)

        for record in yearly_data:
            if record.get('year'):
                year = record['year']
                count = record['file_count']
                api_est = self.estimate_api_calls(count)
                print(f"{year:<12} {count:<15,} {api_est['backup_only']:<20,} {api_est['full_migration']:<20,}")

        print()

    def print_monthly_report(self, monthly_data):
        """Print monthly breakdown."""
        print("=" * 90)
        print("MONTHLY ACTIVITY")
        print("=" * 90)
        print()

        if not monthly_data:
            print("❌ No data found")
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
            print(f"   {'Month':<12} {'Files':<15} {'% of Average':<15} {'Est. Daily API Calls':<20}")
            print(f"   {'-'*62}")
            for month, count in peak_data['peak_months']:
                pct = (count / peak_data['average']) * 100
                daily_api = (count * 2) / 30  # Full migration estimate, per day
                print(f"   {month:<12} {count:<15,} {pct:<15.1f}% {daily_api:<20,.0f}")
            print()

        # Off-Peak Months
        if peak_data['offpeak_months']:
            print(f"❄️  OFF-PEAK SEASON MONTHS ({len(peak_data['offpeak_months'])} months):")
            print(f"   {'Month':<12} {'Files':<15} {'% of Average':<15} {'Est. Daily API Calls':<20}")
            print(f"   {'-'*62}")
            for month, count in peak_data['offpeak_months']:
                pct = (count / peak_data['average']) * 100
                daily_api = (count * 2) / 30
                print(f"   {month:<12} {count:<15,} {pct:<15.1f}% {daily_api:<20,.0f}")
            print()

        # Recommendations
        print("💡 MIGRATION RECOMMENDATIONS:")
        if peak_data['offpeak_months']:
            print(f"   ✅ BEST migration window: Off-peak months listed above")
            offpeak_avg = sum(c for _, c in peak_data['offpeak_months']) / len(peak_data['offpeak_months'])
            daily_backup = offpeak_avg / 30
            daily_full = (offpeak_avg * 2) / 30
            print(f"   📊 Expected daily load (off-peak):")
            print(f"      - Backup only: ~{daily_backup:,.0f} API calls/day")
            print(f"      - Full migration: ~{daily_full:,.0f} API calls/day")
        print()

        if peak_data['peak_months']:
            print(f"   ⚠️  AVOID migration during: Peak months listed above")
            peak_avg = sum(c for _, c in peak_data['peak_months']) / len(peak_data['peak_months'])
            daily_backup = peak_avg / 30
            daily_full = (peak_avg * 2) / 30
            print(f"   📊 Expected daily load (peak season):")
            print(f"      - Backup only: ~{daily_backup:,.0f} API calls/day")
            print(f"      - Full migration: ~{daily_full:,.0f} API calls/day")
            print(f"   ⚡ Risk: High user activity = potential conflicts during migration")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Fast Salesforce activity analysis using aggregate queries"
    )
    parser.add_argument(
        '--days',
        type=int,
        help='Analyze last N days (default: all time)'
    )
    parser.add_argument(
        '--skip-summary',
        action='store_true',
        help='Skip summary statistics'
    )
    parser.add_argument(
        '--skip-yearly',
        action='store_true',
        help='Skip yearly breakdown'
    )
    parser.add_argument(
        '--skip-monthly',
        action='store_true',
        help='Skip monthly breakdown'
    )
    parser.add_argument(
        '--peak-only',
        action='store_true',
        help='Show only peak season analysis'
    )

    args = parser.parse_args()

    print("=" * 90)
    print("FAST SALESFORCE ACTIVITY ANALYZER (Aggregate Queries)")
    print("=" * 90)
    print()

    analyzer = FastSalesforceAnalyzer()

    try:
        # Summary
        if not args.skip_summary and not args.peak_only:
            analyzer.print_summary()

        # Yearly
        if not args.skip_yearly and not args.peak_only:
            yearly_data = analyzer.get_yearly_aggregates()
            analyzer.print_yearly_report(yearly_data)

        # Monthly + Peak Analysis
        monthly_records = analyzer.get_monthly_aggregates(args.days)
        monthly_data = analyzer.format_monthly_data(monthly_records)

        if not args.skip_monthly and not args.peak_only:
            analyzer.print_monthly_report(monthly_data)

        # Peak analysis (always show)
        peak_data = analyzer.identify_peak_seasons(monthly_data)
        analyzer.print_peak_analysis(peak_data)

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
