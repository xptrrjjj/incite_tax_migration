#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Salesforce Storage Analysis Script
===================================

Comprehensive analysis of Salesforce storage consumption across all categories:
- File Storage (ContentVersion, Attachments, Documents)
- Data Storage (all standard and custom objects)
- Storage by object type, user, account
- Identifies top storage consumers
- Compares against Enterprise Edition limits

Usage:
python analyze_salesforce_storage.py
python analyze_salesforce_storage.py --detailed
python analyze_salesforce_storage.py --top-objects 20
python analyze_salesforce_storage.py --by-account
"""

import sys
import io
from datetime import datetime
from collections import defaultdict
import argparse
from simple_salesforce import Salesforce
import json

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


class SalesforceStorageAnalyzer:
    """Analyze Salesforce storage consumption."""

    # Enterprise Edition Storage Limits
    ENTERPRISE_LIMITS = {
        'data_storage_base_gb': 10,
        'data_storage_per_user_mb': 20,
        'file_storage_base_gb': 10,
        'file_storage_per_user_gb': 2
    }

    def __init__(self):
        """Initialize Salesforce connection."""
        self.sf = None
        self.org_info = {}
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

    def get_org_limits(self):
        """Get organization limits from Salesforce."""
        print("📊 Retrieving organization limits...", end='', flush=True)
        try:
            limits = self.sf.limits()
            print(" ✅ Done")
            return limits
        except Exception as e:
            print(f" ❌ Failed: {e}")
            return None

    def get_file_storage_usage(self):
        """Get file storage usage by type."""
        print("📁 Analyzing file storage usage...", end='', flush=True)

        storage_data = {}

        try:
            # ContentVersion (Files uploaded via Files/Chatter Files)
            cv_query = """
                SELECT COUNT(Id) record_count, SUM(ContentSize) total_size
                FROM ContentVersion
                WHERE IsLatest = true
            """
            cv_result = self.sf.query(cv_query)
            if cv_result['records']:
                record = cv_result['records'][0]
                storage_data['ContentVersion'] = {
                    'count': record['record_count'] or 0,
                    'size_bytes': record['total_size'] or 0
                }

            # Attachment (Classic attachments)
            att_query = """
                SELECT COUNT(Id) record_count, SUM(BodyLength) total_size
                FROM Attachment
            """
            att_result = self.sf.query(att_query)
            if att_result['records']:
                record = att_result['records'][0]
                storage_data['Attachment'] = {
                    'count': record['record_count'] or 0,
                    'size_bytes': record['total_size'] or 0
                }

            # Document (Documents tab)
            doc_query = """
                SELECT COUNT(Id) record_count, SUM(BodyLength) total_size
                FROM Document
            """
            doc_result = self.sf.query(doc_query)
            if doc_result['records']:
                record = doc_result['records'][0]
                storage_data['Document'] = {
                    'count': record['record_count'] or 0,
                    'size_bytes': record['total_size'] or 0
                }

            print(" ✅ Done")
            return storage_data

        except Exception as e:
            print(f" ❌ Failed: {e}")
            return storage_data

    def get_contentversion_by_type(self):
        """Get ContentVersion storage breakdown by file type."""
        print("📂 Analyzing file types...", end='', flush=True)

        query = """
            SELECT FileExtension, COUNT(Id) record_count, SUM(ContentSize) total_size
            FROM ContentVersion
            WHERE IsLatest = true
            GROUP BY FileExtension
            ORDER BY SUM(ContentSize) DESC
            LIMIT 50
        """

        try:
            result = self.sf.query(query)
            print(f" ✅ {len(result['records'])} file types found")
            return result['records']
        except Exception as e:
            print(f" ❌ Failed: {e}")
            return []

    def get_doclistentry_storage(self):
        """Get DocListEntry__c storage usage (custom object for document management)."""
        print("📋 Analyzing DocListEntry__c records...", end='', flush=True)

        try:
            # Count total records
            query = "SELECT COUNT(Id) total FROM DocListEntry__c"
            result = self.sf.query(query)
            total_records = result['records'][0]['total']

            # Estimate storage (each record consumes data storage)
            # Average Salesforce record: ~2KB per record (conservative estimate)
            estimated_size = total_records * 2048  # bytes

            print(f" ✅ {total_records:,} records found")
            return {
                'count': total_records,
                'size_bytes': estimated_size,
                'note': 'Estimated based on avg 2KB/record'
            }
        except Exception as e:
            print(f" ❌ Failed: {e}")
            return {'count': 0, 'size_bytes': 0, 'note': 'Failed to retrieve'}

    def get_top_objects_by_count(self, limit=20):
        """Get top objects by record count."""
        print(f"🔍 Identifying top {limit} objects by record count...", end='', flush=True)

        try:
            # Get all objects
            objects = self.sf.describe()['sobjects']

            object_counts = []

            for obj in objects:
                obj_name = obj['name']

                # Skip certain system objects
                if obj_name.endswith('Share') or obj_name.endswith('History') or obj_name.endswith('Feed'):
                    continue

                try:
                    query = f"SELECT COUNT(Id) total FROM {obj_name}"
                    result = self.sf.query(query)
                    count = result['records'][0]['total']

                    if count > 0:
                        object_counts.append({
                            'object': obj_name,
                            'count': count,
                            'label': obj['label']
                        })
                except:
                    continue

            # Sort by count
            object_counts.sort(key=lambda x: x['count'], reverse=True)

            print(f" ✅ Analyzed {len(object_counts)} objects")
            return object_counts[:limit]

        except Exception as e:
            print(f" ❌ Failed: {e}")
            return []

    def get_account_file_distribution(self):
        """Get file storage distribution by account (via DocListEntry__c)."""
        print("🏢 Analyzing storage by account...", end='', flush=True)

        query = """
            SELECT Account__c, Account__r.Name, COUNT(Id) doc_count
            FROM DocListEntry__c
            GROUP BY Account__c, Account__r.Name
            ORDER BY COUNT(Id) DESC
            LIMIT 50
        """

        try:
            result = self.sf.query(query)
            print(f" ✅ {len(result['records'])} accounts analyzed")
            return result['records']
        except Exception as e:
            print(f" ❌ Failed: {e}")
            return []

    def format_size(self, size_bytes):
        """Format bytes to human readable."""
        if size_bytes == 0:
            return "0 B"

        units = ['B', 'KB', 'MB', 'GB', 'TB']
        unit_index = 0
        size = float(size_bytes)

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        return f"{size:.2f} {units[unit_index]}"

    def calculate_storage_limits(self, user_count):
        """Calculate storage limits based on Enterprise Edition."""
        data_storage_limit = (
            self.ENTERPRISE_LIMITS['data_storage_base_gb'] * 1024 * 1024 * 1024 +
            user_count * self.ENTERPRISE_LIMITS['data_storage_per_user_mb'] * 1024 * 1024
        )

        file_storage_limit = (
            self.ENTERPRISE_LIMITS['file_storage_base_gb'] * 1024 * 1024 * 1024 +
            user_count * self.ENTERPRISE_LIMITS['file_storage_per_user_gb'] * 1024 * 1024 * 1024
        )

        return {
            'data_storage_bytes': data_storage_limit,
            'file_storage_bytes': file_storage_limit
        }

    def print_summary(self, limits, user_count=100):
        """Print storage summary."""
        print("=" * 100)
        print("SALESFORCE STORAGE SUMMARY")
        print("=" * 100)
        print()

        if limits:
            # Data Storage
            data_storage = limits.get('DataStorageMB', {})
            if data_storage:
                used_mb = data_storage.get('Used', 0)
                max_mb = data_storage.get('Max', 0)
                remaining_mb = data_storage.get('Remaining', 0)

                used_pct = (used_mb / max_mb * 100) if max_mb > 0 else 0

                print("📊 DATA STORAGE:")
                print(f"   Used: {used_mb:,.0f} MB ({self.format_size(used_mb * 1024 * 1024)})")
                print(f"   Max: {max_mb:,.0f} MB ({self.format_size(max_mb * 1024 * 1024)})")
                print(f"   Remaining: {remaining_mb:,.0f} MB ({self.format_size(remaining_mb * 1024 * 1024)})")
                print(f"   Usage: {used_pct:.1f}%")

                if used_pct >= 90:
                    print(f"   ⚠️  WARNING: {used_pct:.1f}% used - approaching limit!")
                elif used_pct >= 75:
                    print(f"   ⚡ NOTICE: {used_pct:.1f}% used - monitor closely")
                else:
                    print(f"   ✅ HEALTHY: {used_pct:.1f}% used")
                print()

            # File Storage
            file_storage = limits.get('FileStorageMB', {})
            if file_storage:
                used_mb = file_storage.get('Used', 0)
                max_mb = file_storage.get('Max', 0)
                remaining_mb = file_storage.get('Remaining', 0)

                used_pct = (used_mb / max_mb * 100) if max_mb > 0 else 0

                print("📁 FILE STORAGE:")
                print(f"   Used: {used_mb:,.0f} MB ({self.format_size(used_mb * 1024 * 1024)})")
                print(f"   Max: {max_mb:,.0f} MB ({self.format_size(max_mb * 1024 * 1024)})")
                print(f"   Remaining: {remaining_mb:,.0f} MB ({self.format_size(remaining_mb * 1024 * 1024)})")
                print(f"   Usage: {used_pct:.1f}%")

                if used_pct >= 90:
                    print(f"   ⚠️  WARNING: {used_pct:.1f}% used - approaching limit!")
                elif used_pct >= 75:
                    print(f"   ⚡ NOTICE: {used_pct:.1f}% used - monitor closely")
                else:
                    print(f"   ✅ HEALTHY: {used_pct:.1f}% used")
                print()

            # API Limits
            daily_api = limits.get('DailyApiRequests', {})
            if daily_api:
                used = daily_api.get('Used', 0)
                max_calls = daily_api.get('Max', 0)
                remaining = daily_api.get('Remaining', 0)

                used_pct = (used / max_calls * 100) if max_calls > 0 else 0

                print("🔌 API USAGE (24-Hour Rolling):")
                print(f"   Used: {used:,} calls")
                print(f"   Max: {max_calls:,} calls")
                print(f"   Remaining: {remaining:,} calls")
                print(f"   Usage: {used_pct:.1f}%")
                print()

    def print_file_storage_detail(self, file_storage):
        """Print detailed file storage breakdown."""
        print("=" * 100)
        print("FILE STORAGE BREAKDOWN")
        print("=" * 100)
        print()

        if not file_storage:
            print("❌ No file storage data available")
            return

        print(f"{'Storage Type':<20} {'Record Count':<15} {'Total Size':<20} {'Avg Size/Record':<20}")
        print("-" * 100)

        total_files = 0
        total_size = 0

        for storage_type, data in sorted(file_storage.items(), key=lambda x: x[1]['size_bytes'], reverse=True):
            count = data['count']
            size = data['size_bytes']
            avg_size = size / count if count > 0 else 0

            print(f"{storage_type:<20} {count:<15,} {self.format_size(size):<20} {self.format_size(avg_size):<20}")

            total_files += count
            total_size += size

        print("-" * 100)
        avg_total = total_size / total_files if total_files > 0 else 0
        print(f"{'TOTAL':<20} {total_files:<15,} {self.format_size(total_size):<20} {self.format_size(avg_total):<20}")
        print()

    def print_file_type_breakdown(self, file_types):
        """Print file type breakdown."""
        print("=" * 100)
        print("FILE TYPE BREAKDOWN (ContentVersion)")
        print("=" * 100)
        print()

        if not file_types:
            print("❌ No file type data available")
            return

        print(f"{'Extension':<15} {'Count':<15} {'Total Size':<20} {'Avg Size':<20} {'% of Total':<15}")
        print("-" * 100)

        total_size = sum(r['total_size'] or 0 for r in file_types)

        for record in file_types[:30]:  # Top 30
            ext = record['FileExtension'] or '(none)'
            count = record['record_count'] or 0
            size = record['total_size'] or 0
            avg_size = size / count if count > 0 else 0
            pct = (size / total_size * 100) if total_size > 0 else 0

            print(f"{ext:<15} {count:<15,} {self.format_size(size):<20} {self.format_size(avg_size):<20} {pct:<15.2f}%")

        print()

    def print_top_objects(self, objects):
        """Print top objects by record count."""
        print("=" * 100)
        print("TOP OBJECTS BY RECORD COUNT")
        print("=" * 100)
        print()

        if not objects:
            print("❌ No object data available")
            return

        print(f"{'Object API Name':<40} {'Label':<30} {'Record Count':<15}")
        print("-" * 100)

        for obj in objects:
            print(f"{obj['object']:<40} {obj['label']:<30} {obj['count']:<15,}")

        print()

    def print_account_distribution(self, accounts):
        """Print storage distribution by account."""
        print("=" * 100)
        print("TOP ACCOUNTS BY DOCUMENT COUNT (DocListEntry__c)")
        print("=" * 100)
        print()

        if not accounts:
            print("❌ No account data available")
            return

        print(f"{'Account Name':<50} {'Document Count':<15}")
        print("-" * 100)

        total_docs = 0

        for record in accounts[:30]:  # Top 30
            account_name = record.get('Name') or '(Unknown)'
            doc_count = record['doc_count']

            print(f"{account_name[:48]:<50} {doc_count:<15,}")
            total_docs += doc_count

        print("-" * 100)
        print(f"{'TOTAL (Top 30)':<50} {total_docs:<15,}")
        print()

    def print_doclistentry_analysis(self, doclist_data):
        """Print DocListEntry__c analysis."""
        print("=" * 100)
        print("DOCLISTENTRY__C STORAGE ANALYSIS")
        print("=" * 100)
        print()

        count = doclist_data.get('count', 0)
        size = doclist_data.get('size_bytes', 0)
        note = doclist_data.get('note', '')

        print(f"📋 Total Records: {count:,}")
        print(f"💾 Estimated Data Storage: {self.format_size(size)}")
        print(f"ℹ️  Note: {note}")
        print()
        print("⚠️  IMPORTANT:")
        print("   - DocListEntry__c records consume DATA storage, not FILE storage")
        print("   - Each record contains metadata about documents")
        print("   - Actual files referenced by Document__c field consume FILE storage")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze Salesforce storage consumption"
    )
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed file type and object breakdowns'
    )
    parser.add_argument(
        '--top-objects',
        type=int,
        default=20,
        help='Number of top objects to show (default: 20)'
    )
    parser.add_argument(
        '--by-account',
        action='store_true',
        help='Show storage distribution by account'
    )
    parser.add_argument(
        '--user-count',
        type=int,
        default=100,
        help='Number of user licenses for limit calculation (default: 100)'
    )

    args = parser.parse_args()

    print("=" * 100)
    print("SALESFORCE STORAGE ANALYZER")
    print("=" * 100)
    print()

    analyzer = SalesforceStorageAnalyzer()

    try:
        # Get org limits
        limits = analyzer.get_org_limits()

        # Print summary
        analyzer.print_summary(limits, args.user_count)

        # Get file storage breakdown
        file_storage = analyzer.get_file_storage_usage()
        analyzer.print_file_storage_detail(file_storage)

        # DocListEntry analysis
        doclist_data = analyzer.get_doclistentry_storage()
        analyzer.print_doclistentry_analysis(doclist_data)

        # Detailed analysis
        if args.detailed:
            # File type breakdown
            file_types = analyzer.get_contentversion_by_type()
            analyzer.print_file_type_breakdown(file_types)

            # Top objects
            top_objects = analyzer.get_top_objects_by_count(args.top_objects)
            analyzer.print_top_objects(top_objects)

        # Account distribution
        if args.by_account:
            account_dist = analyzer.get_account_file_distribution()
            analyzer.print_account_distribution(account_dist)

        # Recommendations
        print("=" * 100)
        print("💡 RECOMMENDATIONS")
        print("=" * 100)
        print()

        if limits:
            file_storage_limits = limits.get('FileStorageMB', {})
            if file_storage_limits:
                used_pct = (file_storage_limits.get('Used', 0) / file_storage_limits.get('Max', 1) * 100)

                if used_pct >= 75:
                    print("⚠️  FILE STORAGE ACTIONS NEEDED:")
                    print("   1. Migrate files to external S3 storage (reduces file storage)")
                    print("   2. Archive old/unused ContentVersion records")
                    print("   3. Clean up duplicate files")
                    print("   4. Consider purchasing additional file storage ($5/GB/month)")
                    print()

            data_storage_limits = limits.get('DataStorageMB', {})
            if data_storage_limits:
                used_pct = (data_storage_limits.get('Used', 0) / data_storage_limits.get('Max', 1) * 100)

                if used_pct >= 75:
                    print("⚠️  DATA STORAGE ACTIONS NEEDED:")
                    print("   1. Archive old records to external database")
                    print("   2. Delete unnecessary test/demo data")
                    print("   3. Review and clean up large custom objects")
                    print("   4. Consider data archiving solutions (Big Objects, external archives)")
                    print()

        print("✅ MIGRATION BENEFITS:")
        print("   - Migrating files to S3 REDUCES file storage consumption")
        print("   - DocListEntry__c records remain (minimal data storage impact)")
        print("   - Frees up Salesforce storage for other uses")
        print("   - Cost savings vs purchasing additional Salesforce storage")
        print()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
