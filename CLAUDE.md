# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Salesforce to S3 file migration system designed to migrate files from Trackland's managed S3 storage to a client-owned S3 bucket. The system supports both single-phase direct migration and a two-phase approach for safer handling of 1M+ files. It integrates with Salesforce's DocListEntry__c custom objects (from the Trackland Document Manager package) and provides comprehensive tracking and rollback capabilities.

## Architecture

### Core Components

#### Migration Scripts
- **Two-Phase System** (`backup_only_migration.py`, `full_migration.py`): Safer approach for 1M+ files with backup-first strategy
- **Legacy Single-Phase** (`salesforce_s3_migration.py`): Direct migration with immediate Salesforce updates
- **Database Tracking** (`migration_db.py`): SQLite-based tracking system for large-scale migrations

#### Management Tools  
- **Status Monitor** (`migration_status.py`): Comprehensive migration tracking and statistics
- **Rollback Tool** (`rollback_migration.py`): Emergency recovery system for failed migrations
- **Configuration System** (`config_template.py` → `config.py`): Template-based configuration with sensitive data protection

#### Analysis Tools
- **Pre-Migration Analysis** (`migration_analysis.py`, `list_accounts.py`): Account discovery and scope analysis
- **Debug Scripts** (`debug_*.py`): Specialized debugging tools for different aspects of the system

### Data Flow

#### Two-Phase Migration (Recommended for 1M+ files)
**Phase 1 - Backup Only:**
1. **Discovery**: Query DocListEntry__c records from Salesforce
2. **Download**: Fetch files from external S3 bucket (trackland-doc-storage)
3. **Upload**: Transfer files to client-owned S3 bucket with organized structure
4. **Track**: Record metadata in SQLite database (no Salesforce changes)
5. **Repeat**: Support incremental backups for new files

**Phase 2 - Full Migration:**
1. **Validate**: Ensure backup data exists from Phase 1
2. **Identify**: Find new files added since last backup
3. **Copy**: Download/upload only new files (use existing backups)
4. **Update**: Modify DocListEntry__c.Document__c URLs to point to your S3
5. **Verify**: Validate migration and provide rollback data

#### Legacy Single-Phase Migration
1. **Discovery**: Query DocListEntry__c records from Salesforce
2. **Download**: Fetch files from external S3 bucket  
3. **Upload**: Transfer files to client-owned S3 bucket
4. **Update**: Modify DocListEntry__c.Document__c URLs immediately
5. **Validation**: Verify migration success

### Integration Points

- **Salesforce API**: Uses simple-salesforce library to interact with custom objects (DocListEntry__c, Account)
- **AWS S3**: Boto3 for S3 operations on both source and destination buckets
- **SQLite Database**: Local tracking system for metadata, run history, and error logging (two-phase system)
- **Trackland Package**: Leverages existing "TL - Document Manager" package components for PDF viewing/annotation

## Common Commands

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure credentials (copy template and edit)
cp config_template.py config.py
```

### Two-Phase Migration System

#### Phase 1: Backup Only (Safe - No Salesforce Changes)
```bash
# Full backup (first time)
python backup_only_migration.py --full

# Incremental backup (subsequent runs)  
python backup_only_migration.py --incremental
```

#### Phase 2: Full Migration (When Ready)
```bash
# Test migration (recommended)
python full_migration.py --dry-run

# Execute full migration
python full_migration.py --execute
```

#### Migration Monitoring
```bash
# Status overview
python migration_status.py --overview

# Comprehensive status
python migration_status.py --all

# Account breakdown
python migration_status.py --accounts

# Recent errors
python migration_status.py --recent-errors 10
```

#### Emergency Rollback
```bash
# Rollback from database
python rollback_migration.py --from-database --dry-run
python rollback_migration.py --from-database --execute

# Rollback from file
python rollback_migration.py --rollback-file rollback_data.json --execute
```

### Legacy Single-Phase Migration
```bash
# Original migration script (still available)
python salesforce_s3_migration.py        # Uses config settings
```

### Pre-Migration Analysis
```bash
# List all accounts with files
python list_accounts.py

# Comprehensive migration analysis
python migration_analysis.py

# Debug specific aspects
python debug_files.py                    # File-specific debugging
python debug_comprehensive.py            # Full system debugging
python debug_all_custom_objects.py       # Custom object analysis
```

## Configuration Management

The system uses a template-based configuration approach:

- **`config_template.py`**: Version-controlled template with placeholder values
- **`config.py`**: Local configuration file (git-ignored) with actual credentials
- **Environment Variables**: Alternative authentication method for production deployments

### Key Configuration Sections

- **SALESFORCE_CONFIG**: Salesforce authentication (username, password, security_token, domain)
- **AWS_CONFIG**: AWS credentials and S3 bucket information  
- **MIGRATION_CONFIG**: Migration behavior (batch_size, file filters, dry_run mode, test settings)

## Testing Strategy

The system includes comprehensive testing features:

- **Test Mode**: `test_single_account: True` processes only one account
- **Dry Run**: `dry_run: True` simulates migration without actual file operations
- **File Limits**: `max_test_files: 5` limits files processed during testing
- **Account Targeting**: Specify exact account via `test_account_id` or `test_account_name`

## File Organization

### S3 Structure
Files are organized in S3 with the pattern:
```
uploads/{AccountId}/{AccountName}/{filename}
```

### Debug Scripts
- `debug_files.py`: File-specific debugging and analysis
- `debug_comprehensive.py`: Full system state analysis  
- `debug_external_files.py`: External file source validation
- `debug_hidden_files.py`: Hidden/system file detection
- `debug_bookkeeping_log.py`: Migration audit trail analysis

## Migration Safety

- **Backup Strategy**: Always backup DocListEntry__c records before migration
- **Rollback Plan**: Original URLs can be restored from backup data
- **Validation**: Built-in success/failure reporting with detailed logging
- **Incremental Processing**: Batch processing with configurable batch sizes
- **Error Recovery**: Robust error handling with detailed logging to `logs/` directory

## Dependencies

Core dependencies (see `requirements.txt`):
- `simple-salesforce>=1.12.4`: Salesforce API integration
- `boto3>=1.26.0`: AWS S3 operations  
- `requests>=2.28.0`: HTTP operations for file downloads

## Security Considerations

- **Credential Protection**: `config.py` is git-ignored to prevent credential exposure
- **S3 Permissions**: Requires specific S3 permissions for source/destination bucket operations
- **Salesforce Permissions**: Requires API access and permissions for ContentDocument, ContentVersion, and Account objects
- **Environment Variables**: Preferred method for production credential management