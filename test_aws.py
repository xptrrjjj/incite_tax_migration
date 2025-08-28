#!/usr/bin/env python3
"""
AWS S3 Connection Test
=====================

This script tests your AWS credentials and S3 access.
"""

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Try to import configuration
try:
    from config import AWS_CONFIG
    print("✓ Using AWS configuration from config.py")
    USE_CONFIG = True
except ImportError:
    print("⚠️  config.py not found, using default AWS credential chain")
    USE_CONFIG = False
    AWS_CONFIG = {"region": "us-east-1", "bucket_name": "incite-tax"}

def test_aws_credentials():
    """Test AWS credentials and S3 access."""
    print("Testing AWS S3 Connection")
    print("=" * 40)
    
    try:
        # Try to create S3 client
        print("1. Creating S3 client...")
        
        # Check if credentials are provided in config
        if (USE_CONFIG and 
            AWS_CONFIG.get('access_key_id') and 
            AWS_CONFIG.get('secret_access_key') and
            AWS_CONFIG['access_key_id'] != 'your_aws_access_key_id_here' and
            AWS_CONFIG['secret_access_key'] != 'your_aws_secret_access_key_here'):
            
            s3_client = boto3.client(
                's3',
                region_name=AWS_CONFIG['region'],
                aws_access_key_id=AWS_CONFIG['access_key_id'],
                aws_secret_access_key=AWS_CONFIG['secret_access_key']
            )
            print("   ✅ Using credentials from config.py")
        else:
            s3_client = boto3.client('s3', region_name=AWS_CONFIG['region'])
            print("   ✅ Using default AWS credential chain")
            
        print("   ✅ S3 client created successfully")
        
        # Try to list buckets
        print("2. Testing credentials by listing buckets...")
        response = s3_client.list_buckets()
        print("   ✅ Credentials are valid")
        
        # Show existing buckets
        buckets = response['Buckets']
        print(f"   Found {len(buckets)} bucket(s):")
        for bucket in buckets:
            print(f"      - {bucket['Name']}")
        
        # Test the specific bucket
        bucket_name = AWS_CONFIG['bucket_name']
        print(f"3. Testing access to bucket '{bucket_name}'...")
        
        try:
            s3_client.head_bucket(Bucket=bucket_name)
            print(f"   ✅ Bucket '{bucket_name}' exists and is accessible")
            
            # Try to list objects (just to test permissions)
            try:
                s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                print(f"   ✅ You have read access to '{bucket_name}'")
            except ClientError as e:
                print(f"   ⚠️  Limited access to '{bucket_name}': {e}")
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                print(f"   ⚠️  Bucket '{bucket_name}' does not exist")
                print("   💡 The migration script will try to create it")
            elif error_code == '403':
                print(f"   ❌ Access denied to bucket '{bucket_name}'")
                print("   💡 Check your AWS permissions")
            else:
                print(f"   ❌ Error accessing bucket: {e}")
        
        print("\n" + "=" * 40)
        print("✅ AWS S3 Connection Test PASSED")
        print("You're ready to run the migration script!")
        
        return True
        
    except NoCredentialsError:
        print("❌ AWS credentials not found")
        print("\n💡 To fix this, choose one option:")
        print("   1. Run: aws configure")
        print("   2. Set environment variables:")
        print("      export AWS_ACCESS_KEY_ID=your_key")
        print("      export AWS_SECRET_ACCESS_KEY=your_secret")
        print("   3. Use IAM roles (if on EC2)")
        return False
        
    except ClientError as e:
        print(f"❌ AWS error: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_aws_credentials()
    exit(0 if success else 1) 