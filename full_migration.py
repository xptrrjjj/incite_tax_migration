#!/usr/bin/env python3
"""
Phase 2: Full Migration Script  
==============================

This script performs the final migration by updating Salesforce DocListEntry__c
records to use your S3 URLs instead of external S3. Uses existing backup data
from Phase 1 and only copies new files added since last backup.

Features:
- Updates Salesforce URLs to point to your S3
- Uses existing backed-up files (no re-copying)
- Only copies new files added since last backup
- Comprehensive validation and rollback capability
- Detailed logging and progress tracking

⚠️ WARNING: This modifies Salesforce production data!
            Always test thoroughly before running in production.

Usage:
1. python full_migration.py --dry-run      # Test mode (no Salesforce changes)
2. python full_migration.py --execute      # Execute the migration
"""

import os
import sys
import argparse
import logging
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import requests
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError
from urllib.parse import urlparse
import json

# Import our database manager
from migration_db import MigrationDB, calculate_file_hash

# Import configuration
try:
    from config import SALESFORCE_CONFIG, AWS_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


class FullMigration:
    """Phase 2 migration - update Salesforce to use your S3 URLs."""
    
    def __init__(self, dry_run: bool = True):
        """Initialize the full migration."""
        self.dry_run = dry_run
        self.logger = self._setup_logging()
        self.db = MigrationDB()
        
        # Initialize counters
        self.stats = {
            'total_files': 0,
            'existing_files': 0,  # Files already backed up in Phase 1
            'new_files': 0,       # Files that need to be copied
            'updated_urls': 0,    # Salesforce URLs updated
            'failed_updates': 0,  # Failed Salesforce updates
            'skipped': 0,
            'total_size': 0
        }
        
        self.sf = None
        self.s3_client = None
        self.run_id = None
        self.rollback_data = []  # For storing original URLs for rollback
        
    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "dryrun" if self.dry_run else "execute"
        log_file = log_dir / f"full_migration_{mode}_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Full migration logging initialized. Log file: {log_file}")
        return logger
    
    def authenticate_salesforce(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            self.logger.info("Authenticating with Salesforce...")
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
    
    def authenticate_aws(self) -> bool:
        """Authenticate with AWS S3."""
        try:
            self.logger.info("Authenticating with AWS S3...")
            
            # Create S3 client with explicit credentials if provided
            if AWS_CONFIG.get("access_key_id") and AWS_CONFIG.get("secret_access_key"):
                self.s3_client = boto3.client(
                    's3',
                    region_name=AWS_CONFIG["region"],
                    aws_access_key_id=AWS_CONFIG["access_key_id"],
                    aws_secret_access_key=AWS_CONFIG["secret_access_key"]
                )
            else:
                # Use default credential chain
                self.s3_client = boto3.client('s3', region_name=AWS_CONFIG["region"])
            
            # Test authentication
            self.s3_client.list_buckets()
            
            self.logger.info("✓ Successfully authenticated with AWS S3")
            return True
            
        except NoCredentialsError:
            self.logger.error("❌ AWS credentials not found. Please run 'aws configure' or set environment variables.")
            return False
        except ClientError as e:
            self.logger.error(f"❌ AWS S3 authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during AWS authentication: {e}")
            return False
    
    def validate_backup_data(self) -> bool:
        """Validate that we have backup data from Phase 1."""
        try:
            self.logger.info("Validating backup data from Phase 1...")
            
            stats = self.db.get_migration_stats()
            total_files = stats['files'].get('total_files', 0)
            
            if total_files == 0:
                self.logger.error("❌ No backup data found. Please run Phase 1 backup first.")
                return False
            
            backup_only = stats['files'].get('backup_only', 0)
            fully_migrated = stats['files'].get('fully_migrated', 0)
            
            self.logger.info(f"✓ Found {total_files} backed up files")
            self.logger.info(f"  - Backup only: {backup_only}")
            self.logger.info(f"  - Fully migrated: {fully_migrated}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error validating backup data: {e}")
            return False
    
    def get_current_salesforce_files(self) -> Dict[str, Dict]:
        """Get current DocListEntry__c records from Salesforce."""
        try:
            self.logger.info("Querying current DocListEntry__c records from Salesforce...")
            
            query = """
                SELECT Id, Name, Document__c, Account__c, Account__r.Name, 
                       LastModifiedDate, CreatedDate, SystemModstamp
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
            """
            
            query_result = self.sf.query_all(query)
            records = query_result['records']
            
            # Convert to dictionary for easier lookup
            records_dict = {record['Id']: record for record in records}
            
            self.logger.info(f"Found {len(records)} current DocListEntry__c records")
            return records_dict
            
        except SalesforceError as e:
            self.logger.error(f"❌ Failed to query Salesforce: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error querying Salesforce: {e}")
            raise
    
    def identify_new_files(self, current_sf_records: Dict[str, Dict]) -> List[Dict]:
        """Identify files that need to be copied (not in Phase 1 backup)."""
        try:
            self.logger.info("Identifying new files since last backup...")
            
            # Get all backed up file IDs
            backed_up_files = self.db.get_backed_up_files()
            backed_up_ids = {file['doclist_entry_id'] for file in backed_up_files}
            
            # Find files in Salesforce that aren't backed up
            new_files = []
            for record_id, record in current_sf_records.items():
                if record_id not in backed_up_ids:
                    new_files.append(record)
            
            self.logger.info(f"Found {len(new_files)} new files to copy")
            return new_files
            
        except Exception as e:
            self.logger.error(f"❌ Error identifying new files: {e}")
            raise
    
    def copy_new_files(self, new_files: List[Dict]) -> bool:
        """Copy new files to your S3 (same logic as Phase 1)."""
        if not new_files:
            self.logger.info("No new files to copy")
            return True
        
        try:
            self.logger.info(f"Copying {len(new_files)} new files to S3...")
            
            for i, record in enumerate(new_files, 1):
                try:
                    doclist_id = record['Id']
                    original_url = record['Document__c']
                    account_id = record['Account__c']
                    account_name = record['Account__r']['Name'] if record['Account__r'] else 'Unknown'
                    
                    # Clean account name for file path
                    clean_account_name = self._clean_filename(account_name)
                    
                    # Extract file name from URL
                    parsed_url = urlparse(original_url)
                    file_name = os.path.basename(parsed_url.path) or f"file_{doclist_id}"
                    
                    # Generate S3 key
                    s3_key = f"uploads/{account_id}/{clean_account_name}/{file_name}"
                    
                    self.logger.info(f"Copying new file ({i}/{len(new_files)}): {file_name}")
                    
                    if not self.dry_run:
                        # Download from external S3
                        content, file_size = self._download_file(original_url)
                        
                        # Upload to your S3
                        your_s3_url = self._upload_to_s3(content, s3_key, file_name)
                        
                        # Calculate file hash
                        file_hash = calculate_file_hash(content)
                        
                        # Record in database
                        file_data = {
                            'doclist_entry_id': doclist_id,
                            'account_id': account_id,
                            'account_name': account_name,
                            'original_url': original_url,
                            'your_s3_key': s3_key,
                            'your_s3_url': your_s3_url,
                            'file_name': file_name,
                            'file_size_bytes': file_size,
                            'file_hash': file_hash,
                            'backup_timestamp': datetime.now().isoformat(),
                            'last_modified_sf': record.get('LastModifiedDate')
                        }
                        
                        self.db.record_file_migration(file_data)
                        self.stats['total_size'] += file_size
                    else:
                        self.logger.info(f"  [DRY RUN] Would copy: {file_name} to {s3_key}")
                    
                    self.stats['new_files'] += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to copy new file {record['Id']}: {e}")
                    continue
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error copying new files: {e}")
            return False
    
    def update_salesforce_urls(self) -> bool:
        """Update DocListEntry__c.Document__c URLs to point to your S3."""
        try:
            self.logger.info("Updating Salesforce URLs to point to your S3...")
            
            # Get all files that need Salesforce URL updates
            files_to_update = self.db.get_files_needing_salesforce_update()
            
            if not files_to_update:
                self.logger.info("No files need Salesforce URL updates")
                return True
            
            self.logger.info(f"Updating {len(files_to_update)} Salesforce records")
            
            # Process in batches for better performance
            batch_size = 200  # Salesforce API limit
            total_batches = (len(files_to_update) + batch_size - 1) // batch_size
            
            updated_ids = []
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(files_to_update))
                batch = files_to_update[start_idx:end_idx]
                
                self.logger.info(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} records)")
                
                if not self.dry_run:
                    # Prepare batch update data
                    updates = []
                    for file_record in batch:
                        # Store original URL for rollback
                        self.rollback_data.append({
                            'Id': file_record['doclist_entry_id'],
                            'original_url': file_record['original_url']
                        })
                        
                        updates.append({
                            'Id': file_record['doclist_entry_id'],
                            'Document__c': file_record['your_s3_url']
                        })
                    
                    # Execute batch update
                    try:
                        results = self.sf.bulk.DocListEntry__c.update(updates)
                        
                        # Check results
                        for i, result in enumerate(results):
                            if result['success']:
                                updated_ids.append(batch[i]['doclist_entry_id'])
                                self.stats['updated_urls'] += 1
                            else:
                                self.logger.error(f"Failed to update {batch[i]['doclist_entry_id']}: {result['errors']}")
                                self.stats['failed_updates'] += 1
                                
                                # Record error
                                self.db.record_migration_error(
                                    self.run_id, batch[i]['doclist_entry_id'],
                                    'salesforce_update_error', str(result['errors'])
                                )
                        
                    except Exception as e:
                        self.logger.error(f"Batch update failed: {e}")
                        self.stats['failed_updates'] += len(batch)
                        continue
                else:
                    # Dry run - just log what would be updated
                    for file_record in batch:
                        self.logger.info(f"  [DRY RUN] Would update {file_record['doclist_entry_id']}")
                        self.logger.info(f"    From: {file_record['original_url']}")
                        self.logger.info(f"    To:   {file_record['your_s3_url']}")
                        self.stats['updated_urls'] += 1
                
                # Progress update
                progress = (batch_num + 1) / total_batches * 100
                self.logger.info(f"Update progress: {progress:.1f}%")
            
            # Mark files as updated in database
            if updated_ids and not self.dry_run:
                self.db.mark_salesforce_updated(updated_ids)
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error updating Salesforce URLs: {e}")
            return False
    
    def validate_migration(self) -> bool:
        """Validate the migration by checking some random files."""
        if self.dry_run:
            self.logger.info("[DRY RUN] Skipping migration validation")
            return True
        
        try:
            self.logger.info("Validating migration by spot-checking files...")
            
            # Get a sample of migrated files
            sample_files = self.db.conn.execute('''
                SELECT * FROM file_migrations 
                WHERE salesforce_updated = 1 
                ORDER BY RANDOM() 
                LIMIT 10
            ''').fetchall()
            
            validation_passed = 0
            validation_failed = 0
            
            for file_record in sample_files:
                try:
                    # Check if file exists in your S3
                    self.s3_client.head_object(
                        Bucket=AWS_CONFIG["bucket_name"], 
                        Key=file_record['your_s3_key']
                    )
                    
                    # Check if Salesforce record has the correct URL
                    sf_record = self.sf.DocListEntry__c.get(file_record['doclist_entry_id'])
                    if sf_record['Document__c'] == file_record['your_s3_url']:
                        validation_passed += 1
                        self.logger.debug(f"✓ Validation passed for {file_record['doclist_entry_id']}")
                    else:
                        validation_failed += 1
                        self.logger.warning(f"❌ URL mismatch for {file_record['doclist_entry_id']}")
                
                except Exception as e:
                    validation_failed += 1
                    self.logger.warning(f"❌ Validation failed for {file_record['doclist_entry_id']}: {e}")
            
            success_rate = validation_passed / (validation_passed + validation_failed) * 100
            self.logger.info(f"Validation complete: {validation_passed}/{validation_passed + validation_failed} passed ({success_rate:.1f}%)")
            
            return success_rate >= 90  # Require 90% validation success
            
        except Exception as e:
            self.logger.error(f"❌ Error during migration validation: {e}")
            return False
    
    def save_rollback_data(self):
        """Save rollback data to file for emergency recovery."""
        if not self.rollback_data or self.dry_run:
            return
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rollback_file = f"rollback_data_{timestamp}.json"
            
            with open(rollback_file, 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'total_records': len(self.rollback_data),
                    'records': self.rollback_data
                }, f, indent=2)
            
            self.logger.info(f"✓ Rollback data saved to {rollback_file}")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save rollback data: {e}")
    
    def _download_file(self, url: str) -> Tuple[bytes, int]:
        """Download file from external S3 URL."""
        response = requests.get(url, stream=True, timeout=300)
        response.raise_for_status()
        content = response.content
        return content, len(content)
    
    def _upload_to_s3(self, content: bytes, s3_key: str, file_name: str) -> str:
        """Upload file content to your S3 bucket."""
        bucket_name = AWS_CONFIG["bucket_name"]
        
        self.s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=content,
            ContentDisposition=f'attachment; filename="{file_name}"'
        )
        
        return f"https://{bucket_name}.s3.{AWS_CONFIG['region']}.amazonaws.com/{s3_key}"
    
    def _clean_filename(self, name: str) -> str:
        """Clean account name for use in file paths."""
        import re
        cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
        cleaned = re.sub(r'_+', '_', cleaned)
        cleaned = cleaned.strip('_.')
        return cleaned or 'Unknown'
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def run(self):
        """Execute the full migration."""
        try:
            # Print banner
            mode = "DRY RUN" if self.dry_run else "LIVE EXECUTION"
            self.logger.info("=" * 60)
            self.logger.info(f"Phase 2: Full Migration - {mode}")
            self.logger.info("=" * 60)
            
            if self.dry_run:
                self.logger.info("🧪 DRY RUN MODE - No changes will be made")
            else:
                self.logger.info("⚠️  LIVE MODE - Salesforce will be modified!")
                self.logger.info("⚠️  Users will switch to your S3 files")
            
            self.logger.info("=" * 60)
            
            # Start migration run tracking
            config_snapshot = {
                'salesforce': {k: v if k != 'password' else '***' for k, v in SALESFORCE_CONFIG.items()},
                'aws': {k: v if 'key' not in k.lower() else '***' for k, v in AWS_CONFIG.items()},
                'migration': MIGRATION_CONFIG,
                'dry_run': self.dry_run
            }
            
            self.run_id = self.db.start_migration_run('full_migration', config_snapshot)
            
            # Validate backup data exists
            if not self.validate_backup_data():
                raise Exception("Phase 1 backup validation failed")
            
            # Authenticate
            if not self.authenticate_salesforce():
                raise Exception("Salesforce authentication failed")
            
            if not self.authenticate_aws():
                raise Exception("AWS authentication failed")
            
            # Get current Salesforce files
            current_sf_records = self.get_current_salesforce_files()
            self.stats['total_files'] = len(current_sf_records)
            
            # Identify new files that need copying
            new_files = self.identify_new_files(current_sf_records)
            
            # Copy new files
            if not self.copy_new_files(new_files):
                raise Exception("Failed to copy new files")
            
            # Update Salesforce URLs
            if not self.update_salesforce_urls():
                raise Exception("Failed to update Salesforce URLs")
            
            # Save rollback data
            self.save_rollback_data()
            
            # Validate migration
            if not self.validate_migration():
                self.logger.warning("⚠️ Migration validation failed - consider rollback")
            
            # Final statistics
            self._print_final_stats()
            
            # Update final run stats
            self.db.update_run_stats(self.run_id, **self.stats)
            self.db.end_migration_run(self.run_id, 'completed')
            
        except Exception as e:
            error_msg = f"Full migration failed: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            
            if self.run_id:
                self.db.end_migration_run(self.run_id, 'failed', error_msg)
            
            raise
        
        finally:
            self.cleanup()
    
    def _print_final_stats(self):
        """Print final migration statistics."""
        mode = "DRY RUN" if self.dry_run else "LIVE"
        
        self.logger.info("=" * 60)
        self.logger.info(f"FULL MIGRATION SUMMARY ({mode})")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files in Salesforce: {self.stats['total_files']}")
        self.logger.info(f"New files copied to S3: {self.stats['new_files']}")
        self.logger.info(f"Salesforce URLs updated: {self.stats['updated_urls']}")
        self.logger.info(f"Failed URL updates: {self.stats['failed_updates']}")
        
        if self.stats['total_size'] > 0:
            self.logger.info(f"New data migrated: {self._format_size(self.stats['total_size'])}")
        
        if not self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("✅ MIGRATION COMPLETED")
            self.logger.info("✅ Users are now using your S3 files")
            self.logger.info("✅ Original files remain in external S3 as backup")
        else:
            self.logger.info("=" * 60)
            self.logger.info("🧪 DRY RUN COMPLETED")
            self.logger.info("🧪 Use --execute to perform actual migration")
        
        self.logger.info("=" * 60)
    
    def cleanup(self):
        """Clean up resources."""
        if self.db:
            self.db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Phase 2: Full migration with Salesforce updates")
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Test mode - no changes will be made (default)'
    )
    parser.add_argument(
        '--execute', 
        action='store_true', 
        help='Execute the migration (modifies Salesforce)'
    )
    
    args = parser.parse_args()
    
    # Default to dry-run if no option specified
    if not args.dry_run and not args.execute:
        print("No execution mode specified. Defaulting to --dry-run")
        print("Use --execute to perform actual migration")
        dry_run = True
    elif args.execute:
        dry_run = False
        # Confirmation for live execution
        print("\n⚠️  WARNING: This will modify Salesforce production data!")
        print("⚠️  Users will switch from external S3 to your S3 files!")
        confirm = input("Type 'CONFIRM' to proceed with live migration: ")
        if confirm != 'CONFIRM':
            print("Migration cancelled.")
            sys.exit(0)
    else:
        dry_run = True
    
    try:
        migration = FullMigration(dry_run=dry_run)
        migration.run()
        
    except KeyboardInterrupt:
        print("\n⚠ Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()