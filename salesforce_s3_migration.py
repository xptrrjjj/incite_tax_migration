#!/usr/bin/env python3
"""
Salesforce DocListEntry S3 Migration Script
===========================================

This script migrates files from an external S3 bucket (referenced in DocListEntry__c) 
to your own S3 bucket, then updates the Salesforce DocListEntry__c.Document__c URLs.

Requirements:
- pip install simple-salesforce boto3 requests

Usage:
1. Update the configuration variables below
2. Run: python salesforce_s3_migration.py
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


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default configuration (will be overridden by config.py if present)
DEFAULT_SALESFORCE_CONFIG = {
    "username": "Automation@incitetax.com",
    "password": "<insert_password>",
    "security_token": "<insert_security_token>",
    "domain": "login"  # Use 'test' for sandbox
}

DEFAULT_AWS_CONFIG = {
    "region": "us-east-1",
    "bucket_name": "<new-s3-bucket-name>",
    "access_key_id": "<your_aws_access_key_id>",
    "secret_access_key": "<your_aws_secret_access_key>"
}

DEFAULT_MIGRATION_CONFIG = {
    "batch_size": 100,  # Process files in batches
    "max_file_size_mb": 100,  # Skip files larger than this
    "allowed_extensions": ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.gif', '.txt', '.csv'],
    "dry_run": False,  # Set to True to test without actual file operations
    
    # PROOF OF CONCEPT SETTINGS
    "test_single_account": False,  # Set to True to test with just one account
    "test_account_id": None,  # Specific Account ID to test with (if None, uses first account found)
    "test_account_name": None,  # Or specify account name to test with (e.g., "Acme Corp")
    "max_test_files": 5,  # Limit number of files to process during testing
}

# Try to import from config.py, fall back to defaults
try:
    from config import SALESFORCE_CONFIG, AWS_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    SALESFORCE_CONFIG = DEFAULT_SALESFORCE_CONFIG
    AWS_CONFIG = DEFAULT_AWS_CONFIG
    MIGRATION_CONFIG = DEFAULT_MIGRATION_CONFIG
    print("⚠ Using default configuration. Copy config_template.py to config.py for custom settings.")

# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging() -> logging.Logger:
    """Set up logging configuration."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"salesforce_migration_{timestamp}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger


# =============================================================================
# SALESFORCE OPERATIONS
# =============================================================================

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
            
            self.logger.info("Successfully authenticated with Salesforce")
            return True
            
        except SalesforceError as e:
            self.logger.error(f"Salesforce authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during Salesforce authentication: {e}")
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
                # Get all accounts with DocListEntry__c records
                self.logger.info("Getting all accounts with DocListEntry__c records...")
                accounts_query = """
                    SELECT DISTINCT Account__c, Account__r.Name
                    FROM DocListEntry__c
                    WHERE Account__c != NULL
                    AND IsDeleted = FALSE
                    AND Document__c != NULL
                    ORDER BY Account__r.Name
                    LIMIT 200
                """
                
                accounts_result = self.sf.query_all(accounts_query)
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
                            'type_current': record['Type_Current__c'],
                            'type_original': record['Type_Original__c'],
                            'doc_type': record['DocType__c'],
                            'parent_folder_id': record.get('Parent_Folder__c'),
                            'identifier': record['Identifier__c'],
                            'client_name': record.get('ClientName__c'),
                            'applicable_year': record.get('ApplicableYear__c'),
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
    
    def get_folder_structure(self, account_id: str) -> Dict[str, Dict]:
        """Get folder structure for an account."""
        try:
            folders_query = f"""
                SELECT Id, Name, Parent_Folder__c, Identifier__c, ApplicableYear__c
                FROM DocListEntry__c
                WHERE Account__c = '{account_id}'
                AND IsDeleted = FALSE
                AND Type_Current__c = 'Folder'
                ORDER BY Name
            """
            
            result = self.sf.query_all(folders_query)
            folders = {}
            
            for record in result['records']:
                folders[record['Id']] = {
                    'name': record['Name'],
                    'parent_folder_id': record.get('Parent_Folder__c'),
                    'identifier': record['Identifier__c'],
                    'year': record.get('ApplicableYear__c')
                }
            
            return folders
            
        except Exception as e:
            self.logger.error(f"Error getting folder structure: {e}")
            return {}
    
    def update_doclistentry_url(self, doclistentry_id: str, new_s3_url: str) -> bool:
        """Update the Document__c URL in DocListEntry__c record."""
        try:
            update_data = {
                'Document__c': new_s3_url
            }
            
            result = self.sf.DocListEntry__c.update(doclistentry_id, update_data)
            
            if result == 204:  # Success response for update
                self.logger.info(f"Successfully updated DocListEntry__c URL: {doclistentry_id}")
                return True
            else:
                self.logger.error(f"Failed to update DocListEntry__c URL: {result}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error updating DocListEntry__c URL: {e}")
            return False


