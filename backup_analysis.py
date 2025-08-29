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
        """Get comprehensive analysis of files to backup."""
        try:
            # Get all accounts with DocListEntry__c records
            self.logger.info("Getting all accounts with DocListEntry__c records...")
            accounts_query = """
                SELECT Account__c
                FROM DocListEntry__c
                WHERE Account__c != NULL
                AND IsDeleted = FALSE
                AND Document__c != NULL
                GROUP BY Account__c
                LIMIT 300
            """
            
            accounts_result = self.sf.query(accounts_query)
            target_account_ids = [acc['Account__c'] for acc in accounts_result['records']]
            
            self.logger.info(f"Found {len(target_account_ids)} accounts with DocListEntry__c files")
            
            if not target_account_ids:
                return {"error": "No accounts found"}
            
            # Get detailed file information for all accounts
            all_files = []
            batch_size = 20
            
            self.logger.info("Analyzing files across all accounts...")
            
            for i in range(0, len(target_account_ids), batch_size):
                batch_ids = target_account_ids[i:i + batch_size]
                ids_str = "', '".join(batch_ids)
                
                files_query = f"""
                    SELECT Id, Name, Document__c, Type_Current__c,
                           Account__c, Account__r.Name, CreatedDate, LastModifiedDate
                    FROM DocListEntry__c
                    WHERE Account__c IN ('{ids_str}')
                    AND IsDeleted = FALSE
                    AND Document__c != NULL
                    AND Type_Current__c = 'Document'
                    ORDER BY Account__c, Name
                """
                
                try:
                    self.logger.info(f"Analyzing batch {i//batch_size + 1}/{(len(target_account_ids) + batch_size - 1)//batch_size}")
                    result = self.sf.query_all(files_query)
                    
                    for record in result['records']:
                        file_info = {
                            'doclistentry_id': record['Id'],
                            'name': record['Name'],
                            'document_url': record['Document__c'],
                            'account_id': record['Account__c'],
                            'account_name': record['Account__r']['Name'],
                            'created_date': record['CreatedDate'],
                            'last_modified_date': record['LastModifiedDate']
                        }
                        all_files.append(file_info)
                        
                except SalesforceError as e:
                    self.logger.error(f"Error querying files for batch: {e}")
                    continue
            
            return self.analyze_files(all_files)
            
        except Exception as e:
            self.logger.error(f"Error during analysis: {e}")
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
        
        # Allowed extensions from config
        allowed_extensions = MIGRATION_CONFIG.get('allowed_extensions', [])
        
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
                
                # Check if processable
                if not allowed_extensions or (file_ext and file_ext in allowed_extensions):
                    processable_files += 1
                    account_stats[account_id]['processable_files'] += 1
                else:
                    skipped_files += 1
                    account_stats[account_id]['skipped_files'] += 1
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