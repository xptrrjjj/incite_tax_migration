# Getting Started - Proof of Concept Test

This guide will help you quickly test the Salesforce to S3 migration script with one account.

## 🚀 Quick Start (5 minutes)

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Update S3 Bucket Name
Edit `config.py` and update the bucket name:
```python
AWS_CONFIG = {
    "region": "us-east-1",
    "bucket_name": "your-actual-bucket-name-here"  # ← Change this
}
```

### Step 3: (Optional) See Available Accounts
```bash
python list_accounts.py
```
This will show you all accounts with files. Copy an Account ID or Name if you want to test with a specific account.

### Step 4: (Optional) Choose Specific Account
Edit `config.py` to test with a specific account:
```python
MIGRATION_CONFIG = {
    # ... other settings ...
    "test_account_id": "0013D00000AbcDefGHI",  # ← Use an actual Account ID
    # OR
    "test_account_name": "Acme Corporation",   # ← Use an actual Account Name
}
```

### Step 5: Run the Test
```bash
python salesforce_s3_migration.py
```

## 🧪 What the Test Does

Since you're in **DRY RUN + TEST MODE**, the script will:

1. ✅ Connect to Salesforce
2. ✅ Connect to AWS S3
3. ✅ Find files from one account (up to 5 files)
4. ✅ Show you exactly what would happen
5. ❌ **NOT actually move any files**

## 📋 Sample Output

```
Salesforce to S3 File Migration Script
==================================================
🧪 DRY RUN MODE - No files will actually be moved
==================================================
🔍 TEST MODE - Single Account Only
   Will use first account found
   Max files to process: 5
==================================================

2024-01-15 10:30:15 - INFO - ✓ Using configuration from config.py
2024-01-15 10:30:15 - INFO - Logging initialized. Log file: logs/salesforce_migration_20240115_103015.log
2024-01-15 10:30:16 - INFO - Successfully authenticated with Salesforce
2024-01-15 10:30:17 - INFO - Successfully authenticated with AWS S3
2024-01-15 10:30:18 - INFO - 🧪 RUNNING IN TEST MODE - Single Account Only
2024-01-15 10:30:19 - INFO - Found 3 files linked to Account records
2024-01-15 10:30:19 - INFO - Files will be processed for 1 account(s):
2024-01-15 10:30:19 - INFO -   - ABC Company (0013D00000AbcDefGHI): 3 files

==================================================
🔍 DRY RUN - What would happen:
  📁 File: Invoice_2024.pdf
  📊 Size: 1.2 MB
  🏢 Account: ABC Company (0013D00000AbcDefGHI)
  ⬇️  Would download from Salesforce ContentDocument: 0693D000001AbcDef
  ⬆️  Would upload to S3 path: uploads/0013D00000AbcDefGHI/ABC Company/Invoice_2024.pdf
  🔗 S3 URL would be: https://your-bucket.s3.us-east-1.amazonaws.com/uploads/0013D00000AbcDefGHI/ABC Company/Invoice_2024.pdf
  📎 Would re-upload to Salesforce with title: [S3] Invoice_2024.pdf
  🔗 Would link to Account: 0013D00000AbcDefGHI
==================================================

============================================================
MIGRATION SUMMARY
============================================================
Total files processed: 3
Successful migrations: 3
Failed migrations: 0
Skipped files: 0
Total data migrated: 4.50 MB
Success rate: 100.0%
============================================================
🧪 DRY RUN COMPLETED
To perform the actual migration:
1. Set 'dry_run': False in your config.py
2. Run the script again
============================================================
```

## ✅ Next Steps

After the test looks good:

1. **Run the actual migration for one account:**
   ```python
   # In config.py
   MIGRATION_CONFIG = {
       "dry_run": False,        # ← Change to False
       "test_single_account": True,  # Keep as True for now
       # ... other settings
   }
   ```

2. **Run for all accounts:**
   ```python
   # In config.py
   MIGRATION_CONFIG = {
       "dry_run": False,         # ← False for actual migration
       "test_single_account": False,  # ← False for all accounts
       # ... other settings
   }
   ```

## 🆘 Troubleshooting

- **"Authentication failed"**: Check your password and security token
- **"AWS credentials not found"**: Run `aws configure` or set environment variables
- **"Bucket not found"**: Update the bucket name in config.py
- **"No files found"**: Run `python list_accounts.py` to see available accounts

## 📝 Logs

All activity is logged to `logs/salesforce_migration_YYYYMMDD_HHMMSS.log`

---

**Ready to test? Run:** `python salesforce_s3_migration.py` 