# =============================================================================
# AWS S3 OPERATIONS
# =============================================================================

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
                # Fall back to default credential chain (AWS CLI, environment variables, IAM roles)
                self.s3_client = boto3.client('s3', region_name=self.config['region'])
                self.logger.info("Using default AWS credential chain")
            
            # Test connection by listing buckets
            self.s3_client.list_buckets()
            
            self.logger.info("Successfully authenticated with AWS S3")
            return True
            
        except NoCredentialsError:
            self.logger.error("AWS credentials not found. Please configure your credentials in config.py or use AWS CLI.")
            return False
        except ClientError as e:
            self.logger.error(f"AWS S3 authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error during S3 authentication: {e}")
            return False
    
    def create_bucket_if_not_exists(self) -> bool:
        """Create S3 bucket if it doesn't exist."""
        try:
            bucket_name = self.config['bucket_name']
            
            # Check if bucket exists
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                self.logger.info(f"S3 bucket '{bucket_name}' already exists")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    # Bucket doesn't exist, create it
                    if self.config['region'] == 'us-east-1':
                        # us-east-1 doesn't require location constraint
                        self.s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.config['region']}
                        )
                    
                    self.logger.info(f"Created S3 bucket: {bucket_name}")
                    return True
                else:
                    self.logger.error(f"Error checking bucket existence: {e}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error creating S3 bucket: {e}")
            return False
    
    def download_from_external_s3(self, s3_url: str) -> Optional[bytes]:
        """Download file from external S3 bucket using public URL."""
        try:
            self.logger.info(f"Downloading from external S3: {s3_url}")
            
            # Download using requests (public URL)
            response = requests.get(s3_url, timeout=60)
            
            if response.status_code == 200:
                self.logger.info(f"Successfully downloaded file ({len(response.content)} bytes)")
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
            self.logger.info(f"Successfully uploaded file to S3: {s3_key}")
            return s3_url
            
        except ClientError as e:
            self.logger.error(f"Error uploading file to S3: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error uploading to S3: {e}")
            return None


# =============================================================================
# MIGRATION ORCHESTRATOR
# =============================================================================

