#!/usr/bin/env python3
"""
Migration Rollback Tool
======================

Emergency rollback tool to restore original Salesforce URLs if something
goes wrong during Phase 2 migration.

Features:
- Restore original external S3 URLs in Salesforce
- Uses rollback data files or database records
- Batch processing for performance
- Comprehensive logging and verification

⚠️ WARNING: Use only in emergency situations!

Usage:
python rollback_migration.py --rollback-file rollback_data_20241201_143022.json
python rollback_migration.py --from-database  # Use database records
"""

import sys
import argparse
import json
import logging
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

from migration_db import MigrationDB

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


class MigrationRollback:
    """Emergency rollback tool for migration."""
    
    def __init__(self, dry_run: bool = True):
        """Initialize rollback tool."""
        self.dry_run = dry_run
        self.logger = self._setup_logging()
        self.sf = None
        
        # Statistics
        self.stats = {
            'total_records': 0,
            'successful_rollbacks': 0,
            'failed_rollbacks': 0,
            'skipped_records': 0
        }
    
    def _setup_logging(self) -> logging.Logger:
        """Set up logging configuration."""
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode = "dryrun" if self.dry_run else "execute"
        log_file = log_dir / f"rollback_{mode}_{timestamp}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        logger = logging.getLogger(__name__)
        logger.info(f"Rollback logging initialized. Log file: {log_file}")
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
    
    def load_rollback_data_from_file(self, rollback_file: str) -> List[Dict]:
        """Load rollback data from JSON file."""
        try:
            self.logger.info(f"Loading rollback data from {rollback_file}")
            
            rollback_path = Path(rollback_file)
            if not rollback_path.exists():
                raise FileNotFoundError(f"Rollback file not found: {rollback_file}")
            
            with open(rollback_path, 'r') as f:
                data = json.load(f)
            
            records = data.get('records', [])
            self.logger.info(f"Loaded {len(records)} rollback records from file")
            
            return records
            
        except Exception as e:
            self.logger.error(f"Failed to load rollback data from file: {e}")
            raise
    
    def load_rollback_data_from_database(self) -> List[Dict]:
        """Load rollback data from migration database."""
        try:
            self.logger.info("Loading rollback data from database")
            
            with MigrationDB() as db:
                # Get all files that have been fully migrated (salesforce_updated = 1)
                migrated_files = db.conn.execute('''
                    SELECT doclist_entry_id, original_url
                    FROM file_migrations
                    WHERE salesforce_updated = 1
                    ORDER BY updated_date DESC
                ''').fetchall()
                
                records = []
                for file_record in migrated_files:
                    records.append({
                        'Id': file_record['doclist_entry_id'],
                        'original_url': file_record['original_url']
                    })
                
                self.logger.info(f"Loaded {len(records)} rollback records from database")
                return records
                
        except Exception as e:
            self.logger.error(f"Failed to load rollback data from database: {e}")
            raise
    
    def verify_rollback_data(self, records: List[Dict]) -> List[Dict]:
        """Verify rollback data and filter valid records."""
        try:
            self.logger.info(f"Verifying {len(records)} rollback records")
            
            valid_records = []
            invalid_count = 0
            
            for record in records:
                # Check required fields
                if not record.get('Id') or not record.get('original_url'):
                    self.logger.warning(f"Invalid rollback record: missing Id or original_url")
                    invalid_count += 1
                    continue
                
                # Validate Salesforce ID format (15 or 18 characters)
                sf_id = record['Id']
                if len(sf_id) not in [15, 18]:
                    self.logger.warning(f"Invalid Salesforce ID format: {sf_id}")
                    invalid_count += 1
                    continue
                
                # Validate URL format
                original_url = record['original_url']
                if not original_url.startswith('http'):
                    self.logger.warning(f"Invalid URL format: {original_url}")
                    invalid_count += 1
                    continue
                
                valid_records.append(record)
            
            self.logger.info(f"Verification complete: {len(valid_records)} valid, {invalid_count} invalid")
            return valid_records
            
        except Exception as e:
            self.logger.error(f"Failed to verify rollback data: {e}")
            raise
    
    def get_current_salesforce_data(self, record_ids: List[str]) -> Dict[str, Dict]:
        """Get current Salesforce data for comparison."""
        try:
            self.logger.info(f"Fetching current Salesforce data for {len(record_ids)} records")
            
            # Split into batches to avoid query limits
            batch_size = 200
            all_records = {}
            
            for i in range(0, len(record_ids), batch_size):
                batch_ids = record_ids[i:i + batch_size]
                ids_string = "','".join(batch_ids)
                
                query = f"""
                    SELECT Id, Document__c 
                    FROM DocListEntry__c 
                    WHERE Id IN ('{ids_string}')
                """
                
                result = self.sf.query(query)
                
                for record in result['records']:
                    all_records[record['Id']] = record
            
            self.logger.info(f"Retrieved {len(all_records)} current Salesforce records")
            return all_records
            
        except SalesforceError as e:
            self.logger.error(f"Failed to query current Salesforce data: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error querying Salesforce: {e}")
            raise
    
    def perform_rollback(self, rollback_records: List[Dict]) -> bool:
        """Perform the actual rollback operation."""
        try:
            self.logger.info(f"Starting rollback for {len(rollback_records)} records")
            
            # Get current Salesforce data for comparison
            record_ids = [r['Id'] for r in rollback_records]
            current_sf_data = self.get_current_salesforce_data(record_ids)
            
            # Process records in batches
            batch_size = 200  # Salesforce bulk API limit
            total_batches = (len(rollback_records) + batch_size - 1) // batch_size
            
            for batch_num in range(total_batches):
                start_idx = batch_num * batch_size
                end_idx = min(start_idx + batch_size, len(rollback_records))
                batch = rollback_records[start_idx:end_idx]
                
                self.logger.info(f"Processing rollback batch {batch_num + 1}/{total_batches} ({len(batch)} records)")
                
                # Prepare batch update data
                updates = []
                batch_stats = {'processed': 0, 'skipped': 0}
                
                for record in batch:
                    record_id = record['Id']
                    original_url = record['original_url']
                    
                    # Check if record exists in current Salesforce data
                    current_record = current_sf_data.get(record_id)
                    if not current_record:
                        self.logger.warning(f"Record not found in Salesforce: {record_id}")
                        batch_stats['skipped'] += 1
                        continue
                    
                    current_url = current_record.get('Document__c')
                    
                    # Check if rollback is needed
                    if current_url == original_url:
                        self.logger.debug(f"Record already has original URL, skipping: {record_id}")
                        batch_stats['skipped'] += 1
                        continue
                    
                    # Add to updates
                    updates.append({
                        'Id': record_id,
                        'Document__c': original_url
                    })
                    batch_stats['processed'] += 1
                    
                    if not self.dry_run:
                        self.logger.info(f"Rolling back {record_id}")
                        self.logger.info(f"  From: {current_url}")
                        self.logger.info(f"  To:   {original_url}")
                    else:
                        self.logger.info(f"[DRY RUN] Would rollback {record_id}")
                
                # Execute batch update if not dry run
                if updates and not self.dry_run:
                    try:
                        results = self.sf.bulk.DocListEntry__c.update(updates)
                        
                        # Process results
                        for i, result in enumerate(results):
                            if result['success']:
                                self.stats['successful_rollbacks'] += 1
                            else:
                                self.logger.error(f"Failed to rollback {updates[i]['Id']}: {result['errors']}")
                                self.stats['failed_rollbacks'] += 1
                    
                    except Exception as e:
                        self.logger.error(f"Batch rollback failed: {e}")
                        self.stats['failed_rollbacks'] += len(updates)
                        continue
                
                elif updates:
                    # Dry run - count as successful
                    self.stats['successful_rollbacks'] += len(updates)
                
                self.stats['skipped_records'] += batch_stats['skipped']
                self.stats['total_records'] += batch_stats['processed'] + batch_stats['skipped']
                
                # Progress update
                progress = (batch_num + 1) / total_batches * 100
                self.logger.info(f"Rollback progress: {progress:.1f}%")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Rollback operation failed: {e}")
            return False
    
    def update_database_after_rollback(self) -> bool:
        """Update migration database to reflect rollback."""
        if self.dry_run:
            return True
        
        try:
            self.logger.info("Updating migration database after rollback")
            
            with MigrationDB() as db:
                # Mark all fully migrated files as backup-only
                cursor = db.conn.execute('''
                    UPDATE file_migrations 
                    SET salesforce_updated = 0, migration_phase = 1, updated_date = ?
                    WHERE salesforce_updated = 1
                ''', (datetime.now().isoformat(),))
                
                updated_count = cursor.rowcount
                db.conn.commit()
                
                self.logger.info(f"Updated {updated_count} database records to backup-only status")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to update database after rollback: {e}")
            return False
    
    def run(self, rollback_source: str, rollback_file: str = None):
        """Execute the rollback operation."""
        try:
            # Print banner
            mode = "DRY RUN" if self.dry_run else "LIVE EXECUTION"
            self.logger.info("=" * 60)
            self.logger.info(f"MIGRATION ROLLBACK - {mode}")
            self.logger.info("=" * 60)
            
            if self.dry_run:
                self.logger.info("🧪 DRY RUN MODE - No changes will be made")
            else:
                self.logger.info("⚠️  LIVE MODE - Salesforce will be modified!")
                self.logger.info("⚠️  Original external S3 URLs will be restored")
            
            self.logger.info("=" * 60)
            
            # Authenticate with Salesforce
            if not self.authenticate_salesforce():
                raise Exception("Salesforce authentication failed")
            
            # Load rollback data
            if rollback_source == 'file':
                if not rollback_file:
                    raise Exception("Rollback file path required when using --rollback-file")
                rollback_records = self.load_rollback_data_from_file(rollback_file)
            elif rollback_source == 'database':
                rollback_records = self.load_rollback_data_from_database()
            else:
                raise Exception("Invalid rollback source specified")
            
            if not rollback_records:
                self.logger.info("No rollback records found. Nothing to rollback.")
                return
            
            # Verify rollback data
            valid_records = self.verify_rollback_data(rollback_records)
            
            if not valid_records:
                self.logger.error("No valid rollback records found.")
                return
            
            # Perform rollback
            success = self.perform_rollback(valid_records)
            
            if success and not self.dry_run:
                # Update database
                self.update_database_after_rollback()
            
            # Print final statistics
            self._print_final_stats()
            
        except Exception as e:
            error_msg = f"Rollback failed: {str(e)}"
            self.logger.error(error_msg)
            self.logger.error(traceback.format_exc())
            raise
    
    def _print_final_stats(self):
        """Print final rollback statistics."""
        mode = "DRY RUN" if self.dry_run else "LIVE"
        
        self.logger.info("=" * 60)
        self.logger.info(f"ROLLBACK SUMMARY ({mode})")
        self.logger.info("=" * 60)
        self.logger.info(f"Total records processed: {self.stats['total_records']}")
        self.logger.info(f"Successful rollbacks:    {self.stats['successful_rollbacks']}")
        self.logger.info(f"Failed rollbacks:        {self.stats['failed_rollbacks']}")
        self.logger.info(f"Skipped records:         {self.stats['skipped_records']}")
        
        if self.stats['total_records'] > 0:
            success_rate = (self.stats['successful_rollbacks'] / self.stats['total_records']) * 100
            self.logger.info(f"Success rate:            {success_rate:.1f}%")
        
        if not self.dry_run and self.stats['successful_rollbacks'] > 0:
            self.logger.info("=" * 60)
            self.logger.info("✅ ROLLBACK COMPLETED")
            self.logger.info("✅ Users are back to using external S3 files")
            self.logger.info("✅ Your S3 backup files remain intact")
        elif self.dry_run:
            self.logger.info("=" * 60)
            self.logger.info("🧪 DRY RUN COMPLETED")
            self.logger.info("🧪 Use --execute to perform actual rollback")
        
        self.logger.info("=" * 60)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Emergency migration rollback tool")
    parser.add_argument(
        '--rollback-file', 
        metavar='FILE',
        help='Path to rollback data JSON file'
    )
    parser.add_argument(
        '--from-database',
        action='store_true',
        help='Use rollback data from migration database'
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Test mode - no changes will be made (default)'
    )
    parser.add_argument(
        '--execute', 
        action='store_true', 
        help='Execute the rollback (modifies Salesforce)'
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.rollback_file and not args.from_database:
        print("❌ Must specify either --rollback-file or --from-database")
        sys.exit(1)
    
    if args.rollback_file and args.from_database:
        print("❌ Cannot specify both --rollback-file and --from-database")
        sys.exit(1)
    
    # Determine execution mode
    if not args.dry_run and not args.execute:
        print("No execution mode specified. Defaulting to --dry-run")
        print("Use --execute to perform actual rollback")
        dry_run = True
    elif args.execute:
        dry_run = False
        # Confirmation for live execution
        print("\n⚠️  WARNING: This will modify Salesforce production data!")
        print("⚠️  This will restore original external S3 URLs!")
        confirm = input("Type 'ROLLBACK' to proceed: ")
        if confirm != 'ROLLBACK':
            print("Rollback cancelled.")
            sys.exit(0)
    else:
        dry_run = True
    
    # Determine rollback source
    rollback_source = 'file' if args.rollback_file else 'database'
    
    try:
        rollback = MigrationRollback(dry_run=dry_run)
        rollback.run(rollback_source, args.rollback_file)
        
    except KeyboardInterrupt:
        print("\n⚠ Rollback interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Rollback failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()