#!/usr/bin/env python3
"""
Chunked Backup Migration Script
==============================

Improved backup migration that processes data in small chunks instead of 
one massive query. Much more reliable for large datasets and provides 
real-time progress updates.

Features:
- Chunked processing (1000 records at a time)
- Real-time progress updates
- Better error handling
- Account-by-account processing option
- Resume capability

Usage:
python backup_chunked_migration.py --full
python backup_chunked_migration.py --by-account  # Process one account at a time
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


class ChunkedBackupMigration:
    """Improved backup migration with chunked processing."""
    
    def __init__(self, by_account: bool = False):
        """Initialize the chunked backup migration."""
        self.by_account = by_account
        self.logger = self._setup_logging()
        self.db = MigrationDB()
        
        # Processing settings
        self.chunk_size = 1000  # Records per chunk
        self.max_retries = 3
        
        # Initialize counters
        self.stats = {
            'processed': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'new_files': 0,
            'updated_files': 0,
            'total_size': 0,
            'accounts_processed': 0,
            'chunks_processed': 0
        }
        
        self.sf = None
        self.s3_client = None
        self.run_id = None
        
    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "by_account" if self.by_account else "chunked"
        log_file = log_dir / f"backup_chunked_{mode}_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Chunked backup migration logging initialized. Log file: {log_file}")
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
            
            if AWS_CONFIG.get("access_key_id") and AWS_CONFIG.get("secret_access_key"):
                self.s3_client = boto3.client(
                    's3',
                    region_name=AWS_CONFIG["region"],
                    aws_access_key_id=AWS_CONFIG["access_key_id"],
                    aws_secret_access_key=AWS_CONFIG["secret_access_key"]
                )
            else:
                self.s3_client = boto3.client('s3', region_name=AWS_CONFIG["region"])
            
            self.s3_client.list_buckets()
            self._ensure_bucket_exists()
            
            self.logger.info("✓ Successfully authenticated with AWS S3")
            return True
            
        except NoCredentialsError:
            self.logger.error("❌ AWS credentials not found. Please run 'aws configure' or set environment variables.")
            return False
        except ClientError as e:
            self.logger.error(f"❌ AWS S3 authentication failed: {e}")
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
                raise
    
    def get_account_list(self) -> List[Dict]:
        """Get list of accounts that have DocListEntry records."""
        try:
            self.logger.info("Getting accounts with DocListEntry records...")
            
            # Use regular query() with LIMIT since aggregate queries don't support query_all()
            query = """
                SELECT Account__c, Account__r.Name, COUNT(Id)
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
                GROUP BY Account__c, Account__r.Name
                ORDER BY COUNT(Id) DESC
                LIMIT 2000
            """
            
            result = self.sf.query(query)
            accounts = result['records']
            
            self.logger.info(f"Found {len(accounts)} accounts with DocListEntry records")
            
            # Log top accounts
            for i, account in enumerate(accounts[:5]):
                count = account.get('expr0', 0)  # Salesforce returns COUNT() as 'expr0'
                account_name = account.get('Account__r', {}).get('Name', 'Unknown Account') if account.get('Account__r') else 'Unknown Account'
                self.logger.info(f"  {i+1}. {account_name}: {count} files")
            
            return accounts
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get account list: {e}")
            raise
    
    def get_records_chunked(self, account_id: str = None) -> List[Dict]:
        """Get DocListEntry records in chunks."""
        try:
            base_query = """
                SELECT Id, Name, Document__c, Account__c, Account__r.Name, 
                       LastModifiedDate, CreatedDate, SystemModstamp, Identifier__c
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
            """
            
            if account_id:
                query = base_query + f" AND Account__c = '{account_id}'"
            else:
                query = base_query
            
            query += f" LIMIT {self.chunk_size}"
            
            all_records = []
            offset = 0
            
            while True:
                if offset > 0:
                    paginated_query = query + f" OFFSET {offset}"
                else:
                    paginated_query = query
                
                self.logger.info(f"Fetching records {offset+1} to {offset+self.chunk_size}...")
                result = self.sf.query(paginated_query)
                
                records = result['records']
                if not records:
                    break
                
                all_records.extend(records)
                self.logger.info(f"✓ Retrieved {len(records)} records (total: {len(all_records)})")
                
                # If we got fewer records than chunk_size, we're done
                if len(records) < self.chunk_size:
                    break
                
                offset += self.chunk_size
                
                # Safety check to prevent infinite loops
                if offset > 100000:  # Max 100k records per account
                    self.logger.warning(f"Reached maximum offset limit for safety")
                    break
            
            return all_records
            
        except Exception as e:
            self.logger.error(f"❌ Failed to get records: {e}")
            raise
    
    def process_by_account(self):
        """Process files account by account."""
        try:
            accounts = self.get_account_list()
            
            # Filter to single account if in test mode
            if MIGRATION_CONFIG.get("test_single_account"):
                test_account_id = MIGRATION_CONFIG.get("test_account_id")
                test_account_name = MIGRATION_CONFIG.get("test_account_name")
                
                if test_account_id:
                    accounts = [acc for acc in accounts if acc['Account__c'] == test_account_id]
                elif test_account_name:
                    # Safely check account name
                    accounts = [acc for acc in accounts if acc.get('Account__r', {}).get('Name', '') == test_account_name]
                else:
                    accounts = accounts[:1]  # Just take first account
                
                self.logger.info(f"🧪 TEST MODE - Processing {len(accounts)} account(s)")
            
            for i, account in enumerate(accounts, 1):
                account_id = account['Account__c']
                account_name = account.get('Account__r', {}).get('Name', 'Unknown Account') if account.get('Account__r') else 'Unknown Account'
                record_count = account.get('expr0', 0)  # COUNT() result
                
                self.logger.info("=" * 60)
                self.logger.info(f"Processing Account {i}/{len(accounts)}: {account_name}")
                self.logger.info(f"Account ID: {account_id}")
                self.logger.info(f"Expected files: {record_count}")
                self.logger.info("=" * 60)
                
                # Get records for this account
                records = self.get_records_chunked(account_id)
                
                if not records:
                    self.logger.warning(f"No records found for account {account_name}")
                    continue
                
                self.logger.info(f"Retrieved {len(records)} records for {account_name}")
                
                # Process files for this account
                self.process_files_batch(records, account_name)
                
                self.stats['accounts_processed'] += 1
                self.logger.info(f"✓ Completed account {account_name} ({self.stats['successful']} successful so far)")
                
                # Update database stats
                self.db.update_run_stats(self.run_id, **self.stats)
            
        except Exception as e:
            self.logger.error(f"❌ Failed to process by account: {e}")
            raise
    
    def process_all_chunked(self):
        """Process all files in chunks using cursor-based pagination."""
        try:
            self.logger.info("Processing all records in chunks...")
            
            # Get total count first
            count_result = self.sf.query("""
                SELECT COUNT() 
                FROM DocListEntry__c 
                WHERE Document__c != NULL 
                AND Account__c != NULL
                AND Type_Current__c = 'Document'
            """)
            total_records = count_result['totalSize']
            
            self.logger.info(f"Total records to process: {total_records:,}")
            
            processed = 0
            last_id = None
            chunk_num = 0
            
            while True:
                chunk_num += 1
                
                # Cursor-based pagination using WHERE Id > last_id
                if last_id:
                    query = f"""
                        SELECT Id, Name, Document__c, Account__c, Account__r.Name, 
                               LastModifiedDate, CreatedDate, Identifier__c
                        FROM DocListEntry__c 
                        WHERE Document__c != NULL 
                        AND Account__c != NULL
                        AND Type_Current__c = 'Document'
                        AND Id > '{last_id}'
                        ORDER BY Id
                        LIMIT {self.chunk_size}
                    """
                else:
                    # First chunk
                    query = f"""
                        SELECT Id, Name, Document__c, Account__c, Account__r.Name, 
                               LastModifiedDate, CreatedDate, Identifier__c
                        FROM DocListEntry__c 
                        WHERE Document__c != NULL 
                        AND Account__c != NULL
                        AND Type_Current__c = 'Document'
                        ORDER BY Id
                        LIMIT {self.chunk_size}
                    """
                
                try:
                    self.logger.info(f"📦 Processing chunk {chunk_num} ({processed+1}-{processed+self.chunk_size} of ~{total_records:,})")
                    result = self.sf.query(query)
                    records = result['records']
                    
                    if not records:
                        self.logger.info("No more records found - processing complete")
                        break
                    
                    self.logger.info(f"✓ Retrieved {len(records)} records")
                    
                    # Process this chunk
                    self.process_files_batch(records)
                    
                    # Update cursor to last ID in this batch
                    last_id = records[-1]['Id']
                    processed += len(records)
                    self.stats['chunks_processed'] += 1
                    
                    # Progress update
                    progress = (processed / total_records) * 100
                    self.logger.info(f"📈 Overall progress: {progress:.1f}% ({processed:,}/{total_records:,})")
                    
                    # Update database stats every 5 chunks to avoid too much DB activity
                    if chunk_num % 5 == 0:
                        self.db.update_run_stats(self.run_id, **self.stats)
                    
                    # If we got fewer records than chunk_size, we're at the end
                    if len(records) < self.chunk_size:
                        self.logger.info("Reached end of records - processing complete")
                        break
                    
                except Exception as e:
                    self.logger.error(f"❌ Error processing chunk {chunk_num}: {e}")
                    # For cursor-based pagination, we can't easily skip, so break
                    self.logger.error("Stopping due to cursor pagination error")
                    break
            
            self.logger.info(f"Processed {processed:,} total records in {chunk_num} chunks")
            
        except Exception as e:
            self.logger.error(f"❌ Failed to process chunked: {e}")
            raise
    
    def process_files_batch(self, records: List[Dict], account_context: str = ""):
        """Process a batch of file records."""
        for i, record in enumerate(records, 1):
            try:
                context = f"{account_context} - " if account_context else ""
                file_name = record.get('Name', record['Id'])
                
                # Log file with extension info for debugging
                if '.' in file_name:
                    file_ext = file_name.split('.')[-1].lower()
                    self.logger.info(f"📄 {context}Processing file {i}/{len(records)}: {file_name} [.{file_ext}]")
                else:
                    self.logger.info(f"📄 {context}Processing file {i}/{len(records)}: {file_name} [no extension]")
                
                success = self.process_single_file(record)
                if success:
                    self.stats['successful'] += 1
                else:
                    self.stats['failed'] += 1
                
                self.stats['processed'] += 1
                
                # Periodic progress update
                if self.stats['processed'] % 10 == 0:
                    success_rate = (self.stats['successful'] / self.stats['processed']) * 100
                    self.logger.info(f"📊 Progress: {self.stats['processed']} processed, {success_rate:.1f}% success rate")
                
            except Exception as e:
                self.logger.error(f"❌ Error processing record {record['Id']}: {e}")
                self.stats['failed'] += 1
                continue
    
    def process_single_file(self, record: Dict) -> bool:
        """Process a single DocListEntry record for backup."""
        doclist_id = record['Id']
        
        try:
            # Extract file information
            original_url = record['Document__c']
            account_id = record['Account__c']
            account_name = record['Account__r']['Name'] if record['Account__r'] else 'Unknown'
            identifier_c = record.get('Identifier__c')  # Get Identifier__c if available
            
            # Log the identifier for debugging
            if identifier_c:
                self.logger.info(f"Found Identifier__c: {identifier_c} for record {doclist_id}")
            else:
                self.logger.info(f"No Identifier__c found for record {doclist_id}")
            
            # Clean account name for file path
            clean_account_name = self._clean_filename(account_name)
            
            # Extract file name from URL
            parsed_url = urlparse(original_url)
            file_name = os.path.basename(parsed_url.path) or f"file_{doclist_id}"
            
            # For backup mode, we backup ALL files - no extension filtering
            # (Extension filtering can be applied later in Phase 2 migration if needed)
            
            # Generate S3 key with organized structure
            s3_key = f"uploads/{account_id}/{clean_account_name}/{file_name}"
            
            # In dry run mode, just log what would happen
            if MIGRATION_CONFIG.get("dry_run"):
                self.logger.info(f"🧪 [DRY RUN] Would backup: {file_name} to {s3_key}")
                return True
            
            # Check if file already exists in S3 for incremental
            if self._file_exists_in_s3(s3_key):
                self.logger.debug(f"File already exists in S3, skipping: {s3_key}")
                self.stats['skipped'] += 1
                return True
            
            # Download file using Trackland API methods
            # Pass the identifier_c to download_file for proper API calls
            content, file_size = self.download_file(original_url, doclist_id, identifier_c)
            
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
            
            self.stats['total_size'] += file_size
            
            self.logger.debug(f"✓ Backed up: {file_name} ({self._format_size(file_size)})")
            return True
            
        except Exception as e:
            error_msg = f"Failed to process {doclist_id}: {str(e)}"
            self.logger.error(error_msg)
            
            # Record error in database
            self.db.record_migration_error(
                self.run_id, doclist_id, 'backup_error', 
                str(e), record.get('Document__c')
            )
            
            return False
    
    def download_file(self, url: str, doclist_entry_id: str = None, identifier_c: str = None) -> Tuple[bytes, int]:
        """Download file using Trackland API pre-signed URL approach."""
        try:
            # Validate that this is a trackland URL
            if 'trackland-doc-storage' not in url:
                self.logger.warning(f"Skipping non-trackland URL: {url}")
                raise Exception(f"Not a trackland-doc-storage URL: {url}")
            
            self.logger.info(f"Attempting download via Trackland API: {url}")
            
            # Determine the proper file identifier for API calls
            # Priority: 1) Identifier__c from record, 2) S3 key from URL
            if identifier_c:
                file_identifier = identifier_c
                self.logger.info(f"Using Identifier__c from record: {file_identifier}")
            else:
                # Fallback to extracting from URL
                # URL format: https://trackland-doc-storage.s3.us-west-2.amazonaws.com/incitetax-pdf-manager/uuid.pdf
                # We need the S3 key: incitetax-pdf-manager/uuid.pdf
                parsed_url = urlparse(url)
                file_identifier = parsed_url.path.lstrip('/')  # Remove leading slash
                
                if not file_identifier:
                    raise Exception(f"Could not extract file identifier from URL: {url}")
                
                self.logger.info(f"Using file identifier from URL: {file_identifier}")
            
            # Method 1: Try Trackland API pre-signed URL generation
            try:
                # Try different actions that might work for reading files
                presigned_url = self._get_trackland_presigned_url(file_identifier, "read")
                if not presigned_url:
                    # Try with different action if "read" doesn't work
                    presigned_url = self._get_trackland_presigned_url(file_identifier, "get-file")
                
                if presigned_url:
                    self.logger.info(f"✓ Got pre-signed URL from Trackland API: {presigned_url[:100]}...")
                    
                    # Download using pre-signed URL
                    response = requests.get(presigned_url, timeout=300, allow_redirects=True)
                    
                    if response.status_code == 200:
                        content = response.content
                        size = len(content)
                        
                        # Basic validation - check if we got actual file content
                        if size > 0 and not response.headers.get('content-type', '').startswith('text/html'):
                            self.logger.info(f"✓ Pre-signed URL download successful ({size} bytes)")
                            
                            # Check file size limits
                            max_size_bytes = MIGRATION_CONFIG.get("max_file_size_mb", 100) * 1024 * 1024
                            if size > max_size_bytes:
                                raise ValueError(f"File size {size} bytes exceeds limit of {max_size_bytes} bytes")
                            
                            return content, size
                        else:
                            self.logger.info("Pre-signed URL returned HTML (likely error page)")
                    else:
                        self.logger.info(f"Pre-signed URL failed with status: {response.status_code}, response: {response.text[:200]}")
                        
            except Exception as presigned_error:
                self.logger.info(f"Trackland API pre-signed URL failed: {presigned_error}")
            
            # Method 2: Try Trackland document versions API
            try:
                content_result = self._try_trackland_document_api(file_identifier)
                if content_result:
                    self.logger.info(f"✓ Trackland document API successful")
                    return content_result
            except Exception as doc_api_error:
                self.logger.info(f"Trackland document API failed: {doc_api_error}")
            
            # Method 3: Try direct access without authentication (fallback)
            try:
                response = requests.get(url, timeout=300, allow_redirects=True)
                
                if response.status_code == 200:
                    content = response.content
                    size = len(content)
                    
                    # Basic validation - check if we got actual file content
                    if size > 0 and not response.headers.get('content-type', '').startswith('text/html'):
                        self.logger.info(f"✓ Direct access successful ({size} bytes)")
                        
                        # Check file size limits
                        max_size_bytes = MIGRATION_CONFIG.get("max_file_size_mb", 100) * 1024 * 1024
                        if size > max_size_bytes:
                            raise ValueError(f"File size {size} bytes exceeds limit of {max_size_bytes} bytes")
                        
                        return content, size
                    else:
                        self.logger.info("Direct access returned HTML (likely error page)")
                        
            except Exception as direct_error:
                self.logger.info(f"Direct access failed: {direct_error}")
            
            # Method 4: Try ContentDocument API if we have doclist_entry_id
            if doclist_entry_id:
                self.logger.info("Attempting ContentDocument API download...")
                try:
                    content_result = self._try_content_document_download(doclist_entry_id)
                    if content_result:
                        self.logger.info(f"✓ ContentDocument API successful")
                        return content_result
                except Exception as cd_error:
                    self.logger.info(f"ContentDocument API failed: {cd_error}")
            
            # All methods failed - provide detailed error info
            self.logger.error(f"❌ All download methods failed for: {url}")
            self.logger.error(f"File identifier: {file_identifier}")
            
            # Try one final diagnostic call to understand the error
            try:
                final_response = requests.get(url, timeout=30)
                error_details = f"Status: {final_response.status_code}"
                if final_response.text:
                    error_details += f", Response: {final_response.text[:300]}"
                self.logger.error(f"Diagnostic info: {error_details}")
            except:
                pass
            
            raise Exception(f"All download methods exhausted. URL may require special credentials or be inaccessible.")
            
        except Exception as e:
            raise Exception(f"Download failed: {e}")
    
    def _get_trackland_presigned_url(self, file_identifier: str, action: str = "read") -> Optional[str]:
        """Generate pre-signed URL using Trackland API - try multiple base URLs."""
        # Try different possible API base URLs since the main org URL returns 404
        potential_base_urls = [
            # Original org URL
            self.sf.sf_instance,
            # Possible Trackland-specific subdomains
            "trackland-api.herokuapp.com",
            "api.trackland.com", 
            f"trackland-{self.sf.sf_instance.split('.')[0].replace('https://', '')}.herokuapp.com",
            # Alternative patterns
            f"api-{self.sf.sf_instance.split('.')[0].replace('https://', '')}.trackland.com"
        ]
        
        for base_url in potential_base_urls:
            try:
                # Ensure URL has proper scheme
                if not base_url.startswith('https://'):
                    org_url = f"https://{base_url}"
                else:
                    org_url = base_url
                    
                if org_url.endswith('.com/'):
                    org_url = org_url.rstrip('/')
                
                # Trackland API endpoint for pre-signed URL generation
                api_url = f"{org_url}/api/generate/presigned-url"
                
                # Prepare request payload based on discovered pattern
                payload = {
                    "identifier": file_identifier,
                    "app": "pdf-editor-sf",  # App identifier from PDF viewer
                    "action": action  # "read" for download, "save-new-version" for upload
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.sf.session_id}",
                    "User-Agent": "simple-salesforce/1.0"
                }
                
                self.logger.info(f"Trying API base URL: {api_url}")
                
                response = requests.post(api_url, json=payload, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    result = response.json()
                    presigned_url = result.get('data', {}).get('url')
                    
                    if presigned_url:
                        self.logger.info(f"✓ Found working API at {org_url}")
                        self.logger.info(f"✓ Got pre-signed URL: {presigned_url[:50]}...")
                        return presigned_url
                    else:
                        self.logger.info(f"No URL in response from {org_url}: {result}")
                elif response.status_code == 404:
                    self.logger.info(f"API not found at {org_url} (404)")
                else:
                    self.logger.info(f"API at {org_url} returned status {response.status_code}: {response.text[:200]}")
                        
            except Exception as e:
                self.logger.info(f"Failed to connect to {base_url}: {e}")
                continue
        
        self.logger.info("No working API base URL found for pre-signed URLs")
        return None
    
    def _try_trackland_document_api(self, file_identifier: str) -> Optional[Tuple[bytes, int]]:
        """Try downloading via Trackland document versions API - try multiple base URLs."""
        # Try different possible API base URLs since the main org URL returns 404
        potential_base_urls = [
            # Original org URL
            self.sf.sf_instance,
            # Possible Trackland-specific subdomains
            "trackland-api.herokuapp.com",
            "api.trackland.com", 
            f"trackland-{self.sf.sf_instance.split('.')[0].replace('https://', '')}.herokuapp.com",
            # Alternative patterns
            f"api-{self.sf.sf_instance.split('.')[0].replace('https://', '')}.trackland.com"
        ]
        
        for base_url in potential_base_urls:
            try:
                # Ensure URL has proper scheme
                if not base_url.startswith('https://'):
                    org_url = f"https://{base_url}"
                else:
                    org_url = base_url
                    
                if org_url.endswith('.com/'):
                    org_url = org_url.rstrip('/')
                
                # Try document versions API endpoint
                api_url = f"{org_url}/api/document/versions/{file_identifier}"
                
                headers = {
                    "Authorization": f"Bearer {self.sf.session_id}",
                    "User-Agent": "simple-salesforce/1.0",
                    "Accept": "application/octet-stream"
                }
                
                self.logger.info(f"Trying document API: {api_url}")
                
                response = requests.get(api_url, headers=headers, timeout=30)
                
                if response.status_code == 200:
                    content = response.content
                    size = len(content)
                    
                    if size > 0:
                        self.logger.info(f"✓ Found working document API at {org_url}")
                        self.logger.info(f"Document API successful ({size} bytes)")
                        return content, size
                elif response.status_code == 404:
                    self.logger.info(f"Document API not found at {org_url} (404)")
                else:
                    self.logger.info(f"Document API at {org_url} returned status {response.status_code}: {response.text[:200]}")
                        
            except Exception as e:
                self.logger.info(f"Failed to connect to {base_url}: {e}")
                continue
        
        self.logger.info("No working document API base URL found")
        return None
    
    def _try_content_document_download(self, doclist_entry_id: str) -> Optional[Tuple[bytes, int]]:
        """Try downloading via ContentDocument API."""
        try:
            # Look for ContentDocumentLinks
            content_query = f"""
                SELECT ContentDocumentId, ContentDocument.LatestPublishedVersionId
                FROM ContentDocumentLink 
                WHERE LinkedEntityId = '{doclist_entry_id}'
                LIMIT 1
            """
            
            content_result = self.sf.query(content_query)
            if content_result['records']:
                version_id = content_result['records'][0]['ContentDocument']['LatestPublishedVersionId']
                
                # Try to download via ContentVersion
                headers = {
                    'Authorization': f'Bearer {self.sf.session_id}',
                    'User-Agent': 'simple-salesforce/1.0'
                }
                version_url = f"{self.sf.base_url}sobjects/ContentVersion/{version_id}/VersionData"
                version_response = requests.get(version_url, headers=headers, timeout=300)
                
                if version_response.status_code == 200:
                    content = version_response.content
                    size = len(content)
                    self.logger.info(f"Downloaded via ContentVersion API ({size} bytes)")
                    return content, size
            
            return None
            
        except Exception as e:
            self.logger.info(f"ContentDocument method failed: {e}")
            return None
    
    def upload_to_s3(self, content: bytes, s3_key: str, file_name: str) -> str:
        """Upload file content to your S3 bucket with memory optimization."""
        try:
            bucket_name = AWS_CONFIG["bucket_name"]
            
            # For large files, use streaming upload to avoid memory issues
            if len(content) > 50 * 1024 * 1024:  # 50MB threshold
                self.logger.debug(f"Using streaming upload for large file: {self._format_size(len(content))}")
                # Use BytesIO for streaming large files
                from io import BytesIO
                file_obj = BytesIO(content)
                
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=file_obj,
                    ContentDisposition=f'attachment; filename="{file_name}"'
                )
            else:
                # Direct upload for smaller files
                self.s3_client.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=content,
                    ContentDisposition=f'attachment; filename="{file_name}"'
                )
            
            s3_url = f"https://{bucket_name}.s3.{AWS_CONFIG['region']}.amazonaws.com/{s3_key}"
            
            # Immediately clear the content from memory to free up space
            del content
            
            return s3_url
            
        except Exception as e:
            raise Exception(f"S3 upload failed: {e}")
    
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
        """Execute the chunked backup migration."""
        try:
            # Print banner
            mode = "BY-ACCOUNT" if self.by_account else "CHUNKED"
            self.logger.info("=" * 60)
            self.logger.info(f"Phase 1: {mode} BACKUP Migration")
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
                'processing_mode': mode.lower()
            }
            
            self.run_id = self.db.start_migration_run('backup_chunked', config_snapshot)
            
            # Authenticate
            if not self.authenticate_salesforce():
                raise Exception("Salesforce authentication failed")
            
            if not self.authenticate_aws():
                raise Exception("AWS authentication failed")
            
            # Process files
            if self.by_account:
                self.process_by_account()
            else:
                self.process_all_chunked()
            
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
        mode = "BY-ACCOUNT" if self.by_account else "CHUNKED"
        
        self.logger.info("=" * 60)
        self.logger.info(f"{mode} BACKUP MIGRATION SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total files processed: {self.stats['processed']}")
        self.logger.info(f"Successfully backed up: {self.stats['successful']}")
        self.logger.info(f"Failed backups: {self.stats['failed']}")
        self.logger.info(f"Skipped files: {self.stats['skipped']}")
        self.logger.info(f"New files: {self.stats['new_files']}")
        self.logger.info(f"Updated files: {self.stats['updated_files']}")
        self.logger.info(f"Total data backed up: {self._format_size(self.stats['total_size'])}")
        
        if self.by_account:
            self.logger.info(f"Accounts processed: {self.stats['accounts_processed']}")
        else:
            self.logger.info(f"Chunks processed: {self.stats['chunks_processed']}")
        
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
    parser = argparse.ArgumentParser(description="Chunked backup-only file migration")
    parser.add_argument(
        '--full', 
        action='store_true', 
        help='Run full backup using chunked processing'
    )
    parser.add_argument(
        '--by-account', 
        action='store_true', 
        help='Process one account at a time (slower but more reliable)'
    )
    
    args = parser.parse_args()
    
    if not args.full and not args.by_account:
        print("Please specify processing mode:")
        print("  --full        Process all records in chunks")
        print("  --by-account  Process one account at a time")
        print()
        print("Examples:")
        print("  python backup_chunked_migration.py --full")
        print("  python backup_chunked_migration.py --by-account")
        sys.exit(1)
    
    try:
        migration = ChunkedBackupMigration(by_account=args.by_account)
        migration.run()
        
    except KeyboardInterrupt:
        print("\n⚠ Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()