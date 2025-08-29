#!/usr/bin/env python3
"""
Simple Backup Migration Script
=============================

Simplified backup-only script based on the working salesforce_s3_migration.py
but WITHOUT updating Salesforce URLs - just creates backup copies.

Features:
- Uses the proven query approach from the original script
- Backs up files to your S3 without modifying Salesforce
- Tracks progress in SQLite database
- Works with existing config.py settings

Usage:
python simple_backup_migration.py
"""

import os
import sys
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

# Import our database manager and original modules
from migration_db import MigrationDB, calculate_file_hash

# Import configuration
try:
    from config import SALESFORCE_CONFIG, AWS_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
    
    # Debug: Show which configuration values are being used
    print("\n" + "="*60)
    print("DEBUG: CONFIGURATION VALUES LOADED")
    print("="*60)
    print("MIGRATION_CONFIG values:")
    print(f"  dry_run: {MIGRATION_CONFIG.get('dry_run')}")
    print(f"  test_single_account: {MIGRATION_CONFIG.get('test_single_account')}")
    print(f"  test_account_name: {MIGRATION_CONFIG.get('test_account_name')}")
    print(f"  max_test_files: {MIGRATION_CONFIG.get('max_test_files')}")
    print(f"  batch_size: {MIGRATION_CONFIG.get('batch_size')}")
    
    print("\nAWS_CONFIG values:")
    print(f"  region: {AWS_CONFIG.get('region')}")
    print(f"  bucket_name: {AWS_CONFIG.get('bucket_name')}")
    
    print("\nSALESFORCE_CONFIG values:")
    print(f"  username: {SALESFORCE_CONFIG.get('username')}")
    print(f"  domain: {SALESFORCE_CONFIG.get('domain')}")
    print("="*60)
    
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


