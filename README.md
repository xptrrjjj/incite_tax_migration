# Salesforce to S3 File Migration Script

A production-ready Python script that automates the migration of files from Salesforce to AWS S3 and back, preserving file structure and relinking files to their original Account records.

## Features

- **Automated File Migration**: Downloads files from Salesforce, uploads to S3, and re-uploads to Salesforce
- **Structure Preservation**: Maintains organized folder structure in S3: `uploads/{AccountId}/{AccountName}/{filename}`
- **Account-Specific Scope**: Only processes files linked to Account objects
- **Batch Processing**: Processes files in configurable batches for optimal performance
- **Comprehensive Logging**: Detailed logging with timestamps and file tracking
- **Error Handling**: Robust error handling with retry logic and detailed error reporting
- **Configuration Validation**: Validates all required settings before execution
- **Dry Run Mode**: Test the migration process without actually moving files
- **File Filtering**: Configurable file size limits and allowed extensions
- **Migration Statistics**: Detailed reporting on migration success rates and file counts

## Prerequisites

1. **Python 3.7+** installed on your system
2. **Salesforce Account** with API access
3. **AWS Account** with S3 access
4. **AWS CLI configured** or environment variables set up for authentication

## Installation

1. Clone or download the script files:
```bash
git clone <repository-url>
cd incite_salesforceBackup
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

### 1. Salesforce Configuration

Update the `SALESFORCE_CONFIG` section in `salesforce_s3_migration.py`:

```python
SALESFORCE_CONFIG = {
    "username": "Automation@incitetax.com",
    "password": "your_actual_password",
    "security_token": "your_actual_security_token",
    "domain": "login"  # Use 'test' for sandbox
}
```

**To get your Salesforce Security Token:**
1. Log into Salesforce
2. Go to Setup → My Personal Information → Reset My Security Token
3. Click "Reset Security Token"
4. Check your email for the new token

### 2. AWS Configuration

Update the `AWS_CONFIG` section:

```python
AWS_CONFIG = {
    "region": "us-east-1",
    "bucket_name": "your-actual-bucket-name"
}
```

**AWS Authentication Options:**

Option 1: AWS CLI Configuration
```bash
aws configure
```

Option 2: Environment Variables
```bash
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key
export AWS_DEFAULT_REGION=us-east-1
```

Option 3: IAM Role (for EC2 instances)
- Attach an IAM role with S3 permissions to your EC2 instance

### 3. Migration Settings (Optional)

Customize the `MIGRATION_CONFIG` section as needed:

```python
MIGRATION_CONFIG = {
    "batch_size": 100,  # Process files in batches
    "max_file_size_mb": 100,  # Skip files larger than this
    "allowed_extensions": ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.gif', '.txt', '.csv'],
    "dry_run": False,  # Set to True to test without actual file operations
}
```

## Usage

### Basic Usage

1. Configure the script with your credentials (see Configuration section)
2. Run the migration:

```bash
python salesforce_s3_migration.py
```

### Dry Run (Recommended First)

Test the migration without actually moving files:

```python
# In the script, set:
MIGRATION_CONFIG = {
    # ... other settings ...
    "dry_run": True,
}
```

Then run:
```bash
python salesforce_s3_migration.py
```

### Monitor Progress

The script provides real-time logging output showing:
- Authentication status
- File discovery progress
- Individual file migration status
- Batch processing progress
- Final migration statistics

## File Structure

The script creates the following S3 structure:

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
│   │   │   ├── file3.xlsx
│   │   │   └── file4.jpg
│   │   └── ...
│   └── ...
```

## Logging

The script creates detailed log files in the `logs/` directory:

- **Console Output**: Real-time progress updates
- **Log Files**: Detailed logs with timestamps (`logs/salesforce_migration_YYYYMMDD_HHMMSS.log`)
- **Migration Statistics**: Summary of successful/failed migrations

## Error Handling

The script includes comprehensive error handling for:

- **Authentication failures** (Salesforce and AWS)
- **Network connectivity issues**
- **File download/upload failures**
- **S3 bucket creation issues**
- **Salesforce API limits**
- **File size restrictions**
- **Invalid file types**

## Security Considerations

1. **Credential Security**: Never commit credentials to version control
2. **Environment Variables**: Use environment variables for sensitive data
3. **IAM Permissions**: Use least-privilege IAM policies
4. **VPC Security**: Run from secure networks when possible
5. **Data Encryption**: S3 encryption is recommended for sensitive files

## Required AWS Permissions

Your AWS user/role needs these S3 permissions:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-bucket-name",
                "arn:aws:s3:::your-bucket-name/*"
            ]
        }
    ]
}
```

## Required Salesforce Permissions

Your Salesforce user needs:

- **API Enabled** profile permission
- **View All Data** or specific object permissions for:
  - ContentDocument
  - ContentVersion
  - ContentDocumentLink
  - Account
- **Create, Read, Update** permissions on ContentVersion and ContentDocumentLink

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify credentials are correct
   - Check security token is current
   - Ensure API access is enabled

2. **AWS Access Denied**
   - Verify AWS credentials are configured
   - Check IAM permissions
   - Confirm bucket name is correct

3. **Large File Failures**
   - Increase `max_file_size_mb` setting
   - Check network stability for large uploads

4. **Rate Limiting**
   - Reduce `batch_size` setting
   - Add delays between API calls if needed

### Debug Mode

Enable detailed debugging by modifying the logging level:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO
    # ... rest of config
)
```

## Support

For issues or questions:

1. Check the log files for detailed error messages
2. Verify all configuration settings
3. Test with dry run mode first
4. Review the troubleshooting section above

## License

This script is provided as-is for internal use. Please review and test thoroughly before production use.

## Version History

- **v1.0.0**: Initial release with full migration functionality
  - Salesforce to S3 migration
  - Structure preservation
  - Account-specific filtering
  - Comprehensive logging
  - Error handling and validation 