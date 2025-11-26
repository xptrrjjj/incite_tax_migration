#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Complete Salesforce Storage Audit
==================================

COMPREHENSIVE storage analysis for Incite Tax's Salesforce org.
Analyzes EVERY object, EVERY file type, EVERY storage category to identify
what's consuming their Enterprise Edition storage limits.

This script analyzes:
- Data Storage: ALL standard and custom objects with record counts
- File Storage: ALL ContentVersion, Attachment, Document records
- Storage by file type, size distribution, object breakdown
- Identifies what's hitting the cap

Usage:
python salesforce_storage_audit_full.py
python salesforce_storage_audit_full.py --export-csv
python salesforce_storage_audit_full.py --detailed
"""

import sys
import io
from datetime import datetime
from collections import defaultdict
import argparse
from simple_salesforce import Salesforce
import csv
from pathlib import Path

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


class ComprehensiveStorageAuditor:
    """Complete Salesforce storage audit - analyze EVERYTHING."""

    def __init__(self):
        """Initialize Salesforce connection."""
        self.sf = None
        self.all_results = {
            'objects': [],
            'file_storage': {},
            'file_types': [],
            'limits': None,
            'timestamp': datetime.now().isoformat()
        }
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
        """Get ALL organization limits."""
        print("📊 Retrieving organization limits...")
        try:
            limits = self.sf.limits()

            # Extract key storage info
            data_storage = limits.get('DataStorageMB', {})
            file_storage = limits.get('FileStorageMB', {})
            api_usage = limits.get('DailyApiRequests', {})

            print(f"   📊 Data Storage: {data_storage.get('Used', 0):,.0f} / {data_storage.get('Max', 0):,.0f} MB ({data_storage.get('Used', 0) / data_storage.get('Max', 1) * 100:.1f}%)")
            print(f"   📁 File Storage: {file_storage.get('Used', 0):,.0f} / {file_storage.get('Max', 0):,.0f} MB ({file_storage.get('Used', 0) / file_storage.get('Max', 1) * 100:.1f}%)")
            print(f"   🔌 API Calls: {api_usage.get('Used', 0):,} / {api_usage.get('Max', 0):,} ({api_usage.get('Used', 0) / api_usage.get('Max', 1) * 100:.1f}%)")

            self.all_results['limits'] = limits
            return limits
        except Exception as e:
            print(f"❌ Failed: {e}")
            return None

    def analyze_all_objects(self):
        """Analyze EVERY object in the org - no limits."""
        print("\n🔍 ANALYZING ALL OBJECTS IN ORG...")
        print("   This will take several minutes for large orgs...")
        print()

        try:
            # Get all objects
            describe = self.sf.describe()
            all_objects = describe['sobjects']

            total_objects = len(all_objects)
            processed = 0

            print(f"   Found {total_objects} total objects")
            print(f"   Querying record counts for each object...")
            print()

            object_data = []

            for obj in all_objects:
                obj_name = obj['name']
                obj_label = obj['label']
                obj_type = 'Custom' if obj['custom'] else 'Standard'

                processed += 1

                # Progress indicator
                if processed % 50 == 0:
                    print(f"   Progress: {processed}/{total_objects} objects processed...")

                try:
                    # Count records
                    query = f"SELECT COUNT(Id) total FROM {obj_name}"
                    result = self.sf.query(query)
                    count = result['records'][0]['total']

                    # Estimate size (conservative: 2KB per record for data storage)
                    estimated_size_bytes = count * 2048

                    object_data.append({
                        'object_name': obj_name,
                        'label': obj_label,
                        'type': obj_type,
                        'record_count': count,
                        'estimated_size_bytes': estimated_size_bytes,
                        'estimated_size_mb': estimated_size_bytes / (1024 * 1024),
                        'queryable': obj.get('queryable', False),
                        'deletable': obj.get('deletable', False),
                        'updateable': obj.get('updateable', False)
                    })

                except Exception as e:
                    # Skip objects that can't be queried
                    continue

            # Sort by record count descending
            object_data.sort(key=lambda x: x['record_count'], reverse=True)

            print(f"\n   ✅ Analyzed {len(object_data)} queryable objects")
            print(f"   📊 Found {sum(o['record_count'] for o in object_data):,} total records")
            print(f"   💾 Estimated total data storage: {sum(o['estimated_size_mb'] for o in object_data):,.2f} MB")

            self.all_results['objects'] = object_data
            return object_data

        except Exception as e:
            print(f"❌ Failed: {e}")
            import traceback
            traceback.print_exc()
            return []

    def analyze_file_storage_complete(self):
        """Analyze ALL file storage - complete breakdown."""
        print("\n📁 ANALYZING FILE STORAGE (COMPLETE)...")

        file_storage = {}

        # ContentVersion
        print("   Analyzing ContentVersion...")
        try:
            cv_query = """
                SELECT COUNT(Id) record_count, SUM(ContentSize) total_size
                FROM ContentVersion
                WHERE IsLatest = true
            """
            cv_result = self.sf.query(cv_query)
            if cv_result['records']:
                record = cv_result['records'][0]
                count = record['record_count'] or 0
                size = record['total_size'] or 0
                file_storage['ContentVersion'] = {
                    'count': count,
                    'size_bytes': size,
                    'size_mb': size / (1024 * 1024),
                    'size_gb': size / (1024 * 1024 * 1024)
                }
                print(f"      ✅ {count:,} records, {size / (1024 * 1024 * 1024):.2f} GB")
        except Exception as e:
            print(f"      ❌ Failed: {e}")

        # Attachment
        print("   Analyzing Attachment...")
        try:
            att_query = """
                SELECT COUNT(Id) record_count, SUM(BodyLength) total_size
                FROM Attachment
            """
            att_result = self.sf.query(att_query)
            if att_result['records']:
                record = att_result['records'][0]
                count = record['record_count'] or 0
                size = record['total_size'] or 0
                file_storage['Attachment'] = {
                    'count': count,
                    'size_bytes': size,
                    'size_mb': size / (1024 * 1024),
                    'size_gb': size / (1024 * 1024 * 1024)
                }
                print(f"      ✅ {count:,} records, {size / (1024 * 1024 * 1024):.2f} GB")
        except Exception as e:
            print(f"      ❌ Failed: {e}")

        # Document
        print("   Analyzing Document...")
        try:
            doc_query = """
                SELECT COUNT(Id) record_count, SUM(BodyLength) total_size
                FROM Document
            """
            doc_result = self.sf.query(doc_query)
            if doc_result['records']:
                record = doc_result['records'][0]
                count = record['record_count'] or 0
                size = record['total_size'] or 0
                file_storage['Document'] = {
                    'count': count,
                    'size_bytes': size,
                    'size_mb': size / (1024 * 1024),
                    'size_gb': size / (1024 * 1024 * 1024)
                }
                print(f"      ✅ {count:,} records, {size / (1024 * 1024 * 1024):.2f} GB")
        except Exception as e:
            print(f"      ❌ Failed: {e}")

        total_file_size_gb = sum(f['size_gb'] for f in file_storage.values())
        print(f"\n   ✅ Total File Storage: {total_file_size_gb:.2f} GB")

        self.all_results['file_storage'] = file_storage
        return file_storage

    def analyze_all_file_types(self):
        """Analyze ALL file types in ContentVersion - no limits."""
        print("\n📂 ANALYZING ALL FILE TYPES...")

        try:
            query = """
                SELECT FileExtension, COUNT(Id) record_count, SUM(ContentSize) total_size
                FROM ContentVersion
                WHERE IsLatest = true
                GROUP BY FileExtension
                ORDER BY SUM(ContentSize) DESC
            """

            result = self.sf.query(query)
            file_types = result['records']

            # Format data
            formatted_types = []
            for record in file_types:
                ext = record['FileExtension'] or '(no extension)'
                count = record['record_count'] or 0
                size = record['total_size'] or 0

                formatted_types.append({
                    'extension': ext,
                    'count': count,
                    'size_bytes': size,
                    'size_mb': size / (1024 * 1024),
                    'size_gb': size / (1024 * 1024 * 1024),
                    'avg_size_bytes': size / count if count > 0 else 0
                })

            print(f"   ✅ Found {len(formatted_types)} unique file types")

            self.all_results['file_types'] = formatted_types
            return formatted_types

        except Exception as e:
            print(f"❌ Failed: {e}")
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

    def print_complete_report(self):
        """Print comprehensive storage report."""
        print("\n" + "=" * 120)
        print("COMPLETE SALESFORCE STORAGE AUDIT REPORT")
        print("=" * 120)
        print()

        limits = self.all_results.get('limits')
        if limits:
            self.print_storage_limits(limits)

        self.print_file_storage_report()
        self.print_file_type_report()
        self.print_object_report()
        self.print_storage_impact_analysis()

    def print_storage_limits(self, limits):
        """Print storage limits section."""
        print("📊 STORAGE LIMITS & USAGE")
        print("-" * 120)

        data_storage = limits.get('DataStorageMB', {})
        file_storage = limits.get('FileStorageMB', {})

        if data_storage:
            used = data_storage.get('Used', 0)
            max_storage = data_storage.get('Max', 0)
            remaining = data_storage.get('Remaining', 0)
            pct = (used / max_storage * 100) if max_storage > 0 else 0

            status = "🔴 CRITICAL" if pct >= 95 else "⚠️  WARNING" if pct >= 85 else "⚡ NOTICE" if pct >= 75 else "✅ HEALTHY"

            print(f"\nDATA STORAGE:")
            print(f"   Used: {used:,.2f} MB ({self.format_size(used * 1024 * 1024)})")
            print(f"   Max: {max_storage:,.2f} MB ({self.format_size(max_storage * 1024 * 1024)})")
            print(f"   Remaining: {remaining:,.2f} MB ({self.format_size(remaining * 1024 * 1024)})")
            print(f"   Status: {status} ({pct:.1f}% used)")

            if pct >= 75:
                print(f"   🚨 ACTION REQUIRED: Data storage at {pct:.1f}% capacity!")

        if file_storage:
            used = file_storage.get('Used', 0)
            max_storage = file_storage.get('Max', 0)
            remaining = file_storage.get('Remaining', 0)
            pct = (used / max_storage * 100) if max_storage > 0 else 0

            status = "🔴 CRITICAL" if pct >= 95 else "⚠️  WARNING" if pct >= 85 else "⚡ NOTICE" if pct >= 75 else "✅ HEALTHY"

            print(f"\nFILE STORAGE:")
            print(f"   Used: {used:,.2f} MB ({self.format_size(used * 1024 * 1024)})")
            print(f"   Max: {max_storage:,.2f} MB ({self.format_size(max_storage * 1024 * 1024)})")
            print(f"   Remaining: {remaining:,.2f} MB ({self.format_size(remaining * 1024 * 1024)})")
            print(f"   Status: {status} ({pct:.1f}% used)")

            if pct >= 75:
                print(f"   🚨 ACTION REQUIRED: File storage at {pct:.1f}% capacity!")

        print()

    def print_file_storage_report(self):
        """Print file storage breakdown."""
        print("\n📁 FILE STORAGE BREAKDOWN")
        print("-" * 120)

        file_storage = self.all_results.get('file_storage', {})

        if not file_storage:
            print("No file storage data available")
            return

        print(f"\n{'Type':<20} {'Count':<15} {'Total Size (GB)':<20} {'Avg Size':<20} {'% of Total':<15}")
        print("-" * 120)

        total_size = sum(f['size_gb'] for f in file_storage.values())

        for storage_type, data in sorted(file_storage.items(), key=lambda x: x[1]['size_gb'], reverse=True):
            count = data['count']
            size_gb = data['size_gb']
            avg_size = data['size_bytes'] / count if count > 0 else 0
            pct = (size_gb / total_size * 100) if total_size > 0 else 0

            print(f"{storage_type:<20} {count:<15,} {size_gb:<20.2f} {self.format_size(avg_size):<20} {pct:<15.1f}%")

        print("-" * 120)
        print(f"{'TOTAL':<20} {sum(f['count'] for f in file_storage.values()):<15,} {total_size:<20.2f} {'':<20} {'100.0':<15}%")
        print()

    def print_file_type_report(self):
        """Print ALL file types."""
        print("\n📂 FILE TYPE BREAKDOWN (ALL TYPES)")
        print("-" * 120)

        file_types = self.all_results.get('file_types', [])

        if not file_types:
            print("No file type data available")
            return

        print(f"\n{'Extension':<15} {'Count':<15} {'Total Size (GB)':<20} {'Avg Size':<20} {'% of Total':<15}")
        print("-" * 120)

        total_size = sum(f['size_gb'] for f in file_types)

        for ft in file_types:  # ALL file types, no limit
            ext = ft['extension']
            count = ft['count']
            size_gb = ft['size_gb']
            avg_size = ft['avg_size_bytes']
            pct = (size_gb / total_size * 100) if total_size > 0 else 0

            print(f"{ext:<15} {count:<15,} {size_gb:<20.2f} {self.format_size(avg_size):<20} {pct:<15.2f}%")

        print()

    def print_object_report(self):
        """Print ALL objects with records."""
        print("\n📊 OBJECT BREAKDOWN (ALL OBJECTS WITH RECORDS)")
        print("-" * 120)

        objects = self.all_results.get('objects', [])

        if not objects:
            print("No object data available")
            return

        # Filter to only objects with records
        objects_with_records = [o for o in objects if o['record_count'] > 0]

        print(f"\n{'Object Name':<40} {'Type':<10} {'Records':<15} {'Est. Size (MB)':<20} {'% of Total Records':<20}")
        print("-" * 120)

        total_records = sum(o['record_count'] for o in objects_with_records)

        for obj in objects_with_records:  # ALL objects, no limit
            name = obj['object_name']
            obj_type = obj['type']
            count = obj['record_count']
            size_mb = obj['estimated_size_mb']
            pct = (count / total_records * 100) if total_records > 0 else 0

            print(f"{name:<40} {obj_type:<10} {count:<15,} {size_mb:<20.2f} {pct:<20.2f}%")

        print("-" * 120)
        print(f"{'TOTAL':<40} {'':<10} {total_records:<15,} {sum(o['estimated_size_mb'] for o in objects_with_records):<20.2f} {'100.0':<20}%")
        print()

    def print_storage_impact_analysis(self):
        """Analyze what's causing storage issues."""
        print("\n💡 STORAGE IMPACT ANALYSIS")
        print("-" * 120)
        print()

        limits = self.all_results.get('limits', {})
        objects = self.all_results.get('objects', [])
        file_storage = self.all_results.get('file_storage', {})
        file_types = self.all_results.get('file_types', [])

        # Data Storage Analysis
        data_storage = limits.get('DataStorageMB', {})
        if data_storage:
            used_pct = (data_storage.get('Used', 0) / data_storage.get('Max', 1) * 100)

            if used_pct >= 75:
                print("🚨 DATA STORAGE ISSUE DETECTED")
                print(f"   Current usage: {used_pct:.1f}% of limit")
                print()
                print("   TOP 10 DATA CONSUMERS:")

                top_objects = sorted(objects, key=lambda x: x['record_count'], reverse=True)[:10]
                for i, obj in enumerate(top_objects, 1):
                    print(f"   {i}. {obj['object_name']}: {obj['record_count']:,} records (~{obj['estimated_size_mb']:.2f} MB)")
                print()

        # File Storage Analysis
        file_storage_limits = limits.get('FileStorageMB', {})
        if file_storage_limits:
            used_pct = (file_storage_limits.get('Used', 0) / file_storage_limits.get('Max', 1) * 100)

            if used_pct >= 75:
                print("🚨 FILE STORAGE ISSUE DETECTED")
                print(f"   Current usage: {used_pct:.1f}% of limit")
                print()
                print("   FILE STORAGE BREAKDOWN:")

                for storage_type, data in sorted(file_storage.items(), key=lambda x: x[1]['size_gb'], reverse=True):
                    print(f"   - {storage_type}: {data['count']:,} files, {data['size_gb']:.2f} GB")

                print()
                print("   TOP 10 FILE TYPE CONSUMERS:")

                top_types = sorted(file_types, key=lambda x: x['size_gb'], reverse=True)[:10]
                for i, ft in enumerate(top_types, 1):
                    print(f"   {i}. {ft['extension']}: {ft['count']:,} files, {ft['size_gb']:.2f} GB")
                print()

        # Recommendations
        print("\n💡 RECOMMENDATIONS:")
        print()

        if file_storage_limits and (file_storage_limits.get('Used', 0) / file_storage_limits.get('Max', 1) * 100) >= 75:
            print("   FILE STORAGE ACTIONS:")
            print("   1. ✅ Migrate files to external S3 storage (THIS MIGRATION PROJECT)")
            print("   2. 🗑️  Archive/delete old ContentVersion records")
            print("   3. 🔍 Identify and remove duplicate files")
            print("   4. 💰 Alternative: Purchase additional storage ($5/GB/month)")
            print()

        if data_storage and (data_storage.get('Used', 0) / data_storage.get('Max', 1) * 100) >= 75:
            print("   DATA STORAGE ACTIONS:")
            print("   1. 🗄️  Archive old records to external database")
            print("   2. 🗑️  Delete test/demo data")
            print("   3. 🔍 Review large custom objects for cleanup opportunities")
            print("   4. 📦 Consider Big Objects for historical data")
            print()

    def export_to_csv(self, output_dir="storage_audit_export"):
        """Export all results to CSV files."""
        print(f"\n📤 EXPORTING RESULTS TO CSV...")

        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Export objects
        objects_file = output_path / f"objects_{timestamp}.csv"
        with open(objects_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['object_name', 'label', 'type', 'record_count', 'estimated_size_mb'])
            writer.writeheader()
            writer.writerows(self.all_results['objects'])
        print(f"   ✅ Objects exported to: {objects_file}")

        # Export file types
        file_types_file = output_path / f"file_types_{timestamp}.csv"
        with open(file_types_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['extension', 'count', 'size_gb', 'avg_size_bytes'])
            writer.writeheader()
            writer.writerows(self.all_results['file_types'])
        print(f"   ✅ File types exported to: {file_types_file}")

        # Export file storage summary
        file_storage_file = output_path / f"file_storage_{timestamp}.csv"
        with open(file_storage_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Storage Type', 'Count', 'Size (GB)'])
            for storage_type, data in self.all_results['file_storage'].items():
                writer.writerow([storage_type, data['count'], data['size_gb']])
        print(f"   ✅ File storage exported to: {file_storage_file}")

        print(f"\n   📁 All exports saved to: {output_path.absolute()}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Complete Salesforce storage audit - analyze EVERYTHING"
    )
    parser.add_argument(
        '--export-csv',
        action='store_true',
        help='Export results to CSV files'
    )
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed analysis (same as default)'
    )

    args = parser.parse_args()

    print("=" * 120)
    print("COMPLETE SALESFORCE STORAGE AUDIT")
    print("=" * 120)
    print()
    print("⚠️  NOTE: This will analyze EVERY object and file in your Salesforce org.")
    print("   Estimated time: 5-15 minutes for large orgs")
    print()

    auditor = ComprehensiveStorageAuditor()

    try:
        # Get limits first
        auditor.get_org_limits()

        # Analyze everything
        auditor.analyze_all_objects()
        auditor.analyze_file_storage_complete()
        auditor.analyze_all_file_types()

        # Print complete report
        auditor.print_complete_report()

        # Export if requested
        if args.export_csv:
            auditor.export_to_csv()

        print("\n✅ AUDIT COMPLETE")
        print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
