# Migration Deployment Checklist

## Pre-Deployment Phase

### Environment Setup
- [ ] **Python 3.7+** installed and verified
- [ ] **Virtual environment** created and activated
- [ ] **Dependencies** installed via `pip install -r requirements.txt`
- [ ] **Git repository** cloned and accessible
- [ ] **Disk space** verified (minimum 2GB free for 1M files)
- [ ] **Network connectivity** to Salesforce and AWS confirmed

### Credentials & Access
- [ ] **Salesforce credentials** obtained and tested
  - [ ] Username and password verified
  - [ ] Security token generated and current
  - [ ] API access enabled for user
  - [ ] Sandbox vs Production domain confirmed
- [ ] **AWS credentials** configured and tested  
  - [ ] Access key ID and secret access key obtained
  - [ ] S3 bucket created with appropriate name
  - [ ] IAM permissions verified (see permissions document)
  - [ ] AWS CLI configured or environment variables set

### Configuration Files
- [ ] **config_template.py** copied to **config.py**
- [ ] **Salesforce settings** updated in config.py
- [ ] **AWS settings** updated in config.py  
- [ ] **Migration settings** configured appropriately
- [ ] **config.py** added to .gitignore
- [ ] **Test configuration** with `python list_accounts.py`

### Permissions Verification
- [ ] **Salesforce permissions** confirmed
  - [ ] DocListEntry__c: Read, Update access
  - [ ] Account: Read access
  - [ ] ContentDocument/ContentVersion: Read access
  - [ ] API permissions enabled
- [ ] **S3 permissions** confirmed
  - [ ] Bucket access (ListBucket, GetBucketLocation)
  - [ ] Object operations (PutObject, GetObject, DeleteObject)
  - [ ] CreateBucket permission if bucket doesn't exist

---

## Testing Phase

### Single Account Testing
- [ ] **Test account identified** from `list_accounts.py` output
- [ ] **Test configuration** set in config.py:
  ```python
  "test_single_account": True,
  "test_account_id": "specific_account_id", 
  "max_test_files": 5,
  "dry_run": True
  ```
- [ ] **Single account backup** tested successfully
- [ ] **Files uploaded** to S3 verified manually
- [ ] **Database tracking** confirmed in migration_tracking.db
- [ ] **No Salesforce changes** verified (URLs unchanged)

### Small Scale Testing  
- [ ] **Batch size reduced** to 10-20 for testing
- [ ] **Multiple accounts** tested (3-5 accounts)
- [ ] **Error handling** tested with invalid files/URLs
- [ ] **Performance metrics** baseline established
- [ ] **Database queries** tested with `migration_status.py`

### Phase 2 Testing
- [ ] **Dry run mode** tested extensively  
- [ ] **URL updates** validated in dry run logs
- [ ] **New file detection** logic verified
- [ ] **Rollback data generation** confirmed
- [ ] **Validation checks** pass in dry run

---

## Pre-Production Phase

### System Readiness
- [ ] **Full backup environment** prepared
- [ ] **Database backup** strategy established
- [ ] **Log rotation** configured for long-running processes
- [ ] **Monitoring scripts** prepared for progress tracking
- [ ] **Disk space monitoring** alerts configured

### Stakeholder Preparation
- [ ] **User communication** draft prepared
- [ ] **Maintenance window** scheduled if needed for Phase 2
- [ ] **Support team** briefed on migration process
- [ ] **Rollback procedures** documented and reviewed
- [ ] **Emergency contacts** list prepared

### Performance Optimization
- [ ] **Batch size** optimized based on testing
- [ ] **File size limits** configured appropriately  
- [ ] **File type filters** set based on requirements
- [ ] **Network timeout settings** adjusted if needed
- [ ] **Memory usage** profiled and optimized

---

## Production Phase 1 Deployment

### Phase 1 Execution Checklist
- [ ] **Final configuration** review completed
  ```python
  "dry_run": False,
  "test_single_account": False,
  "batch_size": 100  # Or optimized value
  ```
- [ ] **Backup script** launched: `python backup_only_migration.py --full`
- [ ] **Initial progress** verified within first hour
- [ ] **Log monitoring** established
- [ ] **Error rate** within acceptable range (< 5%)

### Phase 1 Monitoring
- [ ] **Progress monitoring** established
  - [ ] `python migration_status.py --overview` scheduled every hour
  - [ ] Log files monitored for errors
  - [ ] Database size growth tracked
  - [ ] System resources monitored (CPU, memory, disk)
- [ ] **Error response** procedures active
  - [ ] Error thresholds defined
  - [ ] Escalation procedures documented
  - [ ] Fix/retry procedures ready

### Phase 1 Validation
- [ ] **File upload verification** - random sample of files accessible in S3
- [ ] **Database consistency** - record counts match processed files  
- [ ] **No Salesforce impact** - users report no issues
- [ ] **Performance metrics** - within expected ranges
- [ ] **Error analysis** - failed files documented and categorized

---

## Phase 1 to Phase 2 Transition

