# Two-Phase Migration Guide

This guide explains the new two-phase migration approach for safely migrating 1M+ files from external S3 to your own S3 bucket.

## 🎯 Migration Strategy Overview

### **Phase 1: Backup Only** (Safe - No User Impact)
- Downloads files from external S3 → uploads to your S3
- **Leaves Salesforce unchanged** - users keep using original files
- Tracks everything in SQLite database for later use
- Creates complete backup mirror of all files
- Can be run incrementally to catch new files

### **Phase 2: Full Migration** (When Ready)
- Uses backed-up files from Phase 1
- Only copies new files added since last backup
- Updates Salesforce URLs to point to your S3
- **Users switch to your S3** - complete migration

## 📋 Prerequisites

1. **Python 3.7+** and dependencies installed
2. **Salesforce credentials** configured
3. **AWS credentials** configured  
4. **S3 bucket** created for your files
5. **Disk space** for SQLite database (expect ~500MB-2GB for 1M files)

## 🚀 Quick Start

### Step 1: Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Configure credentials (copy template and edit)
cp config_template.py config.py
# Edit config.py with your actual credentials
```

### Step 2: Phase 1 - Backup Only (Safe)
```bash
# Full backup (first time)
python backup_only_migration.py --full

# OR incremental backup (subsequent runs)
python backup_only_migration.py --incremental
```

**What happens:**
- ✅ Downloads all files from external S3
- ✅ Uploads to your S3 with organized structure
- ✅ Tracks everything in SQLite database
- ❌ **Does NOT modify Salesforce**
- ❌ **Users unaffected** - keep using original files

### Step 3: Monitor Progress
```bash
# Check backup status
python migration_status.py --overview

# Detailed statistics  
python migration_status.py --all

# Account breakdown
python migration_status.py --accounts
```

### Step 4: Phase 2 - Full Migration (When Ready)
```bash
# Test first (recommended)
python full_migration.py --dry-run

# Execute when ready
python full_migration.py --execute
```

**What happens:**
- ✅ Uses existing backed-up files (no re-copying)
- ✅ Copies only new files added since last backup
- ✅ Updates Salesforce URLs to your S3
- ✅ **Users switch to your S3 files**

## 📁 File Organization

Your S3 bucket will have this structure:
```
your-s3-bucket/
├── uploads/
│   ├── {AccountId1}/
│   │   ├── {AccountName1}/
│   │   │   ├── file1.pdf
│   │   │   └── file2.docx
│   │   └── ...
│   ├── {AccountId2}/
│   │   ├── {AccountName2}/
│   │   │   └── file3.xlsx
│   │   └── ...
```

## 🗃️ Database Tracking

The system creates `migration_tracking.db` with:
- **file_migrations**: All file metadata and URLs
- **migration_runs**: History of backup/migration runs  
- **migration_errors**: Error tracking and troubleshooting

Key fields in file_migrations:
- `doclist_entry_id`: Salesforce record ID
- `original_url`: External S3 URL
- `your_s3_url`: Your S3 URL  
- `salesforce_updated`: 0 = backup only, 1 = fully migrated
- `backup_timestamp`: When file was backed up

## 📊 Monitoring Commands

### Status Overview
```bash
python migration_status.py                    # Basic overview
python migration_status.py --overview         # Same as above
python migration_status.py --all             # Everything
```

### Detailed Reports
```bash
python migration_status.py --runs            # Recent migration runs
python migration_status.py --accounts        # Top accounts by file count
python migration_status.py --errors          # Error summary
python migration_status.py --recent-errors 20 # Last 20 errors
python migration_status.py --readiness       # Phase 2 readiness check
```

### Export Data
```bash
python migration_status.py --export report.json  # Export detailed report
```

## 🔄 Incremental Workflow

### Ongoing Backup (Recommended)
```bash
# Run weekly/monthly to catch new files
python backup_only_migration.py --incremental

# Check what's new
python migration_status.py --overview
```

### Final Migration When Ready
```bash
# Test the full migration
python full_migration.py --dry-run

# Execute when ready
python full_migration.py --execute
```

## 🆘 Emergency Rollback

If something goes wrong in Phase 2:

```bash
# Rollback using database records
python rollback_migration.py --from-database --dry-run
python rollback_migration.py --from-database --execute

