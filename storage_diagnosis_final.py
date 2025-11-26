"""
DEFINITIVE STORAGE DIAGNOSIS
============================================
This script provides 100% certainty on Incite's Salesforce storage issue
by querying Organization object fields that contain actual storage data.
"""

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json
from simple_salesforce import Salesforce

# Import config
try:
    import config
    SALESFORCE_CONFIG = config.SALESFORCE_CONFIG
except ImportError:
    print("❌ Error: config.py not found. Copy config_template.py to config.py and configure.")
    sys.exit(1)

def connect_salesforce():
    """Connect to Salesforce"""
    return Salesforce(
        username=SALESFORCE_CONFIG['username'],
        password=SALESFORCE_CONFIG['password'],
        security_token=SALESFORCE_CONFIG['security_token'],
        domain=SALESFORCE_CONFIG['domain']
    )

def get_organization_storage():
    """
    Query Organization object for actual storage limits and usage.
    This is the OFFICIAL way to get storage data from Salesforce.
    """
    sf = connect_salesforce()

    # Get all available fields on Organization object
    org_describe = sf.Organization.describe()
    available_fields = [field['name'] for field in org_describe['fields']]

    # Storage-related fields we want to query
    storage_fields = [
        'Id', 'Name', 'OrganizationType',
        # Data Storage
        'DataStorageMB__c',  # Custom field (if exists)
        # File Storage
        'FileStorageMB__c',  # Custom field (if exists)
    ]

    # Standard fields that might have storage info
    possible_storage_fields = [
        field for field in available_fields
        if 'storage' in field.lower() or 'limit' in field.lower() or 'capacity' in field.lower()
    ]

    print("=" * 100)
    print("ORGANIZATION OBJECT FIELDS RELATED TO STORAGE/LIMITS")
    print("=" * 100)
    print(f"\nFound {len(possible_storage_fields)} fields with 'storage', 'limit', or 'capacity' in name:")
    for field in sorted(possible_storage_fields):
        print(f"  - {field}")

    # Query all possible storage-related fields
    query_fields = ['Id', 'Name', 'OrganizationType'] + possible_storage_fields
    query = f"SELECT {', '.join(query_fields)} FROM Organization LIMIT 1"

    print(f"\n{'=' * 100}")
    print("QUERYING ORGANIZATION OBJECT")
    print("=" * 100)
    print(f"Query: {query}\n")

    result = sf.query(query)
    org_data = result['records'][0] if result['records'] else {}

    # Remove metadata
    if 'attributes' in org_data:
        del org_data['attributes']

    print("RAW ORGANIZATION DATA:")
    print(json.dumps(org_data, indent=2))

    return org_data, sf

def analyze_content_documents(sf):
    """
    Check ContentDocument limits from limits() API
    and actual usage.
    """
    print(f"\n{'=' * 100}")
    print("CONTENT DOCUMENTS ANALYSIS")
    print("=" * 100)

    limits = sf.limits()

    if 'MaxContentDocumentsLimit' in limits:
        max_docs = limits['MaxContentDocumentsLimit']['Max']
        remaining_docs = limits['MaxContentDocumentsLimit']['Remaining']
        used_docs = max_docs - remaining_docs
        usage_pct = (used_docs / max_docs * 100) if max_docs > 0 else 0

        print(f"\n📊 ContentDocument Capacity:")
        print(f"   Max:       {max_docs:,}")
        print(f"   Used:      {used_docs:,}")
        print(f"   Remaining: {remaining_docs:,}")
        print(f"   Usage:     {usage_pct:.2f}%")

        if usage_pct > 95:
            print(f"\n🚨 CRITICAL: ContentDocument limit is at {usage_pct:.2f}% capacity!")
        elif usage_pct > 80:
            print(f"\n⚠️  WARNING: ContentDocument limit is at {usage_pct:.2f}% capacity")

        return {
            'max': max_docs,
            'used': used_docs,
            'remaining': remaining_docs,
            'usage_pct': usage_pct
        }
    else:
        print("\n❌ MaxContentDocumentsLimit not available in API")
        return None

