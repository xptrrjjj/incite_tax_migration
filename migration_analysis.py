#!/usr/bin/env python3
"""
Migration Analysis Script
========================

This script analyzes all DocListEntry__c records to show the full scope 
of what would be migrated across all accounts.
"""

import sys
import json
from collections import defaultdict, Counter
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError
from urllib.parse import urlparse

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

# File type size estimates in bytes (based on typical file sizes)
FILE_SIZE_ESTIMATES = {
    '.pdf': 500 * 1024,      # 500KB - typical PDF
    '.docx': 100 * 1024,     # 100KB - typical Word document
    '.doc': 80 * 1024,       # 80KB - older Word document
    '.xlsx': 50 * 1024,      # 50KB - typical Excel spreadsheet
    '.xls': 40 * 1024,       # 40KB - older Excel spreadsheet
    '.jpg': 200 * 1024,      # 200KB - typical JPEG image
    '.jpeg': 200 * 1024,     # 200KB - typical JPEG image
    '.png': 150 * 1024,      # 150KB - typical PNG image
    '.gif': 50 * 1024,       # 50KB - typical GIF image
    '.bmp': 500 * 1024,      # 500KB - typical BMP image
    '.tiff': 300 * 1024,     # 300KB - typical TIFF image
    '.tif': 300 * 1024,      # 300KB - typical TIFF image
    '.heic': 100 * 1024,     # 100KB - typical HEIC image
    '.heif': 100 * 1024,     # 100KB - typical HEIF image
    '.txt': 10 * 1024,       # 10KB - typical text file
    '.csv': 25 * 1024,       # 25KB - typical CSV file
    '.xml': 20 * 1024,       # 20KB - typical XML file
    '.html': 15 * 1024,      # 15KB - typical HTML file
    '.htm': 15 * 1024,       # 15KB - typical HTML file
    '.zip': 1024 * 1024,     # 1MB - typical ZIP archive
    '.rar': 1024 * 1024,     # 1MB - typical RAR archive
    '.7z': 800 * 1024,       # 800KB - typical 7z archive
    '.msg': 50 * 1024,       # 50KB - typical email message
    '.eml': 50 * 1024,       # 50KB - typical email message
    '.ppt': 2 * 1024 * 1024, # 2MB - typical PowerPoint
    '.pptx': 2 * 1024 * 1024, # 2MB - typical PowerPoint
    '.rtf': 30 * 1024,       # 30KB - typical RTF document
    '.pages': 100 * 1024,    # 100KB - typical Pages document
    '.numbers': 50 * 1024,   # 50KB - typical Numbers spreadsheet
    '.key': 1024 * 1024,     # 1MB - typical Keynote presentation
    '.mov': 10 * 1024 * 1024, # 10MB - typical video file
    '.mp4': 10 * 1024 * 1024, # 10MB - typical video file
    '.mp3': 3 * 1024 * 1024,  # 3MB - typical audio file
    '.wav': 5 * 1024 * 1024,  # 5MB - typical audio file
    '.qbo': 10 * 1024,       # 10KB - typical QuickBooks file
    '.qbb': 5 * 1024 * 1024, # 5MB - typical QuickBooks backup
    '.qbw': 10 * 1024 * 1024, # 10MB - typical QuickBooks data
    'no_extension': 50 * 1024, # 50KB - files without extension
    'default': 100 * 1024,   # 100KB - default for unknown types
}

def estimate_file_size(filename: str, page_count: int = None) -> int:
    """Estimate file size based on filename and optional page count."""
    if not filename:
        return FILE_SIZE_ESTIMATES['default']
    
    # Get file extension
    if '.' in filename:
        ext = '.' + filename.split('.')[-1].lower()
    else:
        ext = 'no_extension'
    
    # Get base size estimate
    base_size = FILE_SIZE_ESTIMATES.get(ext, FILE_SIZE_ESTIMATES['default'])
    
    # Adjust for page count if available (mainly for PDFs)
    if page_count and page_count > 0:
        if ext == '.pdf':
            # Estimate ~50KB per page for PDF
            estimated_size = max(base_size, page_count * 50 * 1024)
            return estimated_size
        elif ext in ['.docx', '.doc']:
            # Estimate ~10KB per page for Word documents
            estimated_size = max(base_size, page_count * 10 * 1024)
            return estimated_size
    
    return base_size

def format_bytes(bytes_size):
    """Format bytes to human readable format."""
    if bytes_size == 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0
    size = float(bytes_size)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    return f"{size:.2f} {units[unit_index]}"

