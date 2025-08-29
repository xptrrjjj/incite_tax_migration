#!/usr/bin/env python3
"""
Test with Real User Token
=========================

Get the actual user ID and try to understand the token format.
"""

import requests
import json
from simple_salesforce import Salesforce

# Import our configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    exit(1)

def test_with_user_token():
    """Test with the actual current user."""
    
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
    print("\n👤 Getting current user info...")
    user_info = sf.query("SELECT Id, Username, Name FROM User WHERE Username = '{}'".format(SALESFORCE_CONFIG["username"]))
    
    if user_info['records']:
        user_id = user_info['records'][0]['Id']
        username = user_info['records'][0]['Username']
        name = user_info['records'][0]['Name']
        print(f"User ID: {user_id}")
        print(f"Username: {username}")
        print(f"Name: {name}")
    else:
        print("❌ Could not get user info")
        return False
    
    # Get a test DocListEntry record
    print("\n📄 Getting test DocListEntry...")
    result = sf.query("""
        SELECT Id, Name, Document__c, Identifier__c
        FROM DocListEntry__c 
        WHERE Document__c != NULL 
        AND Identifier__c != NULL 
        LIMIT 1
    """)
    
    if not result['records']:
        print("❌ No DocListEntry records found")
        return False
    
    record = result['records'][0]
    doclist_id = record['Id']
    identifier = record['Identifier__c']
    
    print(f"Test record: {record['Name']}")
    print(f"DocListEntry ID: {doclist_id}")
    print(f"Identifier: {identifier}")
    
    # Method 1: Try with current user ID in payload
    print(f"\n1️⃣ Testing with correct user ID...")
    
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
    
    # Use the correct user ID
    payload = {
        "id": doclist_id,
        "type_current": "Document", 
        "metadata": {
            "user": user_id,  # Use actual user ID
            "app": "doctree",
            "platform": "salesforce",
            "action": "download"
        },
        "version": "FIRST",
        "track": {
            "name": "TL_Notification_Glacier_Restoration",
            "inputs": {
                "UserId": [user_id],  # Use actual user ID
                "DocListEntryId": doclist_id
            }
        }
    }
    
    # Try different content-type headers to fix the encoding issue
    content_types = [
        "application/json",
        "application/json; charset=utf-8",
        "text/plain",
        "application/x-www-form-urlencoded"
    ]
    
    for content_type in content_types:
        print(f"\n   Testing Content-Type: {content_type}")
        test_headers = headers.copy()
        test_headers["content-type"] = content_type
        
        try:
            if content_type == "application/x-www-form-urlencoded":
                # Try form data
                response = requests.post(api_url, data=payload, headers=test_headers, timeout=10)
            elif content_type == "text/plain":
                # Try plain text JSON
                response = requests.post(api_url, data=json.dumps(payload), headers=test_headers, timeout=10)
            else:
                # Try normal JSON
                response = requests.post(api_url, json=payload, headers=test_headers, timeout=10)
            
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:150]}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    presigned_url = result.get('url') or result.get('data', {}).get('url')
                    if presigned_url:
                        print(f"   🎉 SUCCESS! Got URL: {presigned_url[:50]}...")
                        return True
                except:
                    pass
            elif response.status_code != 400 or "Unexpected token" not in response.text:
                print(f"   🤔 Different error - may be progress")
                
        except Exception as e:
            print(f"   Error: {e}")
    
    # Method 2: Try simpler payloads
    print(f"\n2️⃣ Testing simpler payloads...")
    
    simple_payloads = [
        {"id": doclist_id},
        {"identifier": identifier},
        {"doclistentry_id": doclist_id, "file_id": identifier},
    ]
    
    for payload in simple_payloads:
        try:
            print(f"   Simple payload: {payload}")
            response = requests.post(api_url, json=payload, headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:100]}")
            
            if response.status_code == 200:
                print(f"   🎉 SUCCESS with simple payload!")
                return True
            elif "Unexpected token" not in response.text:
                print(f"   🤔 Different error: {response.text[:100]}")
                
        except Exception as e:
            print(f"   Error: {e}")
    
    print(f"\n❌ All methods failed")
    return False

if __name__ == "__main__":
    test_with_user_token()