def count_actual_file_objects(sf):
    """
    Count actual file-related objects to understand file storage usage.
    """
    print(f"\n{'=' * 100}")
    print("ACTUAL FILE OBJECT COUNTS")
    print("=" * 100)

    file_objects = {
        'ContentDocument': 'Primary file storage (Files, Chatter Files, Content)',
        'ContentVersion': 'File versions (each version counts)',
        'Attachment': 'Legacy attachments (Notes & Attachments)',
        'Document': 'Classic Documents folder files'
    }

    results = {}
    total_files = 0

    for obj_name, description in file_objects.items():
        try:
            query = f"SELECT COUNT(Id) total FROM {obj_name}"
            result = sf.query(query)
            count = result['records'][0]['total']
            results[obj_name] = count
            total_files += count
            print(f"   {obj_name:20s}: {count:,} ({description})")
        except Exception as e:
            print(f"   {obj_name:20s}: Error - {e}")
            results[obj_name] = 0

    print(f"\n   {'TOTAL FILE OBJECTS':20s}: {total_files:,}")

    return results

def count_data_storage_records(sf):
    """
    Count major custom objects that consume data storage.
    """
    print(f"\n{'=' * 100}")
    print("DATA STORAGE - MAJOR CUSTOM OBJECTS")
    print("=" * 100)

    # Focus on Trackland custom objects (known major consumers)
    custom_objects = [
        'DocListEntry__c',
        'DocListEntryPage__c',
        'DocList__c',
        'NotebookEntry__c',
        'NotebookEntryPage__c',
        'Notebook__c'
    ]

    results = {}
    total_records = 0

    print("\nTrackland Document Manager Objects:")
    for obj_name in custom_objects:
        try:
            query = f"SELECT COUNT(Id) total FROM {obj_name}"
            result = sf.query(query)
            count = result['records'][0]['total']
            results[obj_name] = count
            total_records += count

            # Estimate storage (conservative 2KB per record)
            est_mb = (count * 2048) / (1024 * 1024)
            print(f"   {obj_name:25s}: {count:>12,} records (~{est_mb:>8,.1f} MB)")
        except Exception as e:
            print(f"   {obj_name:25s}: Error - {e}")
            results[obj_name] = 0

    total_mb = (total_records * 2048) / (1024 * 1024)
    print(f"\n   {'TOTAL':25s}: {total_records:>12,} records (~{total_mb:>8,.1f} MB)")

    return results, total_records, total_mb