# OR rollback using saved rollback file
python rollback_migration.py --rollback-file rollback_data_20241201_143022.json --execute
```

## ⚡ Performance & Scale

### For 1M+ Files:
- **Database**: SQLite handles 1M+ records efficiently
- **Memory**: ~1-2GB RAM during processing
- **Storage**: ~500MB-2GB for database file
- **Time**: ~24-48 hours for full backup (depends on file sizes)

### Optimization Settings:
```python
# In config.py
MIGRATION_CONFIG = {
    "batch_size": 100,        # Reduce if memory issues
    "max_file_size_mb": 100,  # Skip large files if needed
    "allowed_extensions": ['.pdf', '.doc', '.docx', ...],  # Filter file types
}
```

## 🔧 Advanced Usage

### Test with Single Account
```python
# In config.py
MIGRATION_CONFIG = {
    # ... other settings ...
    "test_single_account": True,
    "test_account_id": "0013D00000AbcDefGHI",  # Specific account
    "max_test_files": 10,  # Limit files for testing
}
```

### Custom S3 Structure
Files are organized as: `uploads/{AccountId}/{CleanAccountName}/{FileName}`

Account names are automatically cleaned for file system compatibility.

## 📝 Logging

All operations are logged to:
- **Console**: Real-time progress
- **Log files**: `logs/backup_migration_*` or `logs/full_migration_*`
- **Database**: Run history and statistics

## ✅ Safety Features

### Phase 1 Safety:
- ✅ No Salesforce changes
- ✅ Users completely unaffected
- ✅ Can run multiple times safely
- ✅ Complete rollback possible by simply not running Phase 2

### Phase 2 Safety:
- ✅ Dry run mode for testing
- ✅ Batch processing with error recovery
- ✅ Rollback data automatically saved
- ✅ Validation checks after migration
- ✅ Emergency rollback tool available

### Error Handling:
- ✅ Individual file failures don't stop migration
- ✅ Comprehensive error logging  
- ✅ Retry capabilities
- ✅ Detailed progress tracking

## 🎯 Best Practices

### Before Phase 1:
1. **Test config**: Run with `test_single_account: True`
2. **Check permissions**: Ensure S3 and Salesforce access
3. **Estimate storage**: Check total file sizes
4. **Set expectations**: Phase 1 can take 24-48 hours for 1M files

### Before Phase 2:
1. **Validate backup**: Run `migration_status.py --readiness`
2. **Test thoroughly**: Use `--dry-run` extensively  
3. **Backup database**: Copy `migration_tracking.db`
4. **Schedule wisely**: Plan for user downtime during URL switch
5. **Communicate**: Inform users about the switch

### During Migration:
1. **Monitor closely**: Check logs and progress
2. **Don't interrupt**: Let batches complete
3. **Address errors**: Check failed files and resolve issues

### After Migration:
1. **Validate**: Check random files work for users
2. **Monitor performance**: Ensure your S3 is performing well
3. **Keep backups**: Don't delete external files immediately
4. **Document**: Save rollback files and run reports

## 🔍 Troubleshooting

### Common Issues:

**"No backup data found"**
- Run Phase 1 backup first: `python backup_only_migration.py --full`

**"AWS credentials not found"**
- Run `aws configure` or set environment variables
- Check `config.py` AWS settings

**"Database locked"**
- Another migration process might be running
- Check for stuck processes: `ps aux | grep python`

**"File download failures"**
- Network issues or invalid URLs
- Check error logs: `python migration_status.py --recent-errors`

**"S3 upload failures"**
- Check S3 permissions and bucket configuration
- Verify AWS credentials have write access

### Getting Help:
1. **Check logs**: `logs/` directory has detailed information
2. **Check database**: Use migration_status.py for insights
3. **Validate config**: Ensure all credentials are correct
4. **Test connectivity**: Try AWS CLI and Salesforce API separately

## 📈 Migration Timeline Example

**Week 1:**
- Setup and configuration
- Test with single account
- Start Phase 1 full backup

**Week 2-3:**
- Monitor Phase 1 progress
- Address any errors
- Setup incremental backup schedule

**Week 4:**
- Phase 1 complete
- Validate backup data
- Plan Phase 2 timing

**Week 5:**
- Extensive Phase 2 dry-run testing
- User communication
- Execute Phase 2

**Week 6:**
- Monitor user experience
- Address any issues
- Complete migration cleanup

---

## 🎉 You're Ready!

This two-phase approach gives you maximum safety and control over your 1M+ file migration. Phase 1 can run safely in the background while users continue their work, and Phase 2 provides a controlled switchover when you're ready.

Start with Phase 1 and take your time - there's no rush once your backup is building!