"""
Configuration Template for Salesforce to S3 Migration Script
============================================================

Copy this file to 'config.py' and update the values with your actual credentials.
The main script will import from config.py if it exists, otherwise use the defaults.

IMPORTANT: Add 'config.py' to your .gitignore file to avoid committing credentials!
"""

# =============================================================================
# SALESFORCE CONFIGURATION
# =============================================================================

SALESFORCE_CONFIG = {
    "username": "##########",
    "password": "#######",
    "security_token": "#########",
    "domain": "login"  # Use 'test' for sandbox, 'login' for production
}

# =============================================================================
# AWS CONFIGURATION
# =============================================================================

AWS_CONFIG = {
    "region": "us-east-1",
    "bucket_name": "your-actual-bucket-name-here",
    "access_key_id": "your_aws_access_key_id_here",
    "secret_access_key": "your_aws_secret_access_key_here"
}

# =============================================================================
# MIGRATION SETTINGS
# =============================================================================

MIGRATION_CONFIG = {
    "batch_size": 100,  # Process files in batches (adjust based on your needs)
    "max_file_size_mb": 100,  # Skip files larger than this (in MB)
    "allowed_extensions": [
        '.pdf', '.doc', '.docx', '.xls', '.xlsx', 
        '.jpg', '.jpeg', '.png', '.gif', '.txt', '.csv', '.snote'
    ],
    "dry_run": True,  # Set to True to test without actual file operations
    
    # PROOF OF CONCEPT SETTINGS
    "test_single_account": True,  # Set to True to test with just one account
    "test_account_id": None,  # Specific Account ID to test with (if None, uses first account found)
    "test_account_name": "BBarth2559",  # Or specify account name to test with (e.g., "Acme Corp")
    "max_test_files": 5,  # Limit number of files to process during testing
}

# =============================================================================
# SETUP INSTRUCTIONS
# =============================================================================

"""
SETUP INSTRUCTIONS:

1. Copy this file to 'config.py':
   cp config_template.py config.py

2. Update the values in config.py with your actual credentials:
   - SALESFORCE_CONFIG: Your Salesforce username, password, and security token
   - AWS_CONFIG: Your AWS region, S3 bucket name, access key ID, and secret access key
   - MIGRATION_CONFIG: Customize migration settings as needed

3. Add config.py to your .gitignore file:
   echo "config.py" >> .gitignore

4. Run the migration script:
   python salesforce_s3_migration.py

SECURITY NOTES:
- Never commit config.py to version control
- Use environment variables for production deployments
- Consider using AWS IAM roles instead of access keys
- Regularly rotate your Salesforce security token and AWS access keys
- Keep your AWS credentials secure and never share them
""" 