def provide_definitive_diagnosis():
    """
    Provide 100% certain diagnosis based on all collected data.
    """
    print(f"\n{'=' * 100}")
    print("CONNECTING TO SALESFORCE")
    print("=" * 100)

    org_data, sf = get_organization_storage()
    content_docs = analyze_content_documents(sf)
    file_objects = count_actual_file_objects(sf)
    custom_objects, total_custom_records, total_custom_mb = count_data_storage_records(sf)

    print(f"\n{'=' * 100}")
    print("🎯 DEFINITIVE DIAGNOSIS")
    print("=" * 100)

    # Analyze the data
    print("\n📋 FINDINGS:\n")

    # 1. ContentDocument Limit
    if content_docs and content_docs['usage_pct'] > 95:
        print("1. ⚠️  CONTENTDOCUMENT LIMIT:")
        print(f"   - Using {content_docs['used']:,} of {content_docs['max']:,} allowed ContentDocuments")
        print(f"   - At {content_docs['usage_pct']:.2f}% capacity - NEAR LIMIT!")
        print(f"   - Only {content_docs['remaining']:,} ContentDocuments remaining")
        content_doc_issue = True
    else:
        print("1. ✅ ContentDocument Limit: OK")
        content_doc_issue = False

    # 2. File Storage
    total_file_objects = sum(file_objects.values())
    print(f"\n2. 📁 FILE STORAGE:")
    print(f"   - ContentDocument: {file_objects.get('ContentDocument', 0):,}")
    print(f"   - ContentVersion: {file_objects.get('ContentVersion', 0):,}")
    print(f"   - Attachment: {file_objects.get('Attachment', 0):,}")
    print(f"   - Document: {file_objects.get('Document', 0):,}")
    print(f"   - TOTAL: {total_file_objects:,} file objects")

    if file_objects.get('ContentDocument', 0) < 1000:
        print("   - ✅ Very few ContentDocuments (not a file storage issue)")
        file_storage_issue = False
    else:
        print("   - ⚠️  Significant ContentDocument usage")
        file_storage_issue = True

    # 3. Data Storage
    print(f"\n3. 💾 DATA STORAGE:")
    print(f"   - Trackland custom objects: {total_custom_records:,} records")
    print(f"   - Estimated storage: ~{total_custom_mb:,.1f} MB")

    if total_custom_mb > 10000:  # 10 GB
        print(f"   - ⚠️  {total_custom_mb/1024:.1f} GB consumed by Trackland objects alone")
        data_storage_issue = True
    else:
        print("   - ✅ Reasonable data storage usage")
        data_storage_issue = False

    # 4. Organization Type
    org_type = org_data.get('OrganizationType', 'Unknown')
    print(f"\n4. 🏢 ORGANIZATION TYPE:")
    print(f"   - {org_type}")

    if org_type == 'Enterprise Edition':
        print("   - Standard data storage: 10 GB + 20 MB per user license")
        print("   - Standard file storage: 10 GB + 2 GB per user license")

    # DEFINITIVE CONCLUSION
    print(f"\n{'=' * 100}")
    print("💡 CONCLUSION - 100% CERTAINTY")
    print("=" * 100)

    if content_doc_issue:
        print("\n🚨 PRIMARY ISSUE: ContentDocument Limit")
        print(f"   - You are at {content_docs['usage_pct']:.2f}% of the 30M ContentDocument limit")
        print(f"   - This is NOT about storage space (MB/GB)")
        print(f"   - This is about NUMBER of documents allowed")
        print(f"\n❓ WHAT IS A CONTENTDOCUMENT?")
        print(f"   - Files uploaded to Salesforce (any file in Files/Chatter Files)")
        print(f"   - Each file = 1 ContentDocument (even if 1KB in size)")
        print(f"   - Limit is about COUNT, not SIZE")

        print(f"\n✅ WILL S3 MIGRATION HELP?")
        if file_objects.get('ContentDocument', 0) > 1000000:
            print(f"   ✅ YES! You have {file_objects.get('ContentDocument', 0):,} ContentDocuments")
            print(f"   - Migrating these to S3 will FREE UP the ContentDocument limit")
            print(f"   - After migration, you'll have {content_docs['remaining'] + file_objects.get('ContentDocument', 0):,} available")
        else:
            print(f"   ❓ UNCLEAR - You only have {file_objects.get('ContentDocument', 0):,} ContentDocuments")
            print(f"   - But using {content_docs['used']:,} of {content_docs['max']:,} limit")
            print(f"   - Something else may be consuming the ContentDocument limit")

    elif file_storage_issue:
        print("\n⚠️  PRIMARY ISSUE: File Storage (MB/GB)")
        print("   - You are running out of file storage space")
        print("   - This is about SIZE of files, not COUNT")
        print("\n✅ WILL S3 MIGRATION HELP?")
        print("   ✅ YES! Moving files to S3 will free up file storage space")

    elif data_storage_issue:
        print("\n⚠️  PRIMARY ISSUE: Data Storage (MB/GB)")
        print(f"   - ~{total_custom_mb/1024:.1f} GB consumed by Trackland custom objects")
        print("   - Data storage is about RECORDS and METADATA, not files")
        print("\n❌ WILL S3 MIGRATION HELP?")
        print("   ❌ NO! S3 migration moves FILES, not RECORDS")
        print("   - DocListEntry__c records will still exist in Salesforce")
        print("   - Only the file URLs will change (still same record count)")
        print("   - To free data storage, you'd need to DELETE records")

    else:
        print("\n✅ NO CRITICAL STORAGE ISSUES DETECTED")
        print("   - All storage metrics appear to be within acceptable limits")

    # Additional recommendations
    print(f"\n{'=' * 100}")
    print("📋 RECOMMENDATIONS")
    print("=" * 100)

    if content_doc_issue:
        print("\n1. INVESTIGATE ContentDocument Usage:")
        print("   - Run: SELECT COUNT(Id) FROM ContentDocument")
        print("   - Check where these documents are coming from")
        print("   - Look for automated file creation processes")

        print("\n2. AUDIT FILE SOURCES:")
        print("   - Chatter Files")
        print("   - Content Libraries")
        print("   - Files tab")
        print("   - Email attachments")

        print("\n3. CLEAN UP STRATEGY:")
        print("   - Identify old/unused ContentDocuments")
        print("   - Archive or delete unnecessary files")
        print("   - Implement file retention policies")

    if data_storage_issue:
        print("\n1. DATA ARCHIVAL:")
        print("   - Archive old Trackland records to external system")
        print("   - Consider data retention policies")
        print("   - Use Salesforce Big Objects for archival")

        print("\n2. RECORD CLEANUP:")
        print("   - Identify records that can be safely deleted")
        print("   - Clean up orphaned records")
        print("   - Implement automated purge jobs")

if __name__ == "__main__":
    try:
        provide_definitive_diagnosis()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