def setup_logging() -> logging.Logger:
    """Set up logging configuration."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"simple_backup_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Simple backup logging initialized. Log file: {log_file}")
    return logger


class SalesforceManager:
    """Manages Salesforce authentication and operations."""
    
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.sf = None
        
    def authenticate(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            self.sf = Salesforce(
                username=self.config["username"],
                password=self.config["password"],
                security_token=self.config["security_token"],
                domain=self.config["domain"]
            )
            
            self.logger.info("✓ Successfully authenticated with Salesforce")
            return True
            
        except SalesforceError as e:
            self.logger.error(f"❌ Salesforce authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during Salesforce authentication: {e}")
            return False
    
    def get_doclistentry_files(self, test_account_id: Optional[str] = None, 
                              test_account_name: Optional[str] = None) -> List[Dict]:
        """Get DocListEntry__c records with S3 URLs linked to Account objects."""
        try:
            target_account_ids = []
            
            # Resolve account name to ID if needed
            if test_account_name and not test_account_id:
                self.logger.info(f"Looking up Account ID for name: {test_account_name}")
                account_query = f"""
                    SELECT Id, Name
                    FROM Account
                    WHERE Name = '{test_account_name}'
                    AND IsDeleted = FALSE
                    LIMIT 1
                """
                
                account_result = self.sf.query(account_query)
                if account_result['records']:
                    test_account_id = account_result['records'][0]['Id']
                    self.logger.info(f"Found Account ID: {test_account_id} for name: {test_account_name}")
                else:
                    self.logger.error(f"No account found with name: {test_account_name}")
                    return []
            
            # Prepare account IDs for filtering
            if test_account_id:
                target_account_ids = [test_account_id]
                self.logger.info(f"Filtering by Account ID: {test_account_id}")
            else:
                # Get all accounts with DocListEntry__c records (using the working pattern from salesforce_s3_migration.py)
                self.logger.info("Getting all accounts with DocListEntry__c records...")
                accounts_query = """
                    SELECT DISTINCT Account__c, Account__r.Name
                    FROM DocListEntry__c
                    WHERE Account__c != NULL
                    AND IsDeleted = FALSE
                    AND Document__c != NULL
                    LIMIT 200
                """
                
                accounts_result = self.sf.query(accounts_query)
                target_account_ids = [acc['Account__c'] for acc in accounts_result['records']]
                
                self.logger.info(f"Found {len(target_account_ids)} accounts with DocListEntry__c files")
            
            if not target_account_ids:
                self.logger.warning("No accounts with DocListEntry__c files found")
                return []
            
            # Now query DocListEntry__c records for the target accounts
            all_files = []
            batch_size = 20  # Process account IDs in batches
            
            for i in range(0, len(target_account_ids), batch_size):
                batch_ids = target_account_ids[i:i + batch_size]
                ids_str = "', '".join(batch_ids)
                
                # Query DocListEntry__c records for this batch of accounts
                files_query = f"""
                    SELECT Id, Name, Document__c, Type_Current__c, Type_Original__c, 
                           DocType__c, Parent_Folder__c, Visibility__c, Identifier__c,
                           Source__c, ClientName__c, ApplicableYear__c, TaxonomyStage__c,
                           Account__c, Account__r.Name, CreatedDate, LastModifiedDate
                    FROM DocListEntry__c
                    WHERE Account__c IN ('{ids_str}')
                    AND IsDeleted = FALSE
                    AND Document__c != NULL
                    AND Type_Current__c = 'Document'
                    ORDER BY Account__c, Name
                """
                
                try:
                    self.logger.info(f"Querying DocListEntry__c files for batch {i//batch_size + 1}/{(len(target_account_ids) + batch_size - 1)//batch_size}")
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
                    self.logger.error(f"Error querying DocListEntry__c files for batch: {e}")
                    continue
            
            self.logger.info(f"Found {len(all_files)} DocListEntry__c files with S3 URLs")
            return all_files
            
        except SalesforceError as e:
            self.logger.error(f"Error querying Salesforce: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error querying files: {e}")
            return []


class S3Manager:
    """Manages AWS S3 operations."""
    
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.logger = logger
        self.s3_client = None
        
    def authenticate(self) -> bool:
        """Initialize S3 client."""
        try:
            # Check if credentials are provided in config
            if (self.config.get('access_key_id') and 
                self.config.get('secret_access_key') and
                self.config['access_key_id'] != '<your_aws_access_key_id>' and
                self.config['secret_access_key'] != '<your_aws_secret_access_key>'):
                
                # Use credentials from config
                self.s3_client = boto3.client(
                    's3',
                    region_name=self.config['region'],
                    aws_access_key_id=self.config['access_key_id'],
                    aws_secret_access_key=self.config['secret_access_key']
                )
                self.logger.info("Using AWS credentials from config file")
            else:
                # Fall back to default credential chain
                self.s3_client = boto3.client('s3', region_name=self.config['region'])
                self.logger.info("Using default AWS credential chain")
            
            # Test connection by listing buckets
            self.s3_client.list_buckets()
            
            self.logger.info("✓ Successfully authenticated with AWS S3")
            return True
            
        except NoCredentialsError:
            self.logger.error("❌ AWS credentials not found. Please configure your credentials in config.py or use AWS CLI.")
            return False
        except ClientError as e:
            self.logger.error(f"❌ AWS S3 authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during S3 authentication: {e}")
            return False
    
    def create_bucket_if_not_exists(self) -> bool:
        """Create S3 bucket if it doesn't exist."""
        try:
            bucket_name = self.config['bucket_name']
            
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                self.logger.info(f"✓ S3 bucket '{bucket_name}' already exists")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # Bucket doesn't exist, create it
                    if self.config['region'] == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.config['region']}
                        )
                    
                    self.logger.info(f"✓ Created S3 bucket: {bucket_name}")
                    return True
                else:
                    self.logger.error(f"❌ Error checking bucket existence: {e}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"❌ Error creating S3 bucket: {e}")
            return False
    
    def download_from_external_s3(self, s3_url: str) -> Optional[bytes]:
        """Download file from external S3 bucket using public URL."""
        try:
            # Download using requests (public URL)
            response = requests.get(s3_url, timeout=60)
            
            if response.status_code == 200:
                return response.content
            else:
                self.logger.error(f"Failed to download file. Status: {response.status_code}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error downloading from external S3: {e}")
            return None
    
    def upload_file(self, file_content: bytes, s3_key: str, 
                   content_type: str = 'binary/octet-stream') -> Optional[str]:
        """Upload file to S3."""
        try:
            bucket_name = self.config['bucket_name']
            
            self.s3_client.put_object(
                Bucket=bucket_name,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type
            )
            
            s3_url = f"https://{bucket_name}.s3.{self.config['region']}.amazonaws.com/{s3_key}"
            return s3_url
            
        except ClientError as e:
            self.logger.error(f"Error uploading file to S3: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error uploading to S3: {e}")
            return None


class SimpleBackupMigration:
    """Simple backup migration orchestrator."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.sf_manager = SalesforceManager(SALESFORCE_CONFIG, logger)
        self.s3_manager = S3Manager(AWS_CONFIG, logger)
        self.db = MigrationDB()
        
        self.stats = {
            'total_files': 0,
            'successful_backups': 0,
            'failed_backups': 0,
            'skipped_files': 0,
            'total_size_mb': 0
        }
        
        self.run_id = None
    
    def initialize(self) -> bool:
        """Initialize all connections and resources."""
        self.logger.info("Initializing backup process...")
        
        # Start run tracking
        config_snapshot = {
            'salesforce': {k: v if k != 'password' else '***' for k, v in SALESFORCE_CONFIG.items()},
            'aws': {k: v if 'key' not in k.lower() else '***' for k, v in AWS_CONFIG.items()},
            'migration': MIGRATION_CONFIG
        }
        self.run_id = self.db.start_migration_run('simple_backup', config_snapshot)
        
        # Authenticate with Salesforce
        if not self.sf_manager.authenticate():
            return False
        
        # Authenticate with AWS S3
        if not self.s3_manager.authenticate():
            return False
        
        # Create S3 bucket if needed
        if not self.s3_manager.create_bucket_if_not_exists():
            return False
        
        self.logger.info("✓ Initialization completed successfully")
        return True
    
    def should_process_file(self, file_info: Dict) -> Tuple[bool, str]:
        """Determine if a file should be processed."""
        # Check if S3 URL exists
        if not file_info.get('document_url'):
            return False, "No S3 URL found"
        
        # Check if it's trackland S3 URL (external)
        if 'trackland-doc-storage' not in file_info['document_url']:
            return False, "Not a trackland S3 URL"
        
        # Get file extension from filename
        filename = file_info['name']
        file_ext = None
        if '.' in filename:
            file_ext = '.' + filename.split('.')[-1].lower()
        
        # Check file extension
        allowed_extensions = MIGRATION_CONFIG.get('allowed_extensions', [])
        if allowed_extensions and file_ext and file_ext not in allowed_extensions:
            return False, f"File extension not allowed: {file_ext}"
        
        return True, "OK"
    
    def generate_s3_key(self, file_info: Dict) -> str:
        """Generate S3 key following the required structure."""
        account_id = file_info['account_id']
        account_name = file_info['account_name']
        filename = file_info['name']
        
        # Clean account name for S3 path
        clean_account_name = "".join(c for c in account_name if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        clean_account_name = clean_account_name.replace(' ', '_')
        
        # Clean filename for S3
        safe_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        
        # Generate S3 key
        s3_key = f"uploads/{account_id}/{clean_account_name}/{safe_filename}"
        return s3_key
    
    def backup_file(self, file_info: Dict) -> bool:
        """Backup a single file to S3."""
        try:
            filename = file_info['name']
            doclistentry_id = file_info['doclistentry_id']
            account_id = file_info['account_id']
            account_name = file_info['account_name']
            external_s3_url = file_info['document_url']
            
            self.logger.info(f"📄 Processing file: {filename} (Account: {account_name})")
            
            # Check if file should be processed
            should_process, reason = self.should_process_file(file_info)
            if not should_process:
                self.logger.warning(f"Skipping file {filename}: {reason}")
                self.stats['skipped_files'] += 1
                return False
            
            # Generate S3 key
            s3_key = self.generate_s3_key(file_info)
            
            if not MIGRATION_CONFIG.get('dry_run', False):
                # Download file from external S3
                file_content = self.s3_manager.download_from_external_s3(external_s3_url)
                
                if not file_content:
                    self.logger.error(f"Failed to download file: {filename}")
                    self.stats['failed_backups'] += 1
                    return False
                
                # Check file size limits
                max_size_bytes = MIGRATION_CONFIG.get("max_file_size_mb", 100) * 1024 * 1024
                if len(file_content) > max_size_bytes:
                    self.logger.warning(f"File too large, skipping: {filename} ({len(file_content)} bytes)")
                    self.stats['skipped_files'] += 1
                    return False
                
                # Upload to our S3
                new_s3_url = self.s3_manager.upload_file(file_content, s3_key)
                
                if not new_s3_url:
                    self.logger.error(f"Failed to upload file: {filename}")
                    self.stats['failed_backups'] += 1
                    return False
                
                # Record in database
                file_hash = calculate_file_hash(file_content)
                file_data = {
                    'doclist_entry_id': doclistentry_id,
                    'account_id': account_id,
                    'account_name': account_name,
                    'original_url': external_s3_url,
                    'your_s3_key': s3_key,
                    'your_s3_url': new_s3_url,
                    'file_name': filename,
                    'file_size_bytes': len(file_content),
                    'file_hash': file_hash,
                    'backup_timestamp': datetime.now().isoformat(),
                    'last_modified_sf': file_info.get('last_modified_date')
                }
                
                self.db.record_file_migration(file_data)
                self.stats['total_size_mb'] += len(file_content) / (1024 * 1024)
                
            else:
                # Dry run mode
                bucket_name = AWS_CONFIG['bucket_name']
                new_s3_url = f"https://{bucket_name}.s3.{AWS_CONFIG['region']}.amazonaws.com/{s3_key}"
                
                self.logger.info("=" * 50)
                self.logger.info("🧪 DRY RUN - What would happen:")
                self.logger.info(f"  📁 File: {filename}")
                self.logger.info(f"  🏢 Account: {account_name} ({account_id})")
                self.logger.info(f"  ⬇️  Would download from: {external_s3_url}")
                self.logger.info(f"  ⬆️  Would backup to: {new_s3_url}")
                self.logger.info(f"  📋 Would record in database (NO Salesforce changes)")
                self.logger.info("=" * 50)
            
            self.stats['successful_backups'] += 1
            self.logger.info(f"✓ Backed up file: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error backing up file {filename}: {e}")
            self.stats['failed_backups'] += 1
            
            # Record error in database
            if self.run_id:
                self.db.record_migration_error(
                    self.run_id, doclistentry_id, 'backup_error', 
                    str(e), external_s3_url
                )
            
            return False
    
    def run_backup(self) -> bool:
        """Run the complete backup process."""
        try:
            self.logger.info("=" * 60)
            self.logger.info("SIMPLE BACKUP MIGRATION")
            self.logger.info("=" * 60)
            self.logger.info("📋 BACKUP-ONLY MODE - Salesforce will NOT be modified")
            self.logger.info("📋 Users will continue using original files")
            self.logger.info("📋 Creating backup copies in your S3 bucket")
            self.logger.info("=" * 60)
            
            # Check if we're in test mode
            test_account_id = None
            test_account_name = None
            
            if MIGRATION_CONFIG.get('test_single_account', False):
                self.logger.info("🧪 RUNNING IN TEST MODE - Single Account Only")
                test_account_id = MIGRATION_CONFIG.get('test_account_id')
                test_account_name = MIGRATION_CONFIG.get('test_account_name')
                
                if test_account_id:
                    self.logger.info(f"   Target Account ID: {test_account_id}")
                elif test_account_name:
                    self.logger.info(f"   Target Account Name: {test_account_name}")
                else:
                    self.logger.info("   Will use first account found")
                
                max_test_files = MIGRATION_CONFIG.get('max_test_files', 5)
                self.logger.info(f"   Max files to process: {max_test_files}")
            
            # Get files to backup
            files_to_backup = self.sf_manager.get_doclistentry_files(test_account_id, test_account_name)
            
            if not files_to_backup:
                self.logger.warning("No DocListEntry__c files found to backup")
                return True
            
            # Limit files in test mode
            if MIGRATION_CONFIG.get('test_single_account', False):
                max_test_files = MIGRATION_CONFIG.get('max_test_files', 5)
                if len(files_to_backup) > max_test_files:
                    self.logger.info(f"Limiting to {max_test_files} files for testing")
                    files_to_backup = files_to_backup[:max_test_files]
            
            self.stats['total_files'] = len(files_to_backup)
            self.logger.info(f"Found {len(files_to_backup)} DocListEntry__c files to backup")
            
            # Show account summary
            accounts = {}
            for file_info in files_to_backup:
                account_id = file_info['account_id']
                account_name = file_info['account_name']
                if account_id not in accounts:
                    accounts[account_id] = {'name': account_name, 'file_count': 0}
                accounts[account_id]['file_count'] += 1
            
            self.logger.info(f"Files will be backed up for {len(accounts)} account(s):")
            for account_id, info in accounts.items():
                self.logger.info(f"  - {info['name']} ({account_id}): {info['file_count']} files")
            
            # Process files in batches
            batch_size = MIGRATION_CONFIG.get('batch_size', 100)
            for i in range(0, len(files_to_backup), batch_size):
                batch = files_to_backup[i:i + batch_size]
                batch_num = i//batch_size + 1
                total_batches = (len(files_to_backup) + batch_size - 1)//batch_size
                
                self.logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} files)")
                
                for file_info in batch:
                    self.backup_file(file_info)
                
                # Update database stats
                self.db.update_run_stats(self.run_id, **self.stats)
                
                # Progress update
                progress = (i + len(batch)) / len(files_to_backup) * 100
                success_rate = (self.stats['successful_backups'] / max(1, self.stats['successful_backups'] + self.stats['failed_backups'])) * 100
                self.logger.info(f"📈 Progress: {progress:.1f}% complete, {success_rate:.1f}% success rate")
            
            # Print final statistics
            self.print_backup_summary()
            
            # Update final run stats
            self.db.update_run_stats(self.run_id, **self.stats)
            self.db.end_migration_run(self.run_id, 'completed')
            
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Error during backup process: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            
            if self.run_id:
                self.db.end_migration_run(self.run_id, 'failed', str(e))
            
            return False
    
    def print_backup_summary(self):
        """Print backup statistics."""
        stats = self.stats
        
        self.logger.info("=" * 60)
        self.logger.info("BACKUP SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files processed: {stats['total_files']}")
        self.logger.info(f"Successfully backed up: {stats['successful_backups']}")
        self.logger.info(f"Failed backups: {stats['failed_backups']}")
        self.logger.info(f"Skipped files: {stats['skipped_files']}")
        self.logger.info(f"Total data backed up: {stats['total_size_mb']:.2f} MB")
        
        if stats['total_files'] > 0:
            success_rate = (stats['successful_backups'] / stats['total_files']) * 100
            self.logger.info(f"Success rate: {success_rate:.1f}%")
        
        self.logger.info("=" * 60)
        self.logger.info("📋 BACKUP COMPLETED - Salesforce unchanged")
        self.logger.info("📋 Users continue using original files")
        self.logger.info("📋 Backup files available in your S3 bucket")
        self.logger.info("📋 Run Phase 2 migration when ready to switch users")
        self.logger.info("=" * 60)
    
    def cleanup(self):
        """Clean up resources."""
        if self.db:
            self.db.close()


def main():
    """Main execution function."""
    print("Simple Backup Migration Script")
    print("=" * 50)
    
    # Debug: Show what's actually being used in main()
    print("DEBUG: Values at runtime in main():")
    print(f"  MIGRATION_CONFIG['dry_run'] = {MIGRATION_CONFIG.get('dry_run')}")
    print(f"  MIGRATION_CONFIG['test_single_account'] = {MIGRATION_CONFIG.get('test_single_account')}")
    print("=" * 50)
    
    # Show current mode
    if MIGRATION_CONFIG.get('dry_run', False):
        print("🧪 DRY RUN MODE - No files will actually be moved")
        print("=" * 50)
    else:
        print("🚀 LIVE MODE - Files will be processed")
        print("=" * 50)
    
    if MIGRATION_CONFIG.get('test_single_account', False):
        print("🔍 TEST MODE - Single Account Only")
        print("=" * 50)
    else:
        print("🌍 FULL MODE - All Accounts")
        print("=" * 50)
    
    # Setup logging
    logger = setup_logging()
    
    # Initialize and run backup
    try:
        backup_migration = SimpleBackupMigration(logger)
        
        if not backup_migration.initialize():
            logger.error("❌ Failed to initialize backup process")
            return False
        
        success = backup_migration.run_backup()
        
        if success:
            logger.info("✅ Backup process completed successfully!")
            return True
        else:
            logger.error("❌ Backup process failed!")
            return False
            
    except KeyboardInterrupt:
        logger.info("⚠️ Backup process interrupted by user")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False
    finally:
        if 'backup_migration' in locals():
            backup_migration.cleanup()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)