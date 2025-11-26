"""
COMPLETE SALESFORCE STORAGE ANALYSIS
=====================================
Analyzes ALL objects in Salesforce to determine storage consumption.
This is NOT about migration - this is about understanding current storage usage.
"""

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json
from simple_salesforce import Salesforce
from collections import defaultdict
import time

# Import config
try:
    import config
    SALESFORCE_CONFIG = config.SALESFORCE_CONFIG
except ImportError:
    print("❌ Error: config.py not found. Copy config_template.py to config.py and configure.")
    sys.exit(1)


class CompleteStorageAnalyzer:
    """Analyze ALL Salesforce storage consumption."""

    def __init__(self):
        self.sf = None
        self.connect_salesforce()

    def connect_salesforce(self):
        """Connect to Salesforce API."""
        try:
            sf_config = SALESFORCE_CONFIG
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

    def get_all_objects(self):
        """Get all objects (standard and custom) from Salesforce."""
        print("\n" + "=" * 100)
        print("STEP 1: DISCOVERING ALL SALESFORCE OBJECTS")
        print("=" * 100)

        try:
            describe = self.sf.describe()
            all_objects = describe['sobjects']

            # Categorize objects
            standard_objects = []
            custom_objects = []
            file_objects = []

            file_related = ['ContentDocument', 'ContentVersion', 'Attachment', 'Document']

            for obj in all_objects:
                obj_name = obj['name']

                if obj_name in file_related:
                    file_objects.append(obj_name)
                elif obj_name.endswith('__c'):
                    custom_objects.append(obj_name)
                else:
                    standard_objects.append(obj_name)

            print(f"\n📊 Object Discovery:")
            print(f"   Total Objects:    {len(all_objects):,}")
            print(f"   Standard Objects: {len(standard_objects):,}")
            print(f"   Custom Objects:   {len(custom_objects):,}")
            print(f"   File Objects:     {len(file_objects):,}")

            return {
                'standard': standard_objects,
                'custom': custom_objects,
                'file': file_objects,
                'all': [obj['name'] for obj in all_objects]
            }

        except Exception as e:
            print(f"❌ Error discovering objects: {e}")
            return None

    def count_records_in_object(self, object_name):
        """Count records in a single object."""
        try:
            query = f"SELECT COUNT(Id) total FROM {object_name}"
            result = self.sf.query(query)
            return result['records'][0]['total']
        except Exception as e:
            # Silently fail for objects we can't query
            return None

    def analyze_file_storage(self, file_objects):
        """Analyze file-related objects."""
        print("\n" + "=" * 100)
        print("STEP 2: FILE STORAGE ANALYSIS")
        print("=" * 100)

        file_counts = {}
        total_files = 0

        for obj_name in file_objects:
            count = self.count_records_in_object(obj_name)
            if count is not None:
                file_counts[obj_name] = count
                total_files += count
                print(f"   {obj_name:25s}: {count:>12,}")

        print(f"\n   {'TOTAL FILE OBJECTS':25s}: {total_files:>12,}")

        # Estimate file storage (rough estimate: average 1MB per file)
        estimated_file_storage_mb = total_files * 1.0  # 1MB average
        estimated_file_storage_gb = estimated_file_storage_mb / 1024

        print(f"\n📊 File Storage Estimate:")
        print(f"   Estimated: ~{estimated_file_storage_gb:.2f} GB")
        print(f"   (Assuming 1MB average file size)")

        return {
            'counts': file_counts,
            'total': total_files,
            'estimated_gb': estimated_file_storage_gb
        }

    def analyze_custom_objects(self, custom_objects):
        """Analyze custom objects (main data storage consumers)."""
        print("\n" + "=" * 100)
        print("STEP 3: CUSTOM OBJECTS ANALYSIS (DATA STORAGE)")
        print("=" * 100)

        custom_counts = {}
        total_custom_records = 0

        print("\n⏳ Counting records in custom objects (this may take a few minutes)...")

        # Sort by name for organized output
        custom_objects_sorted = sorted(custom_objects)

        for i, obj_name in enumerate(custom_objects_sorted, 1):
            count = self.count_records_in_object(obj_name)

            if count is not None and count > 0:
                custom_counts[obj_name] = count
                total_custom_records += count

                # Show progress every 50 objects
                if i % 50 == 0:
                    print(f"   Progress: {i}/{len(custom_objects_sorted)} objects checked...")

        # Sort by record count (descending)
        sorted_custom = sorted(custom_counts.items(), key=lambda x: x[1], reverse=True)

        print(f"\n📊 Top Custom Objects by Record Count:")
        print(f"{'Object Name':<40} {'Records':>15} {'Est. Storage (MB)':>20}")
        print("-" * 80)

        total_mb = 0
        for obj_name, count in sorted_custom[:50]:  # Top 50
            est_mb = (count * 2048) / (1024 * 1024)  # 2KB per record estimate
            total_mb += est_mb
            print(f"{obj_name:<40} {count:>15,} {est_mb:>20,.1f}")

        if len(sorted_custom) > 50:
            print(f"\n... and {len(sorted_custom) - 50} more custom objects with data")

        # Calculate total storage for ALL custom objects
        total_all_custom_mb = (total_custom_records * 2048) / (1024 * 1024)
        total_all_custom_gb = total_all_custom_mb / 1024

        print(f"\n{'TOTAL ALL CUSTOM OBJECTS':<40} {total_custom_records:>15,} {total_all_custom_mb:>20,.1f}")
        print(f"\n📊 Total Custom Objects Storage: ~{total_all_custom_gb:.2f} GB")

        return {
            'counts': custom_counts,
            'total_records': total_custom_records,
            'estimated_gb': total_all_custom_gb,
            'top_consumers': sorted_custom[:20]
        }

    def analyze_standard_objects(self, standard_objects):
        """Analyze key standard objects that consume significant storage."""
        print("\n" + "=" * 100)
        print("STEP 4: STANDARD OBJECTS ANALYSIS (DATA STORAGE)")
        print("=" * 100)

        # Key standard objects that typically have many records
        key_standard = [
            'Account', 'Contact', 'Lead', 'Opportunity', 'Case',
            'Task', 'Event', 'EmailMessage', 'User', 'CampaignMember',
            'OpportunityLineItem', 'Note', 'FeedItem', 'FeedComment'
        ]

        standard_counts = {}
        total_standard_records = 0

        print("\n📊 Key Standard Objects:")
        print(f"{'Object Name':<40} {'Records':>15} {'Est. Storage (MB)':>20}")
        print("-" * 80)

        for obj_name in key_standard:
            if obj_name in standard_objects:
                count = self.count_records_in_object(obj_name)

                if count is not None and count > 0:
                    standard_counts[obj_name] = count
                    total_standard_records += count
                    est_mb = (count * 2048) / (1024 * 1024)
                    print(f"{obj_name:<40} {count:>15,} {est_mb:>20,.1f}")

        total_standard_mb = (total_standard_records * 2048) / (1024 * 1024)
        total_standard_gb = total_standard_mb / 1024

        print(f"\n{'TOTAL KEY STANDARD OBJECTS':<40} {total_standard_records:>15,} {total_standard_mb:>20,.1f}")
        print(f"\n📊 Standard Objects Storage: ~{total_standard_gb:.2f} GB")

        return {
            'counts': standard_counts,
            'total_records': total_standard_records,
            'estimated_gb': total_standard_gb
        }

    def get_limits_from_api(self):
        """Get limits from Salesforce API."""
        print("\n" + "=" * 100)
        print("STEP 5: SALESFORCE LIMITS CHECK")
        print("=" * 100)

        limits = self.sf.limits()

        # Check for ContentDocument limit
        content_doc_info = None
        if 'MaxContentDocumentsLimit' in limits:
            max_docs = limits['MaxContentDocumentsLimit']['Max']
            remaining = limits['MaxContentDocumentsLimit']['Remaining']
            used = max_docs - remaining
            usage_pct = (used / max_docs * 100) if max_docs > 0 else 0

            content_doc_info = {
                'max': max_docs,
                'used': used,
                'remaining': remaining,
                'usage_pct': usage_pct
            }

            print(f"\n📊 ContentDocument Limit:")
            print(f"   Max:       {max_docs:,}")
            print(f"   Used:      {used:,}")
            print(f"   Remaining: {remaining:,}")
            print(f"   Usage:     {usage_pct:.2f}%")

            if usage_pct > 95:
                print(f"\n   🚨 CRITICAL: Near ContentDocument limit!")
            elif usage_pct > 80:
                print(f"\n   ⚠️  WARNING: High ContentDocument usage")

        # Check for storage keys (usually not available via API)
        has_data_storage = 'DataStorageMB' in limits
        has_file_storage = 'FileStorageMB' in limits

        if not has_data_storage and not has_file_storage:
            print(f"\n❌ Storage limits (DataStorageMB, FileStorageMB) not available via API")
            print(f"   These limits must be checked manually in:")
            print(f"   Setup → System Overview → Storage Usage")

        return {
            'content_document': content_doc_info,
            'has_data_storage_api': has_data_storage,
            'has_file_storage_api': has_file_storage
        }

    def generate_final_analysis(self, file_analysis, custom_analysis, standard_analysis, limits_info):
        """Generate comprehensive final analysis."""
        print("\n" + "=" * 100)
        print("🎯 COMPREHENSIVE STORAGE ANALYSIS")
        print("=" * 100)

        total_data_storage_gb = custom_analysis['estimated_gb'] + standard_analysis['estimated_gb']
        total_file_storage_gb = file_analysis['estimated_gb']

        print(f"\n📊 STORAGE BREAKDOWN:")
        print(f"\n1. FILE STORAGE (Actual Files):")
        print(f"   Total Files:      {file_analysis['total']:,}")
        print(f"   Estimated Size:   ~{total_file_storage_gb:.2f} GB")

        print(f"\n2. DATA STORAGE (Records/Metadata):")
        print(f"   Custom Objects:   {custom_analysis['total_records']:,} records (~{custom_analysis['estimated_gb']:.2f} GB)")
        print(f"   Standard Objects: {standard_analysis['total_records']:,} records (~{standard_analysis['estimated_gb']:.2f} GB)")
        print(f"   TOTAL DATA:       ~{total_data_storage_gb:.2f} GB")

        print(f"\n3. CONTENTDOCUMENT LIMIT:")
        if limits_info['content_document']:
            cd = limits_info['content_document']
            print(f"   Usage: {cd['used']:,} of {cd['max']:,} ({cd['usage_pct']:.2f}%)")
            if cd['usage_pct'] < 50:
                print(f"   ✅ NOT an issue")
            elif cd['usage_pct'] < 80:
                print(f"   ⚠️  Moderate usage")
            else:
                print(f"   🚨 HIGH usage")

        # Identify top consumers
        print(f"\n" + "=" * 100)
        print("🔍 TOP STORAGE CONSUMERS")
        print("=" * 100)

        print(f"\n📌 Top 10 Custom Objects:")
        for i, (obj_name, count) in enumerate(custom_analysis['top_consumers'][:10], 1):
            est_gb = ((count * 2048) / (1024 * 1024)) / 1024
            print(f"   {i:2d}. {obj_name:<35s} {count:>12,} records (~{est_gb:>6.2f} GB)")

        # Determine likely storage issue
        print(f"\n" + "=" * 100)
        print("💡 DIAGNOSIS")
        print("=" * 100)

        file_to_data_ratio = total_file_storage_gb / total_data_storage_gb if total_data_storage_gb > 0 else 0

        print(f"\n📊 Storage Ratio Analysis:")
        print(f"   File Storage:    ~{total_file_storage_gb:.2f} GB")
        print(f"   Data Storage:    ~{total_data_storage_gb:.2f} GB")
        print(f"   Ratio (File:Data): {file_to_data_ratio:.4f}")

        if file_to_data_ratio < 0.05:  # File storage is less than 5% of data storage
            print(f"\n🎯 LIKELY ISSUE: DATA STORAGE")
            print(f"   ❌ File storage is minimal ({total_file_storage_gb:.2f} GB)")
            print(f"   ⚠️  Data storage is significant ({total_data_storage_gb:.2f} GB)")
            print(f"   💾 You are likely hitting DATA STORAGE limit, not FILE STORAGE")

            print(f"\n📋 WHAT THIS MEANS:")
            print(f"   - Storage issue is from RECORDS/METADATA, not FILES")
            print(f"   - Each record consumes ~2KB of data storage")
            print(f"   - {custom_analysis['total_records'] + standard_analysis['total_records']:,} total records")

            print(f"\n❌ WILL S3 FILE MIGRATION HELP?")
            print(f"   NO - S3 migration moves FILES, not RECORDS")
            print(f"   - DocListEntry__c records will still exist in Salesforce")
            print(f"   - Moving files to S3 only changes the URL field")
            print(f"   - Record count stays the same = same data storage")

            print(f"\n✅ WHAT WOULD ACTUALLY HELP:")
            print(f"   1. DELETE or ARCHIVE old records")
            print(f"   2. Export historical data to external system")
            print(f"   3. Implement data retention policies")
            print(f"   4. Use Salesforce Big Objects for archival")

        elif file_to_data_ratio > 0.5:  # File storage is more than 50% of data storage
            print(f"\n🎯 LIKELY ISSUE: FILE STORAGE")
            print(f"   ⚠️  File storage is significant ({total_file_storage_gb:.2f} GB)")
            print(f"   📄 {file_analysis['total']:,} files stored in Salesforce")
            print(f"   💾 You are likely hitting FILE STORAGE limit")

            print(f"\n✅ WILL S3 FILE MIGRATION HELP?")
            print(f"   YES - Moving files to S3 will free up file storage")
            print(f"   - Estimated space freed: ~{total_file_storage_gb:.2f} GB")

        else:
            print(f"\n🎯 MIXED STORAGE USAGE")
            print(f"   Both file and data storage are being used")
            print(f"   Need to check Salesforce UI for exact limits")

        # Enterprise Edition storage information
        print(f"\n" + "=" * 100)
        print("📖 SALESFORCE ENTERPRISE EDITION STORAGE LIMITS")
        print("=" * 100)

        print(f"\nStandard Allocations:")
        print(f"   Data Storage: 10 GB + 20 MB per user license")
        print(f"   File Storage: 10 GB + 2 GB per user license")

        print(f"\n⚠️  IMPORTANT:")
        print(f"   The limits() API does NOT return actual storage limits")
        print(f"   You MUST check Salesforce UI to see your actual limits:")
        print(f"   Setup → System Overview → Storage Usage")

        print(f"\n" + "=" * 100)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 100)

        # Summary for easy reference
        return {
            'file_storage_gb': total_file_storage_gb,
            'data_storage_gb': total_data_storage_gb,
            'total_files': file_analysis['total'],
            'total_records': custom_analysis['total_records'] + standard_analysis['total_records'],
            'likely_issue': 'DATA_STORAGE' if file_to_data_ratio < 0.05 else 'FILE_STORAGE' if file_to_data_ratio > 0.5 else 'MIXED',
            'top_consumers': custom_analysis['top_consumers'][:10]
        }

    def run_analysis(self):
        """Run complete storage analysis."""
        print("\n" + "=" * 100)
        print("COMPLETE SALESFORCE STORAGE ANALYSIS")
        print("=" * 100)
        print("\nThis will analyze ALL objects to determine storage consumption.")
        print("This may take several minutes...")

        start_time = time.time()

        # Step 1: Discover all objects
        objects = self.get_all_objects()
        if not objects:
            return

        # Step 2: Analyze file storage
        file_analysis = self.analyze_file_storage(objects['file'])

        # Step 3: Analyze custom objects
        custom_analysis = self.analyze_custom_objects(objects['custom'])

        # Step 4: Analyze standard objects
        standard_analysis = self.analyze_standard_objects(objects['standard'])

        # Step 5: Get limits
        limits_info = self.get_limits_from_api()

        # Step 6: Generate final analysis
        final_analysis = self.generate_final_analysis(
            file_analysis,
            custom_analysis,
            standard_analysis,
            limits_info
        )

        elapsed_time = time.time() - start_time
        print(f"\n⏱️  Analysis completed in {elapsed_time:.1f} seconds")

        return final_analysis


def main():
    try:
        analyzer = CompleteStorageAnalyzer()
        analyzer.run_analysis()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
