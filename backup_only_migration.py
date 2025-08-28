#!/usr/bin/env python3
"""
Phase 1: Backup-Only Migration Script
=====================================

This script backs up files from external S3 to your S3 bucket WITHOUT
modifying Salesforce. Users continue using original files while you
build up a complete backup mirror.

Features:
- Backs up all DocListEntry__c files to your S3
- Tracks everything in SQLite database
- Does NOT modify Salesforce (users unaffected)
- Supports incremental backups (only new/changed files)
- Comprehensive logging and error handling

Usage:
1. python backup_only_migration.py --full      # Full backup
2. python backup_only_migration.py --incremental  # Only new files
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

# Import our database manager
from migration_db import MigrationDB, calculate_file_hash

# Import configuration
try:
    from config import SALESFORCE_CONFIG, AWS_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


class BackupOnlyMigration:
    """Phase 1 migration - backup files without modifying Salesforce."""
    
    def __init__(self, incremental: bool = False):
        """Initialize the backup migration."""
        self.incremental = incremental
        self.logger = self._setup_logging()
        self.db = MigrationDB()
        
        # Initialize counters
        self.stats = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'new_files': 0,
            'updated_files': 0,
            'total_size': 0
        }
        
        self.sf = None
        self.s3_client = None
        self.run_id = None
        
    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_type = "incremental" if self.incremental else "full"
        log_file = log_dir / f"backup_migration_{run_type}_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Backup migration logging initialized. Log file: {log_file}")
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
                # Use default credential chain (AWS CLI, environment variables, IAM roles)
                self.s3_client = boto3.client('s3', region_name=AWS_CONFIG["region"])
            
            # Test authentication by listing buckets
            self.s3_client.list_buckets()
            
            # Ensure target bucket exists
            self._ensure_bucket_exists()
            
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
    
    def _ensure_bucket_exists(self):
        """Ensure the target S3 bucket exists."""
        bucket_name = AWS_CONFIG["bucket_name"]
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            self.logger.info(f"✓ S3 bucket '{bucket_name}' exists and accessible")
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                self.logger.info(f"Creating S3 bucket '{bucket_name}'...")
                try:
                    if AWS_CONFIG["region"] == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': AWS_CONFIG["region"]}
                        )
                    self.logger.info(f"✓ Created S3 bucket '{bucket_name}'")
                except ClientError as create_error:
                    self.logger.error(f"❌ Failed to create bucket '{bucket_name}': {create_error}")
                    raise
            else:
                self.logger.error(f"❌ Cannot access bucket '{bucket_name}': {e}")
                raise
    
    def get_doclist_entries(self) -> List[Dict]:
        """Get DocListEntry__c records from Salesforce."""
        try:
            self.logger.info("Querying DocListEntry__c records from Salesforce...")
            
            # Base query for DocListEntry__c with related Account data
            base_query = """
                SELECT Id, Name, Document__c, Account__c, Account__r.Name, 
                       LastModifiedDate, CreatedDate, SystemModstamp
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
            """
            
            # For incremental backup, only get files modified since last backup
            if self.incremental:
                last_backup_files = self.db.find_incremental_files()
                if last_backup_files:
                    self.logger.info(f"Incremental mode: comparing against {len(last_backup_files)} existing backup records")
                else:
                    self.logger.info("No previous backup found, running full backup")
            
            # Execute query
            records = []
            
            # Handle pagination for large datasets
            query_result = self.sf.query_all(base_query)
            total_records = query_result['totalSize']
            records = query_result['records']
            
            self.logger.info(f"Found {total_records} DocListEntry__c records")
            
            # Filter for incremental if needed
            if self.incremental:
                existing_ids = set(self.db.find_incremental_files())
                if existing_ids:
                    original_count = len(records)
                    records = [r for r in records if r['Id'] not in existing_ids]
                    self.logger.info(f"Incremental filter: {len(records)} new/changed records (was {original_count})")
            
            return records
            
        except SalesforceError as e:
            self.logger.error(f"❌ Failed to query Salesforce: {e}")
            raise
        except Exception as e:
            self.logger.error(f"❌ Unexpected error querying Salesforce: {e}")
            raise
    
    def download_file(self, url: str) -> Tuple[bytes, int]:
        """Download file from external S3 URL."""
        try:
            self.logger.debug(f"Downloading file from: {url}")
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()
            
            content = response.content
            size = len(content)
            
            # Check file size limits
            max_size_bytes = MIGRATION_CONFIG.get("max_file_size_mb", 100) * 1024 * 1024
            if size > max_size_bytes:
                raise ValueError(f"File size {size} bytes exceeds limit of {max_size_bytes} bytes")
            
            return content, size
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to download file from {url}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error downloading file: {e}")
            raise
    
    def upload_to_s3(self, content: bytes, s3_key: str, file_name: str) -> str:
        """Upload file content to your S3 bucket."""
        try:
            bucket_name = AWS_CONFIG["bucket_name"]
            
            # Upload file
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=content,
                ContentDisposition=f'attachment; filename="{file_name}"'
            )
            
            # Generate the S3 URL
            s3_url = f"https://{bucket_name}.s3.{AWS_CONFIG['region']}.amazonaws.com/{s3_key}"
            
            self.logger.debug(f"Uploaded to S3: {s3_url}")
            return s3_url
            
        except ClientError as e:
            self.logger.error(f"Failed to upload to S3: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error uploading to S3: {e}")
            raise
    
    def process_single_file(self, record: Dict) -> bool:
        """Process a single DocListEntry record for backup."""
        doclist_id = record['Id']
        
        try:
            # Extract file information
            original_url = record['Document__c']
            account_id = record['Account__c']
            account_name = record['Account__r']['Name'] if record['Account__r'] else 'Unknown'
            
            # Clean account name for file path
            clean_account_name = self._clean_filename(account_name)
            
            # Extract file name from URL
            parsed_url = urlparse(original_url)
            file_name = os.path.basename(parsed_url.path) or f"file_{doclist_id}"
            
            # Check file extension
            file_ext = os.path.splitext(file_name)[1].lower()
            allowed_extensions = MIGRATION_CONFIG.get("allowed_extensions", [])
            if allowed_extensions and file_ext not in allowed_extensions:
                self.logger.info(f"Skipping file {file_name} - extension {file_ext} not allowed")
                self.stats['skipped'] += 1
                return True
            
            # Generate S3 key with organized structure
            s3_key = f"uploads/{account_id}/{clean_account_name}/{file_name}"
            
            # Check if file already exists in S3 (for incremental)
            if self.incremental and self._file_exists_in_s3(s3_key):
                self.logger.debug(f"File already exists in S3, skipping: {s3_key}")
                self.stats['skipped'] += 1
                return True
            
            # Download file from external S3
            self.logger.info(f"Processing: {file_name} for account {account_name}")
            content, file_size = self.download_file(original_url)
            
            # Calculate file hash for change detection
            file_hash = calculate_file_hash(content)
            
            # Upload to your S3
            your_s3_url = self.upload_to_s3(content, s3_key, file_name)
            
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
            
            is_new = self.db.record_file_migration(file_data)
            if is_new:
                self.stats['new_files'] += 1
            else:
                self.stats['updated_files'] += 1
            
            self.stats['successful'] += 1
            self.stats['total_size'] += file_size
            
            self.logger.info(f"✓ Backed up: {file_name} ({self._format_size(file_size)})")
            return True
            
        except Exception as e:
            error_msg = f"Failed to process {doclist_id}: {str(e)}"
            self.logger.error(error_msg)
            
            # Record error in database
            self.db.record_migration_error(
                self.run_id, doclist_id, 'backup_error', 
                str(e), record.get('Document__c')
            )
            
            self.stats['failed'] += 1
            return False
    
    def _file_exists_in_s3(self, s3_key: str) -> bool:
        """Check if file already exists in S3."""
        try:
            self.s3_client.head_object(Bucket=AWS_CONFIG["bucket_name"], Key=s3_key)
            return True
        except ClientError:
            return False
    
    def _clean_filename(self, name: str) -> str:
        """Clean account name for use in file paths."""
        import re
        # Replace invalid characters with underscores
        cleaned = re.sub(r'[<>:"/\\|?*]', '_', name)
        # Remove multiple consecutive underscores
        cleaned = re.sub(r'_+', '_', cleaned)
        # Remove leading/trailing underscores and dots
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
        """Execute the backup migration."""
        try:
            # Print banner
            run_type = "INCREMENTAL BACKUP" if self.incremental else "FULL BACKUP"
            self.logger.info("=" * 60)
            self.logger.info(f"Phase 1: {run_type} Migration")
            self.logger.info("=" * 60)
            self.logger.info("📋 BACKUP-ONLY MODE - Salesforce will NOT be modified")
            self.logger.info("📋 Users will continue using original files")
            self.logger.info("📋 Building backup mirror in your S3 bucket")
            self.logger.info("=" * 60)
            
            # Start migration run tracking
            config_snapshot = {
                'salesforce': {k: v if k != 'password' else '***' for k, v in SALESFORCE_CONFIG.items()},
                'aws': {k: v if 'key' not in k.lower() else '***' for k, v in AWS_CONFIG.items()},
                'migration': MIGRATION_CONFIG,
                'incremental': self.incremental
            }
            
            run_type_db = 'incremental' if self.incremental else 'backup'
            self.run_id = self.db.start_migration_run(run_type_db, config_snapshot)
            
            # Authenticate
            if not self.authenticate_salesforce():
                raise Exception("Salesforce authentication failed")
            
            if not self.authenticate_aws():
                raise Exception("AWS authentication failed")
            
            # Get DocListEntry records
            records = self.get_doclist_entries()
            
            if not records:
                self.logger.info("No records found to process")
                return
            
            self.logger.info(f"Starting backup of {len(records)} files...")
            
            # Process files in batches
            batch_size = MIGRATION_CONFIG.get("batch_size", 100)
            total_batches = (len(records) + batch_size - 1) // batch_size
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(records))
                batch = records[start_idx:end_idx]
                
                self.logger.info(f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} files)")
                
                for record in batch:
                    self.stats['processed'] += 1
                    self.process_single_file(record)
                    
                    # Update run stats periodically
                    if self.stats['processed'] % 50 == 0:
                        self.db.update_run_stats(self.run_id, **self.stats)
                
                # Progress update
                progress = (batch_num + 1) / total_batches * 100
                self.logger.info(f"Progress: {progress:.1f}% ({self.stats['successful']}/{self.stats['processed']} successful)")
            
            # Final statistics
            self._print_final_stats()
            
            # Update final run stats
            self.db.update_run_stats(self.run_id, **self.stats)
            self.db.end_migration_run(self.run_id, 'completed')
            
        except Exception as e:
            error_msg = f"Migration failed: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            
            if self.run_id:
                self.db.end_migration_run(self.run_id, 'failed', error_msg)
            
            raise
        
        finally:
            self.cleanup()
    
    def _print_final_stats(self):
        """Print final migration statistics."""
        self.logger.info("=" * 60)
        self.logger.info("BACKUP MIGRATION SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files processed: {self.stats['processed']}")
        self.logger.info(f"Successfully backed up: {self.stats['successful']}")
        self.logger.info(f"Failed backups: {self.stats['failed']}")
        self.logger.info(f"Skipped files: {self.stats['skipped']}")
        self.logger.info(f"New files: {self.stats['new_files']}")
        self.logger.info(f"Updated files: {self.stats['updated_files']}")
        self.logger.info(f"Total data backed up: {self._format_size(self.stats['total_size'])}")
        
        if self.stats['processed'] > 0:
            success_rate = (self.stats['successful'] / self.stats['processed']) * 100
            self.logger.info(f"Success rate: {success_rate:.1f}%")
        
        self.logger.info("=" * 60)
        self.logger.info("📋 BACKUP COMPLETED - Salesforce unchanged")
        self.logger.info("📋 Users continue using original files")
        self.logger.info("📋 Run Phase 2 migration when ready to switch users")
        self.logger.info("=" * 60)
    
    def cleanup(self):
        """Clean up resources."""
        if self.db:
            self.db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Phase 1: Backup-only file migration")
    parser.add_argument(
        '--incremental', 
        action='store_true', 
        help='Run incremental backup (only new/changed files)'
    )
    parser.add_argument(
        '--full', 
        action='store_true', 
        help='Run full backup (all files)'
    )
    
    args = parser.parse_args()
    
    # Default to full backup if no option specified
    if not args.incremental and not args.full:
        print("No backup type specified. Use --full or --incremental")
        print("Example: python backup_only_migration.py --full")
        sys.exit(1)
    
    if args.incremental and args.full:
        print("Cannot specify both --incremental and --full")
        sys.exit(1)
    
    try:
        migration = BackupOnlyMigration(incremental=args.incremental)
        migration.run()
        
    except KeyboardInterrupt:
        print("\n⚠ Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()