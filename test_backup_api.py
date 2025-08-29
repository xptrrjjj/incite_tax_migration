#!/usr/bin/env python3
"""
Test backup migration with working API
=====================================

Test a single file download using the backup migration script
with the working Trackland API approach.
"""

import os
import sys
import requests
import json
from simple_salesforce import Salesforce

# Import our configuration
try:
    from config import SALESFORCE_CONFIG, AWS_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

def test_single_file_download():
    """Test downloading a single file with working Trackland API."""
    
    # Authenticate with Salesforce
    print("🔐 Authenticating with Salesforce...")
    sf = Salesforce(
        username=SALESFORCE_CONFIG["username"],
        password=SALESFORCE_CONFIG["password"],
        security_token=SALESFORCE_CONFIG["security_token"],
        domain=SALESFORCE_CONFIG["domain"]
    )
    print(f"✓ Authenticated with {sf.sf_instance}")
    
    # Get current user info
    user_info = sf.query(f"SELECT Id FROM User WHERE Username = '{SALESFORCE_CONFIG['username']}'")
    if user_info['records']:
        user_id = user_info['records'][0]['Id']
    else:
        user_id = "005UU00000220KXYAY"  # Fallback
    print(f"User ID: {user_id}")
    
    # Get a test file
    print("\n📄 Getting test file...")
    result = sf.query("""
        SELECT Id, Name, Document__c, Identifier__c
        FROM DocListEntry__c 
        WHERE Document__c != NULL 
        AND Identifier__c != NULL 
        LIMIT 1
    """)
    
    if not result['records']:
        print("❌ No test files found")
        return False
    
    record = result['records'][0]
    doclist_id = record['Id']
    identifier = record['Identifier__c']
    
    print(f"Test file: {record['Name']}")
    print(f"DocListEntry ID: {doclist_id}")
    print(f"Identifier: {identifier}")
    
    # Get pre-signed URL using working API
    print(f"\n🔗 Getting pre-signed URL...")
    
    api_url = f"https://incitetax.api.trackland.com/api/generate/presigned-url/{identifier}"
    
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9", 
        "authorization": "Bearer U2FsdGVkX1+v3DTrAXS/6wknJyOFMGwOV7/N3fDyarBNOi2R77zRFfpq3WiWIiMMYa06xq8zsFuSc5xC+pNh10ax7jCyF4cpLVrobwkFUjFfSSwjlKqNxEm2rCwNMqZYoRlirbv0oDRNGwmow8gw/w==",
        "content-type": "application/json",
        "origin": "https://incitetax.lightning.force.com",
        "referer": "https://incitetax.lightning.force.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "id": doclist_id,
        "type_current": "Document",
        "metadata": {
            "user": user_id,
            "app": "doctree",
            "platform": "salesforce",
            "action": "download"
        },
        "version": "FIRST",
        "track": {
            "name": "TL_Notification_Glacier_Restoration",
            "inputs": {
                "UserId": [user_id],
                "DocListEntryId": doclist_id
            }
        }
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            presigned_url = result.get('data', {}).get('url')
            
            if presigned_url:
                print(f"✅ Got pre-signed URL: {presigned_url[:50]}...")
                
                # Download the file
                print(f"\n📥 Downloading file...")
                file_response = requests.get(presigned_url, timeout=300)
                
                if file_response.status_code == 200:
                    content = file_response.content
                    size = len(content)
                    
                    print(f"✅ Downloaded {size} bytes")
                    print(f"Content-Type: {file_response.headers.get('content-type', 'unknown')}")
                    
                    # Verify it's a real file
                    if content.startswith(b'%PDF'):
                        print(f"✅ Confirmed PDF file!")
                        
                        # Save test file 
                        test_filename = f"test_download_{identifier[:8]}.pdf"
                        with open(test_filename, 'wb') as f:
                            f.write(content)
                        print(f"💾 Saved test file: {test_filename}")
                        
                        return True
                    else:
                        print(f"✅ Downloaded file (not PDF): {content[:50]}")
                        return True
                else:
                    print(f"❌ File download failed: {file_response.status_code}")
            else:
                print(f"❌ No URL in API response: {result}")
        else:
            print(f"❌ API failed: {response.status_code} - {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return False

if __name__ == "__main__":
    success = test_single_file_download()
    if success:
        print(f"\n🎉 Single file download test SUCCESSFUL!")
        print(f"Ready to integrate into backup_chunked_migration.py")
    else:
        print(f"\n❌ Single file download test FAILED")