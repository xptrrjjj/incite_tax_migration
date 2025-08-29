#!/usr/bin/env python3
"""
Backup Analysis Script
=====================

Quick analysis script to show the scope of files that need to be backed up
without actually downloading anything. Shows statistics by account and file types.

Usage:
python backup_analysis.py
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


def setup_logging() -> logging.Logger:
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logger = logging.getLogger(__name__)
    return logger


class BackupAnalyzer:
    """Analyzes files available for backup without downloading."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.sf = None
        
    def authenticate(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            self.sf = Salesforce(
                username=SALESFORCE_CONFIG["username"],
                password=SALESFORCE_CONFIG["password"],
                security_token=SALESFORCE_CONFIG["security_token"],
                domain=SALESFORCE_CONFIG["domain"]
            )
            
            self.logger.info("✓ Successfully authenticated with Salesforce")
            return True
            
        except SalesforceError as e:
            self.logger.error(f"❌ Salesforce authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during Salesforce authentication: {e}")
            return False
    
    def get_backup_analysis(self) -> Dict:
        """Get comprehensive analysis using smart pagination - complete but faster."""
        try:
            # Strategy: Get quick counts first, then paginate efficiently
            
            # Step 1: Quick count of total records to understand scope
            self.logger.info("Getting total record count...")
            count_query = """
                SELECT COUNT()
                FROM DocListEntry__c
                WHERE IsDeleted = FALSE
                AND Document__c != NULL
                AND Type_Current__c = 'Document'
                AND Account__c != NULL
            """
            
            count_result = self.sf.query(count_query)
            total_records = count_result['totalSize']
            self.logger.info(f"Total records to process: {total_records:,}")
            
            # Step 2: Get all unique account IDs efficiently 
            self.logger.info("Getting all unique account IDs...")
            account_query = """
                SELECT Account__c, Account__r.Name
                FROM DocListEntry__c
                WHERE IsDeleted = FALSE
                AND Document__c != NULL
                AND Type_Current__c = 'Document'
                AND Account__c != NULL
                GROUP BY Account__c, Account__r.Name
                ORDER BY Account__r.Name
                LIMIT 2000
            """
            
            account_result = self.sf.query(account_query)
            accounts = {}
            for r in account_result['records']:
                account_id = r['Account__c']
                # Handle missing Account__r relationship safely
                if r.get('Account__r') and r['Account__r'].get('Name'):
                    account_name = r['Account__r']['Name']
                else:
                    account_name = f"Account_{account_id}"
                accounts[account_id] = account_name
            
            self.logger.info(f"Found {len(accounts)} unique accounts")
            
            # Step 3: Use cursor-based pagination (no OFFSET limits)
            all_files = []
            batch_size = 2000
            last_id = None
            batch_num = 0
            total_batches = (total_records + batch_size - 1) // batch_size
            
            self.logger.info("Processing files with cursor-based pagination...")
            
            while True:
                # Cursor-based pagination using WHERE Id > last_id
                if last_id:
                    files_query = f"""
                        SELECT Id, Name, Document__c, Account__c, CreatedDate
                        FROM DocListEntry__c
                        WHERE IsDeleted = FALSE
                        AND Document__c != NULL
                        AND Type_Current__c = 'Document'
                        AND Account__c != NULL
                        AND Id > '{last_id}'
                        ORDER BY Id
                        LIMIT {batch_size}
                    """
                else:
                    # First batch
                    files_query = f"""
                        SELECT Id, Name, Document__c, Account__c, CreatedDate
                        FROM DocListEntry__c
                        WHERE IsDeleted = FALSE
                        AND Document__c != NULL
                        AND Type_Current__c = 'Document'
                        AND Account__c != NULL
                        ORDER BY Id
                        LIMIT {batch_size}
                    """
                
                try:
                    batch_result = self.sf.query(files_query)
                    batch_records = batch_result['records']
                    
                    if not batch_records:
                        break  # No more records
                    
                    batch_num += 1
                    self.logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch_records)} records)")
                    
                    # Convert records efficiently
                    for record in batch_records:
                        file_info = {
                            'doclistentry_id': record['Id'],
                            'name': record['Name'],
                            'document_url': record['Document__c'],
                            'account_id': record['Account__c'],
                            'account_name': accounts.get(record['Account__c'], f"Account_{record['Account__c']}"),
                            'created_date': record['CreatedDate'],
                            'last_modified_date': None  # Skip for speed
                        }
                        all_files.append(file_info)
                    
                    # Update cursor to last ID in this batch
                    last_id = batch_records[-1]['Id']
                    
                    # Progress update every 10 batches
                    if batch_num % 10 == 0:
                        processed = len(all_files)
                        progress = (processed / total_records) * 100
                        self.logger.info(f"Progress: {processed:,}/{total_records:,} ({progress:.1f}%)")
                    
                except SalesforceError as e:
                    self.logger.error(f"Error in batch {batch_num}: {e}")
                    # For cursor-based pagination, we can't easily skip, so break
                    self.logger.error("Stopping due to cursor pagination error")
                    break
            
            self.logger.info(f"Successfully processed {len(all_files):,} files from {len(accounts)} accounts")
            
            return self.analyze_files(all_files)
            
        except Exception as e:
            self.logger.error(f"Error during analysis: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return {"error": str(e)}
    
    def analyze_files(self, files: List[Dict]) -> Dict:
        """Analyze the collected files and generate statistics."""
        if not files:
            return {"error": "No files found"}
        
        # Account statistics
        account_stats = defaultdict(lambda: {
            'name': '',
            'file_count': 0,
            'file_types': defaultdict(int),
            'trackland_files': 0,
            'other_files': 0,
            'processable_files': 0,
            'skipped_files': 0
        })
        
        # Overall statistics
        total_files = len(files)
        file_extensions = defaultdict(int)
        trackland_files = 0
        processable_files = 0
        skipped_files = 0
        
        # For backup analysis, we don't skip any files - backup EVERYTHING
        allowed_extensions = []  # Empty list means allow all extensions
        
        for file_info in files:
            account_id = file_info['account_id']
            account_name = file_info['account_name']
            filename = file_info['name']
            document_url = file_info['document_url']
            
            # Update account stats
            account_stats[account_id]['name'] = account_name
            account_stats[account_id]['file_count'] += 1
            
            # Get file extension
            file_ext = None
            if '.' in filename:
                file_ext = '.' + filename.split('.')[-1].lower()
                file_extensions[file_ext] += 1
                account_stats[account_id]['file_types'][file_ext] += 1
            
            # Check if it's a trackland file
            if document_url and 'trackland-doc-storage' in document_url:
                trackland_files += 1
                account_stats[account_id]['trackland_files'] += 1
                
                # For backup, we process ALL trackland files regardless of extension
                processable_files += 1
                account_stats[account_id]['processable_files'] += 1
            else:
                account_stats[account_id]['other_files'] += 1
        
        # Convert defaultdict to regular dict for JSON serialization
        account_stats_regular = {}
        for account_id, stats in account_stats.items():
            account_stats_regular[account_id] = {
                'name': stats['name'],
                'file_count': stats['file_count'],
                'trackland_files': stats['trackland_files'],
                'other_files': stats['other_files'],
                'processable_files': stats['processable_files'],
                'skipped_files': stats['skipped_files'],
                'file_types': dict(stats['file_types'])
            }
        
        return {
            'summary': {
                'total_accounts': len(account_stats),
                'total_files': total_files,
                'trackland_files': trackland_files,
                'processable_files': processable_files,
                'skipped_files': skipped_files,
                'other_files': total_files - trackland_files
            },
            'file_extensions': dict(file_extensions),
            'accounts': account_stats_regular,
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def print_analysis(self, analysis: Dict):
        """Print formatted analysis results."""
        if 'error' in analysis:
            self.logger.error(f"Analysis failed: {analysis['error']}")
            return
        
        summary = analysis['summary']
        
        print("\n" + "=" * 80)
        print("BACKUP ANALYSIS SUMMARY")
        print("=" * 80)
        print(f"Total Accounts: {summary['total_accounts']:,}")
        print(f"Total Files: {summary['total_files']:,}")
        print(f"Trackland Files (can be backed up): {summary['trackland_files']:,}")
        print(f"Processable Files: {summary['processable_files']:,}")
        print(f"Files to Skip: {summary['skipped_files']:,}")
        print(f"Other Files (non-trackland): {summary['other_files']:,}")
        
        # File types breakdown
        print(f"\n" + "-" * 50)
        print("FILE TYPES BREAKDOWN")
        print("-" * 50)
        file_exts = analysis['file_extensions']
        sorted_exts = sorted(file_exts.items(), key=lambda x: x[1], reverse=True)
        
        for ext, count in sorted_exts[:15]:  # Top 15 file types
            print(f"{ext:>10}: {count:,} files")
        
        if len(sorted_exts) > 15:
            remaining = sum(count for _, count in sorted_exts[15:])
            print(f"{'Others':>10}: {remaining:,} files")
        
        # Top accounts by file count
        print(f"\n" + "-" * 50)
        print("TOP 20 ACCOUNTS BY FILE COUNT")
        print("-" * 50)
        accounts_by_files = sorted(
            analysis['accounts'].items(),
            key=lambda x: x[1]['trackland_files'],
            reverse=True
        )
        
        for account_id, stats in accounts_by_files[:20]:
            name = stats['name'][:30] + "..." if len(stats['name']) > 30 else stats['name']
            print(f"{name:<35} ({account_id}): {stats['trackland_files']:,} trackland files")
        
        print(f"\n" + "=" * 80)
        print("BACKUP SCOPE ESTIMATE")
        print("=" * 80)
        print(f"🏢 Accounts to process: {summary['total_accounts']:,}")
        print(f"📄 Files to backup: {summary['processable_files']:,}")
        print(f"⚠️  Files to skip: {summary['skipped_files']:,}")
        print("=" * 80)


def main():
    """Main execution function."""
    print("Backup Analysis Script")
    print("=" * 50)
    print("Analyzing DocListEntry__c files for backup scope...")
    
    logger = setup_logging()
    
    try:
        analyzer = BackupAnalyzer(logger)
        
        if not analyzer.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = analyzer.get_backup_analysis()
        analyzer.print_analysis(analysis)
        
        return True
        
    except KeyboardInterrupt:
        logger.info("⚠️ Analysis interrupted by user")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)