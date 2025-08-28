# Quick Reference Guide

## 🚀 Essential Commands

### Phase 1: Backup Only (Safe)
```bash
# First time full backup
python backup_only_migration.py --full

# Ongoing incremental backups  
python backup_only_migration.py --incremental

# Check backup progress
python migration_status.py --overview
```

### Phase 2: Full Migration (When Ready)
```bash
# Test migration (safe)
python full_migration.py --dry-run

# Execute migration (live)
python full_migration.py --execute
```

### Emergency Rollback
```bash
# Rollback immediately
python rollback_migration.py --from-database --execute
```

---

## 📊 Status Commands

```bash
# Quick overview
python migration_status.py

# Detailed status
python migration_status.py --all

# Account breakdown
python migration_status.py --accounts

# Recent errors
python migration_status.py --recent-errors 10

# Check readiness for Phase 2
python migration_status.py --readiness

# Export full report
python migration_status.py --export report.json
```

---

## 🔧 Configuration Quick Setup

### 1. Initial Setup
```bash
cp config_template.py config.py
# Edit config.py with your credentials
```

### 2. Test Configuration
```bash
python list_accounts.py
```

### 3. Single Account Test
```python
# In config.py
MIGRATION_CONFIG = {
    "test_single_account": True,
    "test_account_id": "your_test_account_id",
    "max_test_files": 5,
    "dry_run": True
}
```

---

## 🚨 Emergency Procedures

### If Phase 1 Stops
```bash
# Check what happened
python migration_status.py --recent-errors 5

# Resume backup
python backup_only_migration.py --incremental
```

### If Phase 2 Fails
```bash
# Immediate rollback
python rollback_migration.py --from-database --execute

# Verify rollback worked
python migration_status.py --overview
```

### If System Issues
```bash
# Check disk space
df -h .

# Check database
ls -lh migration_tracking.db

# Check logs
tail -50 logs/backup_migration_*.log
```

---

## 📈 Progress Monitoring

### Real-time Monitoring
```bash
# Watch progress every 30 seconds
watch -n 30 "python migration_status.py --overview"

# Monitor logs in real-time
tail -f logs/backup_migration_*.log
```

### Key Metrics to Watch
- **Files processed**: Steady increase expected
- **Success rate**: Should stay above 95%
- **Error count**: Should be minimal
- **Database size**: Growing as files are tracked

---

## ⚙️ Common Settings

### For Testing
```python
MIGRATION_CONFIG = {
    "batch_size": 10,
    "test_single_account": True,
    "max_test_files": 5,
    "dry_run": True
}
```

### For Production
```python
MIGRATION_CONFIG = {
    "batch_size": 100,
    "test_single_account": False,
    "dry_run": False,
    "max_file_size_mb": 100
}
```

### For Large Scale (1M+ files)
```python
MIGRATION_CONFIG = {
    "batch_size": 200,
    "max_file_size_mb": 50,  # Skip very large files
    "allowed_extensions": ['.pdf', '.docx', '.xlsx']  # Essential types only
}
```

---

## 🔍 Quick Diagnostics

### Check Authentication
```bash
# Test Salesforce
python list_accounts.py

# Test AWS (should not error)
python -c "import boto3; print(boto3.client('s3').list_buckets())"
```

### Check Database Health
```bash
# Database size and record count
python migration_status.py --overview | grep "Total Files"

# Recent activity
python migration_status.py --runs
```

### Check File Paths
```bash
# Verify S3 structure exists
aws s3 ls s3://your-bucket-name/uploads/ --recursive | head -10
```

---

## 🎯 Migration Milestones

### Phase 1 Complete When:
- ✅ All DocListEntry__c records processed
- ✅ Files successfully uploaded to your S3
- ✅ Database tracking complete
- ✅ Success rate > 95%
- ✅ `migration_status.py --readiness` shows ready

### Phase 2 Complete When:
- ✅ Salesforce URLs updated to your S3
- ✅ Users can access files normally
- ✅ Rollback data saved
- ✅ Validation checks passed

---

## 📋 Pre-Migration Checklist

### Before Phase 1
- [ ] Config file setup and tested
- [ ] AWS S3 bucket created and accessible
- [ ] Salesforce permissions verified
- [ ] Disk space available (2GB+ for 1M files)
- [ ] Single account test successful

### Before Phase 2  
- [ ] Phase 1 backup complete
- [ ] Dry run successful
- [ ] User communication sent
- [ ] Rollback plan documented
- [ ] Maintenance window scheduled

### After Migration
- [ ] Users can access files
- [ ] Performance is acceptable
- [ ] Rollback data saved securely
- [ ] External S3 files remain as backup

---

## 🆘 Troubleshooting Quick Fixes

| Problem | Quick Fix |
|---------|-----------|
| "Salesforce auth failed" | Check password and security token |
| "AWS credentials not found" | Run `aws configure` |
| "Database locked" | Check for running migration scripts |
| "No files found" | Verify DocListEntry__c records exist |
| "S3 upload failed" | Check bucket permissions |
| "Migration slow" | Reduce batch_size in config |
| "High memory usage" | Reduce batch_size, add swap space |
| "Disk space low" | Clean up logs/, add more disk |

---

## 📞 Getting Help

### Check These First
1. **Logs**: `logs/` directory for detailed errors
2. **Status**: `python migration_status.py --all`
3. **Config**: Verify all settings in `config.py`
4. **Connectivity**: Test AWS and Salesforce separately

### Debug Commands
```bash
# Full system status
python migration_status.py --export debug_report.json

# Recent errors with details
python migration_status.py --recent-errors 20

# Database integrity
sqlite3 migration_tracking.db "PRAGMA integrity_check;"
```

---

*Keep this guide handy during migration operations. Most issues can be resolved with these quick commands and checks.*