def analyze_migration_scope():
    """Analyze the full scope of DocListEntry__c migration across all accounts."""
    
    try:
        # Authenticate with Salesforce
        print("Connecting to Salesforce...")
        sf = Salesforce(
            username=SALESFORCE_CONFIG["username"],
            password=SALESFORCE_CONFIG["password"],
            security_token=SALESFORCE_CONFIG["security_token"],
            domain=SALESFORCE_CONFIG["domain"]
        )
        print("✓ Successfully connected to Salesforce")
        
        # 1. Get all DocListEntry__c records with S3 URLs and valid accounts
        print("\n1. Analyzing all DocListEntry__c records with S3 URLs...")
        
        all_files_query = """
            SELECT Id, Name, Document__c, Type_Current__c, Type_Original__c, 
                   DocType__c, Parent_Folder__c, Visibility__c, Identifier__c,
                   Source__c, ClientName__c, ApplicableYear__c, TaxonomyStage__c,
                   Account__c, Account__r.Name, CreatedDate, LastModifiedDate,
                   PageCount__c, TxPageCount__c, ContentVersionId__c
            FROM DocListEntry__c
            WHERE IsDeleted = FALSE
            AND Document__c != NULL
            AND Type_Current__c = 'Document'
            AND Account__c != NULL
            ORDER BY Account__r.Name, Name
        """
        
        print("   Querying all DocListEntry__c records... (this may take a moment)")
        all_files_result = sf.query_all(all_files_query)
        all_files = all_files_result['records']
        
        print(f"✓ Found {len(all_files)} total DocListEntry__c documents with accounts")
        
        # 2. Get all folders for context
        print("\n2. Analyzing folder structure...")
        
        folders_query = """
            SELECT Id, Name, Parent_Folder__c, Identifier__c, ApplicableYear__c,
                   Account__c, Account__r.Name
            FROM DocListEntry__c
            WHERE IsDeleted = FALSE
            AND Type_Current__c = 'Folder'
            AND Account__c != NULL
            ORDER BY Account__r.Name, Name
        """
        
        folders_result = sf.query_all(folders_query)
        all_folders = folders_result['records']
        
        print(f"✓ Found {len(all_folders)} total folders with accounts")
        
        # 3. Analyze by account
        print("\n3. Analyzing by account...")
        
        accounts_data = defaultdict(lambda: {
            'name': '',
            'files': [],
            'folders': [],
            'total_files': 0,
            'trackland_files': 0,
            'other_s3_files': 0,
            'file_types': Counter(),
            'years': set(),
            'external_domains': set(),
            'trackland_size_bytes': 0,
            'trackland_urls': [],
            'total_pages': 0,
            'files_with_pages': 0
        })
        
        # Process files
        print("   Processing files and estimating sizes...")
        
        for i, file_record in enumerate(all_files):
            if i % 10000 == 0:
                print(f"   Progress: {i:,}/{len(all_files):,}")
            
            account_id = file_record['Account__c']
            # Add null check for Account__r
            account_name = file_record['Account__r']['Name'] if file_record['Account__r'] else f"Account_{account_id}"
            
            accounts_data[account_id]['name'] = account_name
            accounts_data[account_id]['files'].append(file_record)
            accounts_data[account_id]['total_files'] += 1
            
            # Get page count information
            page_count = file_record.get('PageCount__c') or file_record.get('TxPageCount__c')
            if page_count and page_count > 0:
                accounts_data[account_id]['total_pages'] += page_count
                accounts_data[account_id]['files_with_pages'] += 1
            
            # Analyze S3 URL
            document_url = file_record.get('Document__c', '')
            if document_url:
                parsed_url = urlparse(document_url)
                domain = parsed_url.netloc
                accounts_data[account_id]['external_domains'].add(domain)
                
                filename = file_record.get('Name', '')
                
                if 'trackland-doc-storage' in document_url:
                    accounts_data[account_id]['trackland_files'] += 1
                    accounts_data[account_id]['trackland_urls'].append(document_url)
                    
                    # Estimate file size
                    estimated_size = estimate_file_size(filename, page_count)
                    accounts_data[account_id]['trackland_size_bytes'] += estimated_size
                    
                elif 's3' in document_url or 'amazonaws.com' in document_url:
                    accounts_data[account_id]['other_s3_files'] += 1
            
            # Analyze file type
            filename = file_record.get('Name', '')
            if '.' in filename:
                file_ext = '.' + filename.split('.')[-1].lower()
                accounts_data[account_id]['file_types'][file_ext] += 1
            else:
                accounts_data[account_id]['file_types']['no_extension'] += 1
            
            # Analyze year
            year = file_record.get('ApplicableYear__c')
            if year:
                accounts_data[account_id]['years'].add(str(year))
        
        # Process folders
        for folder_record in all_folders:
            account_id = folder_record['Account__c']
            accounts_data[account_id]['folders'].append(folder_record)
        
        # 4. Calculate totals
        print("\n4. Calculating totals and generating report...")
        
        total_accounts = len(accounts_data)
        total_files = sum(data['total_files'] for data in accounts_data.values())
        total_trackland_files = sum(data['trackland_files'] for data in accounts_data.values())
        total_other_s3_files = sum(data['other_s3_files'] for data in accounts_data.values())
        total_folders = len(all_folders)
        estimated_total_size = sum(data['trackland_size_bytes'] for data in accounts_data.values())
        total_pages = sum(data['total_pages'] for data in accounts_data.values())
        files_with_pages = sum(data['files_with_pages'] for data in accounts_data.values())
        
        # 5. Generate comprehensive report
        print("\n" + "=" * 80)
        print("COMPREHENSIVE MIGRATION ANALYSIS REPORT")
        print("=" * 80)
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   • Total accounts with files: {total_accounts:,}")
        print(f"   • Total files across all accounts: {total_files:,}")
        print(f"   • Files from trackland-doc-storage (migration targets): {total_trackland_files:,}")
        print(f"   • Files from other S3 sources: {total_other_s3_files:,}")
        print(f"   • Total folders: {total_folders:,}")
        print(f"   • Files with page count information: {files_with_pages:,}")
        print(f"   • Total pages across all documents: {total_pages:,}")
        
        # Files that will be migrated
        migration_percentage = (total_trackland_files / total_files * 100) if total_files > 0 else 0
        print(f"\n🎯 MIGRATION SCOPE:")
        print(f"   • Files to be migrated: {total_trackland_files:,} ({migration_percentage:.1f}% of all files)")
        print(f"   • Files that will remain unchanged: {total_files - total_trackland_files:,}")
        
        # Size and time estimates
        print(f"\n📦 SIZE ESTIMATES (based on file types):")
        print(f"   • Estimated total data to migrate: {format_bytes(estimated_total_size)}")
        if total_trackland_files > 0:
            avg_file_size = estimated_total_size / total_trackland_files
            print(f"   • Average file size: {format_bytes(avg_file_size)}")
        
        # Time estimates (rough calculations)
        if estimated_total_size > 0:
            # Assume 2 MB/sec transfer rate (accounting for download + upload + processing)
            transfer_rate_mbps = 2.0  # MB per second
            estimated_seconds = (estimated_total_size / (1024 * 1024)) / transfer_rate_mbps
            estimated_minutes = estimated_seconds / 60
            estimated_hours = estimated_minutes / 60
            
            # Add database update time (assume 1 update per second)
            db_update_seconds = total_trackland_files / 1.0
            db_update_hours = db_update_seconds / 3600
            
            total_estimated_hours = estimated_hours + db_update_hours
            
            print(f"\n⏱️  TIME ESTIMATES (rough):")
            print(f"   • File transfer time: ~{estimated_hours:.1f} hours")
            print(f"   • Database updates: ~{db_update_hours:.1f} hours")
            print(f"   • Total estimated time: ~{total_estimated_hours:.1f} hours")
            print(f"   • Note: Actual time depends on network speed and system load")
            
            # Cost estimates (rough AWS S3 pricing)
            gb_size = estimated_total_size / (1024**3)
            estimated_storage_cost = gb_size * 0.023  # ~$0.023 per GB for S3 standard
            estimated_transfer_cost = gb_size * 0.09   # ~$0.09 per GB for data transfer
            
            print(f"\n💰 COST ESTIMATES:")
            print(f"   • Estimated S3 storage cost: ~${estimated_storage_cost:.2f}/month")
            print(f"   • Estimated data transfer cost: ~${estimated_transfer_cost:.2f} (one-time)")
            print(f"   • Total estimated cost: ~${estimated_storage_cost + estimated_transfer_cost:.2f}")
        
        # External domains analysis
        all_domains = set()
        for data in accounts_data.values():
            all_domains.update(data['external_domains'])
        
        print(f"\n🌐 EXTERNAL S3 DOMAINS FOUND:")
        for domain in sorted(all_domains):
            if domain:  # Skip empty domains
                domain_count = sum(1 for data in accounts_data.values() if domain in data['external_domains'])
                print(f"   • {domain}: Used by {domain_count:,} account(s)")
        
        # File types analysis
        all_file_types = Counter()
        for data in accounts_data.values():
            all_file_types.update(data['file_types'])
        
        print(f"\n📁 FILE TYPES BREAKDOWN:")
        for file_type, count in all_file_types.most_common(15):
            percentage = (count / total_files * 100) if total_files > 0 else 0
            est_size = FILE_SIZE_ESTIMATES.get(file_type, FILE_SIZE_ESTIMATES['default'])
            total_type_size = count * est_size
            print(f"   • {file_type}: {count:,} files ({percentage:.1f}%) - Est: {format_bytes(total_type_size)}")
        
        # Top accounts by file count
        top_accounts = sorted(accounts_data.items(), key=lambda x: x[1]['trackland_files'], reverse=True)
        
        print(f"\n🏆 TOP 10 ACCOUNTS BY TRACKLAND FILES:")
        for i, (account_id, data) in enumerate(top_accounts[:10], 1):
            trackland_files = data['trackland_files']
            total_files = data['total_files']
            account_name = data['name']
            size_info = format_bytes(data['trackland_size_bytes'])
            avg_pages = data['total_pages'] / data['files_with_pages'] if data['files_with_pages'] > 0 else 0
            
            print(f"   {i:2d}. {account_name}")
            print(f"       Account ID: {account_id}")
            print(f"       Trackland files: {trackland_files:,} ({size_info})")
            print(f"       Total files: {total_files:,}")
            print(f"       Folders: {len(data['folders'])}")
            print(f"       Files with pages: {data['files_with_pages']:,}")
            if avg_pages > 0:
                print(f"       Average pages per file: {avg_pages:.1f}")
            if data['years']:
                years = sorted(data['years'])
                print(f"       Years: {', '.join(years)}")
            print()
        
        # Migration recommendations
        print(f"\n💡 MIGRATION RECOMMENDATIONS:")
        
        if total_trackland_files > 0:
            print(f"   ✅ Migration is recommended:")
            print(f"      • {total_trackland_files:,} files will be moved from trackland-doc-storage")
            print(f"      • {total_accounts:,} accounts will be updated")
            print(f"      • Estimated data transfer: {format_bytes(estimated_total_size)}")
            print(f"      • Estimated time: ~{total_estimated_hours:.1f} hours")
            print(f"      • Folder structure will be preserved")
            
            if total_trackland_files > 10000:
                print(f"   ⚠️  Large migration detected:")
                print(f"      • Consider running in smaller batches (e.g., 1000 files at a time)")
                print(f"      • Monitor S3 transfer costs during migration")
                print(f"      • Test with a few accounts first")
                print(f"      • Consider running during off-peak hours")
                print(f"      • Set up monitoring for migration progress")
        else:
            print(f"   ℹ️  No trackland files found - migration not needed")
        
        print(f"\n🎯 NEXT STEPS:")
        print(f"   1. Review the account breakdown above")
        print(f"   2. Test with a single account first (test_single_account=True)")
        print(f"   3. Run with dry_run=True to see exactly what will happen")
        print(f"   4. When ready, run full migration with dry_run=False")
        print(f"   5. Monitor progress and adjust batch sizes as needed")
        
        print("=" * 80)
        
        # Export summary to JSON for reference
        summary_data = {
            'total_accounts': total_accounts,
            'total_files': total_files,
            'trackland_files': total_trackland_files,
            'other_s3_files': total_other_s3_files,
            'total_folders': total_folders,
            'migration_percentage': migration_percentage,
            'estimated_total_size_bytes': estimated_total_size,
            'estimated_total_size_formatted': format_bytes(estimated_total_size),
            'average_file_size_bytes': estimated_total_size / total_trackland_files if total_trackland_files > 0 else 0,
            'estimated_hours': total_estimated_hours if estimated_total_size > 0 else 0,
            'total_pages': total_pages,
            'files_with_pages': files_with_pages,
            'external_domains': list(all_domains),
            'file_types': dict(all_file_types),
            'top_accounts': [
                {
                    'account_id': aid,
                    'account_name': data['name'],
                    'trackland_files': data['trackland_files'],
                    'total_files': data['total_files'],
                    'folders': len(data['folders']),
                    'estimated_size_bytes': data['trackland_size_bytes'],
                    'estimated_size_formatted': format_bytes(data['trackland_size_bytes']),
                    'total_pages': data['total_pages'],
                    'files_with_pages': data['files_with_pages']
                }
                for aid, data in top_accounts[:20]  # Top 20
            ],
            'size_estimation_method': 'file_type_based',
            'size_estimates_used': FILE_SIZE_ESTIMATES
        }
        
        with open('migration_analysis_summary.json', 'w') as f:
            json.dump(summary_data, f, indent=2)
        
        print(f"\n💾 Summary exported to: migration_analysis_summary.json")
        
        # Clean up the temporary field discovery script
        import os
        if os.path.exists('check_doclist_fields.py'):
            os.remove('check_doclist_fields.py')
            print("✓ Cleaned up temporary files")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    analyze_migration_scope() 