class MigrationOrchestrator:
    """Orchestrates the entire migration process."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.sf_manager = SalesforceManager(SALESFORCE_CONFIG, logger)
        self.s3_manager = S3Manager(AWS_CONFIG, logger)
        self.migration_stats = {
            'total_files': 0,
            'successful_migrations': 0,
            'failed_migrations': 0,
            'skipped_files': 0,
            'total_size_mb': 0
        }
    
    def initialize(self) -> bool:
        """Initialize all connections and resources."""
        self.logger.info("Initializing migration process...")
        
        # Authenticate with Salesforce
        if not self.sf_manager.authenticate():
            self.logger.error("Failed to authenticate with Salesforce")
            return False
        
        # Authenticate with AWS S3
        if not self.s3_manager.authenticate():
            self.logger.error("Failed to authenticate with AWS S3")
            return False
        
        # Create S3 bucket if needed
        if not self.s3_manager.create_bucket_if_not_exists():
            self.logger.error("Failed to create/verify S3 bucket")
            return False
        
        self.logger.info("Initialization completed successfully")
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
        if file_ext and file_ext not in MIGRATION_CONFIG['allowed_extensions']:
            return False, f"File extension not allowed: {file_ext}"
        
        return True, "OK"
    
    def generate_s3_key(self, file_info: Dict, folders: Dict[str, Dict]) -> str:
        """Generate S3 key following the required structure with folder hierarchy."""
        account_id = file_info['account_id']
        filename = file_info['name']
        
        # Clean filename for S3
        safe_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '.')).strip()
        
        # Build folder path from parent hierarchy
        folder_path = []
        current_folder_id = file_info.get('parent_folder_id')
        
        # Traverse up the folder hierarchy
        while current_folder_id and current_folder_id in folders:
            folder_info = folders[current_folder_id]
            folder_name = "".join(c for c in folder_info['name'] if c.isalnum() or c in (' ', '-', '_')).strip()
            folder_path.insert(0, folder_name)  # Insert at beginning to maintain hierarchy
            current_folder_id = folder_info.get('parent_folder_id')
        
        # Use account name as base folder name (sanitized)
        base_folder_name = "".join(c for c in file_info['account_name'] if c.isalnum() or c in (' ', '-', '_')).strip()
        
        # Build S3 key with folder hierarchy
        if folder_path:
            folder_structure = '/'.join(folder_path)
            s3_key = f"uploads/{account_id}/{base_folder_name}/{folder_structure}/{safe_filename}"
        else:
            s3_key = f"uploads/{account_id}/{base_folder_name}/{safe_filename}"
        
        return s3_key
    
    def migrate_file(self, file_info: Dict, folders: Dict[str, Dict]) -> bool:
        """Migrate a single file from external S3 to our S3."""
        try:
            filename = file_info['name']
            doclistentry_id = file_info['doclistentry_id']
            account_id = file_info['account_id']
            external_s3_url = file_info['document_url']
            
            self.logger.info(f"Processing file: {filename} (Account: {file_info['account_name']})")
            
            # Check if file should be processed
            should_process, reason = self.should_process_file(file_info)
            if not should_process:
                self.logger.warning(f"Skipping file {filename}: {reason}")
                self.migration_stats['skipped_files'] += 1
                return False
            
            # Generate S3 key with folder structure
            s3_key = self.generate_s3_key(file_info, folders)
            
            if not MIGRATION_CONFIG['dry_run']:
                # Download file from external S3
                self.logger.info(f"Downloading file from external S3: {filename}")
                file_content = self.s3_manager.download_from_external_s3(external_s3_url)
                
                if not file_content:
                    self.logger.error(f"Failed to download file from external S3: {filename}")
                    self.migration_stats['failed_migrations'] += 1
                    return False
                
                # Upload to our S3
                self.logger.info(f"Uploading file to our S3: {s3_key}")
                new_s3_url = self.s3_manager.upload_file(file_content, s3_key)
                
                if not new_s3_url:
                    self.logger.error(f"Failed to upload file to our S3: {filename}")
                    self.migration_stats['failed_migrations'] += 1
                    return False
                
                # Update DocListEntry__c URL in Salesforce
                self.logger.info(f"Updating DocListEntry__c URL in Salesforce: {filename}")
                update_success = self.sf_manager.update_doclistentry_url(doclistentry_id, new_s3_url)
                
                if not update_success:
                    self.logger.error(f"Failed to update DocListEntry__c URL in Salesforce: {filename}")
                    self.migration_stats['failed_migrations'] += 1
                    return False
                
                self.migration_stats['total_size_mb'] += len(file_content) / (1024 * 1024)
            else:
                # Enhanced dry run logging
                bucket_name = AWS_CONFIG['bucket_name']
                new_s3_url = f"https://{bucket_name}.s3.{AWS_CONFIG['region']}.amazonaws.com/{s3_key}"
                
                self.logger.info("=" * 50)
                self.logger.info("🔍 DRY RUN - What would happen:")
                self.logger.info(f"  📁 File: {filename}")
                self.logger.info(f"  🏢 Account: {file_info['account_name']} ({account_id})")
                self.logger.info(f"  📂 Folder Path: {s3_key}")
                self.logger.info(f"  ⬇️  Would download from: {external_s3_url}")
                self.logger.info(f"  ⬆️  Would upload to: {new_s3_url}")
                self.logger.info(f"  🔗 Would update DocListEntry__c.Document__c: {doclistentry_id}")
                self.logger.info(f"  📊 Current URL: {external_s3_url}")
                self.logger.info(f"  📊 New URL: {new_s3_url}")
                self.logger.info("=" * 50)
            
            # Update statistics
            self.migration_stats['successful_migrations'] += 1
            
            self.logger.info(f"Successfully migrated file: {filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error migrating file {filename}: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self.migration_stats['failed_migrations'] += 1
            return False
    
    def run_migration(self) -> bool:
        """Run the complete migration process."""
        try:
            self.logger.info("Starting DocListEntry__c S3 migration process...")
            
            # Check if we're in test mode
            if MIGRATION_CONFIG.get('test_single_account', False):
                self.logger.info("🧪 RUNNING IN TEST MODE - Single Account Only")
                test_account_id = MIGRATION_CONFIG.get('test_account_id')
                test_account_name = MIGRATION_CONFIG.get('test_account_name')
                
                # Get files for testing
                files_to_migrate = self.sf_manager.get_doclistentry_files(test_account_id, test_account_name)
                
                # If no specific account was provided, use the first account found
                if not test_account_id and not test_account_name and files_to_migrate:
                    first_account_id = files_to_migrate[0]['account_id']
                    first_account_name = files_to_migrate[0]['account_name']
                    self.logger.info(f"No specific account specified, using first account found: {first_account_name} ({first_account_id})")
                    
                    # Filter files to just this account
                    files_to_migrate = [f for f in files_to_migrate if f['account_id'] == first_account_id]
                
                # Limit number of files for testing
                max_test_files = MIGRATION_CONFIG.get('max_test_files', 5)
                if len(files_to_migrate) > max_test_files:
                    self.logger.info(f"Limiting to {max_test_files} files for testing")
                    files_to_migrate = files_to_migrate[:max_test_files]
                    
            else:
                # Get all files to migrate
                files_to_migrate = self.sf_manager.get_doclistentry_files()
            
            if not files_to_migrate:
                self.logger.warning("No DocListEntry__c files found to migrate")
                return True
            
            self.migration_stats['total_files'] = len(files_to_migrate)
            self.logger.info(f"Found {len(files_to_migrate)} DocListEntry__c files to process")
            
            # Show account summary
            accounts = {}
            for file_info in files_to_migrate:
                account_id = file_info['account_id']
                account_name = file_info['account_name']
                if account_id not in accounts:
                    accounts[account_id] = {'name': account_name, 'file_count': 0}
                accounts[account_id]['file_count'] += 1
            
            self.logger.info(f"Files will be processed for {len(accounts)} account(s):")
            for account_id, info in accounts.items():
                self.logger.info(f"  - {info['name']} ({account_id}): {info['file_count']} files")
            
            # Get folder structures for all accounts
            all_folders = {}
            for account_id in accounts.keys():
                folders = self.sf_manager.get_folder_structure(account_id)
                all_folders[account_id] = folders
                self.logger.info(f"Found {len(folders)} folders for account {accounts[account_id]['name']}")
            
            # Process files in batches
            batch_size = MIGRATION_CONFIG['batch_size']
            for i in range(0, len(files_to_migrate), batch_size):
                batch = files_to_migrate[i:i + batch_size]
                self.logger.info(f"Processing batch {i//batch_size + 1}/{(len(files_to_migrate) + batch_size - 1)//batch_size}")
                
                for file_info in batch:
                    account_id = file_info['account_id']
                    folders = all_folders.get(account_id, {})
                    self.migrate_file(file_info, folders)
            
            # Print final statistics
            self.print_migration_summary()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error during migration process: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return False
    
    def print_migration_summary(self):
        """Print migration statistics."""
        stats = self.migration_stats
        
        self.logger.info("=" * 60)
        self.logger.info("MIGRATION SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files processed: {stats['total_files']}")
        self.logger.info(f"Successful migrations: {stats['successful_migrations']}")
        self.logger.info(f"Failed migrations: {stats['failed_migrations']}")
        self.logger.info(f"Skipped files: {stats['skipped_files']}")
        self.logger.info(f"Total data migrated: {stats['total_size_mb']:.2f} MB")
        
        if stats['total_files'] > 0:
            success_rate = (stats['successful_migrations'] / stats['total_files']) * 100
            self.logger.info(f"Success rate: {success_rate:.1f}%")
        
        self.logger.info("=" * 60)
        
        # Additional guidance based on mode
        if MIGRATION_CONFIG.get('dry_run', False):
            self.logger.info("🧪 DRY RUN COMPLETED")
            self.logger.info("To perform the actual migration:")
            self.logger.info("1. Set 'dry_run': False in your config.py")
            self.logger.info("2. Run the script again")
            self.logger.info("=" * 60)
        
        if MIGRATION_CONFIG.get('test_single_account', False):
            self.logger.info("🔍 TEST MODE COMPLETED")
            self.logger.info("To migrate all accounts:")
            self.logger.info("1. Set 'test_single_account': False in your config.py")
            self.logger.info("2. Consider increasing 'max_file_size_mb' if needed")
            self.logger.info("3. Run the script again")
            self.logger.info("=" * 60)


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    """Main execution function."""
    print("Salesforce DocListEntry__c S3 Migration Script")
    print("=" * 50)
    
    # Show current mode
    if MIGRATION_CONFIG.get('dry_run', False):
        print("🧪 DRY RUN MODE - No files will actually be moved")
        print("=" * 50)
    
    if MIGRATION_CONFIG.get('test_single_account', False):
        print("🔍 TEST MODE - Single Account Only")
        test_account_id = MIGRATION_CONFIG.get('test_account_id')
        test_account_name = MIGRATION_CONFIG.get('test_account_name')
        max_files = MIGRATION_CONFIG.get('max_test_files', 5)
        
        if test_account_id:
            print(f"   Target Account ID: {test_account_id}")
        elif test_account_name:
            print(f"   Target Account Name: {test_account_name}")
        else:
            print("   Will use first account found")
        
        print(f"   Max files to process: {max_files}")
        print("=" * 50)
    
    # Setup logging
    logger = setup_logging()
    
    # Check configuration
    if SALESFORCE_CONFIG['password'] == '<insert_password>':
        logger.error("Please update the Salesforce password in the configuration")
        return False
    
    if SALESFORCE_CONFIG['security_token'] == '<insert_security_token>':
        logger.error("Please update the Salesforce security token in the configuration")
        return False
    
    if AWS_CONFIG['bucket_name'] == '<new-s3-bucket-name>':
        logger.error("Please update the S3 bucket name in the configuration")
        return False
    
    # Initialize and run migration
    try:
        orchestrator = MigrationOrchestrator(logger)
        
        if not orchestrator.initialize():
            logger.error("Failed to initialize migration process")
            return False
        
        success = orchestrator.run_migration()
        
        if success:
            logger.info("Migration process completed successfully!")
            return True
        else:
            logger.error("Migration process failed!")
            return False
            
    except KeyboardInterrupt:
        logger.info("Migration process interrupted by user")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 