### Phase 1 Completion Verification
- [ ] **All files processed** - migration_status.py shows completion
- [ ] **Success rate acceptable** - > 95% files successfully backed up
- [ ] **Database integrity** - no corruption or missing records
- [ ] **S3 storage verification** - file counts match database records
- [ ] **Incremental backup** capability tested and working

### Phase 2 Preparation  
- [ ] **Phase 2 readiness** confirmed with `migration_status.py --readiness`
- [ ] **User communication** sent about upcoming switchover
- [ ] **Rollback procedures** final review completed
- [ ] **Support team** on standby for Phase 2
- [ ] **Maintenance window** confirmed (if applicable)

### Phase 2 Pre-Execution
- [ ] **Extensive dry run** completed successfully
- [ ] **New files since backup** identified and counted
- [ ] **Rollback data storage** location confirmed
- [ ] **Database backup** taken before Phase 2
- [ ] **Emergency contact list** distributed

---

## Production Phase 2 Deployment

### Phase 2 Execution Checklist
- [ ] **Final confirmation** obtained from stakeholders
- [ ] **Phase 2 script** launched: `python full_migration.py --execute`
- [ ] **Initial progress** verified - new files copying if needed
- [ ] **Salesforce URL updates** begin within expected timeframe
- [ ] **No immediate user impact** confirmed

### Phase 2 Real-time Monitoring
- [ ] **User access testing** - sample files accessible via new URLs
- [ ] **Error monitoring** - Salesforce update failures tracked
- [ ] **Performance monitoring** - response times acceptable
- [ ] **Rollback data** being generated and stored
- [ ] **Validation checks** passing during migration

### Phase 2 Completion
- [ ] **Migration statistics** review - success rates acceptable
- [ ] **User validation** - random user testing successful
- [ ] **Rollback data** saved securely
- [ ] **Database state** updated - files marked as fully migrated
- [ ] **Phase 2 completion** confirmed via `migration_status.py`

---

## Post-Migration Phase

### Immediate Post-Migration
- [ ] **User access verification** - comprehensive user testing
- [ ] **Performance validation** - file loading times acceptable
- [ ] **Error monitoring** - no critical issues reported
- [ ] **Rollback capability** - rollback data verified and accessible
- [ ] **Support team** handling user questions/issues

### System Cleanup
- [ ] **Log files** archived appropriately
- [ ] **Database optimization** - VACUUM and ANALYZE run
- [ ] **Temporary files** cleaned up
- [ ] **Configuration files** secured
- [ ] **Documentation** updated with actual results

### Long-term Monitoring
- [ ] **Performance monitoring** - ongoing metrics collection
- [ ] **Error tracking** - continued monitoring for delayed issues
- [ ] **User feedback** - collection and analysis process
- [ ] **Backup verification** - external S3 files remain accessible
- [ ] **Cost monitoring** - S3 storage costs tracking

---

## Rollback Checklist (If Needed)

### Immediate Rollback
- [ ] **Issue severity** assessed - rollback necessary
- [ ] **Rollback script** executed: `python rollback_migration.py --from-database --execute`
- [ ] **User notification** - immediate communication about issue
- [ ] **Rollback verification** - users can access files via original URLs
- [ ] **Database state** updated - files marked as backup-only

### Post-Rollback
- [ ] **Issue analysis** - root cause investigation
- [ ] **User impact** assessed and documented  
- [ ] **System state** verified - back to pre-Phase 2 condition
- [ ] **Next steps** planned - fix issues and retry timeline
- [ ] **Stakeholder communication** - status and next steps

---

## Success Criteria

### Phase 1 Success
- ✅ **> 95% file success rate** in backup process
- ✅ **Zero user impact** - no complaints or access issues
- ✅ **Database integrity** maintained throughout
- ✅ **Performance** within acceptable ranges
- ✅ **Error handling** working as designed

### Phase 2 Success  
- ✅ **> 95% URL update success rate** in Salesforce
- ✅ **User access** maintained during transition
- ✅ **Performance** equal or better than before
- ✅ **Rollback data** successfully generated
- ✅ **Validation checks** all passing

### Overall Migration Success
- ✅ **Users** accessing files from your S3 seamlessly
- ✅ **Performance** meets or exceeds expectations
- ✅ **Cost** within projected budgets
- ✅ **Reliability** no significant downtime
- ✅ **Documentation** complete for future maintenance

---

## Sign-off Requirements

### Phase 1 Sign-off
- [ ] **Technical Lead** - system functionality confirmed
- [ ] **Operations** - monitoring and performance acceptable
- [ ] **Security** - data protection measures verified
- [ ] **Business Stakeholder** - ready to proceed to Phase 2

### Phase 2 Sign-off
- [ ] **Technical Lead** - migration completed successfully
- [ ] **Operations** - system stable and performant
- [ ] **Security** - data integrity maintained
- [ ] **Business Stakeholder** - user experience acceptable

### Final Project Sign-off
- [ ] **Project Manager** - all deliverables completed
- [ ] **Technical Lead** - system documentation complete
- [ ] **Operations** - handover to production support
- [ ] **Business Stakeholder** - business objectives achieved

---

*This checklist ensures comprehensive preparation, execution, and validation of the two-phase migration system. Adapt the specific criteria and thresholds to match your organization's requirements and risk tolerance.*