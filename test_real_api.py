#!/usr/bin/env python3
"""
Test Real Trackland API
=======================

Test the actual API format discovered from browser inspection.
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

def test_real_api():
    """Test the actual API format from browser inspection."""
    
    # Authenticate with Salesforce
    print("🔐 Authenticating with Salesforce...")
    sf = Salesforce(
        username=SALESFORCE_CONFIG["username"],
        password=SALESFORCE_CONFIG["password"],
        security_token=SALESFORCE_CONFIG["security_token"],
        domain=SALESFORCE_CONFIG["domain"]
    )
    print(f"✓ Authenticated with {sf.sf_instance}")
    
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
    
    # Method 1: Try the exact URL pattern from the curl command
    print(f"\n1️⃣ Testing real API URL pattern...")
    
    # The real API URL pattern
    api_url = f"https://incitetax.api.trackland.com/api/generate/presigned-url/{identifier}"
    
    # Headers from the curl command with the valid token
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "authorization": "Bearer U2FsdGVkX1+v3DTrAXS/6wknJyOFMGwOV7/N3fDyarBNOi2R77zRFfpq3WiWIiMMYa06xq8zsFuSc5xC+pNh10ax7jCyF4cpLVrobwkFUjFfSSwjlKqNxEm2rCwNMqZYoRlirbv0oDRNGwmow8gw/w==",
        "content-type": "application/json",
        "origin": "https://incitetax.lightning.force.com",
        "referer": "https://incitetax.lightning.force.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors", 
        "sec-fetch-site": "cross-site"
    }
    
    # Payload from the curl command (adapted for our record)
    payload = {
        "id": doclist_id,
        "type_current": "Document",
        "metadata": {
            "user": "005UU00000220KXYAY",  # This might need to be dynamic
            "app": "doctree",
            "platform": "salesforce", 
            "action": "download"
        },
        "version": "FIRST",
        "track": {
            "name": "TL_Notification_Glacier_Restoration",
            "inputs": {
                "UserId": ["005UU00000220KXYAY"],
                "DocListEntryId": doclist_id
            }
        }
    }
    
    try:
        print(f"URL: {api_url}")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        
        response = requests.post(api_url, json=payload, headers=headers, timeout=30)
        
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:300]}")
        
        if response.status_code == 200:
            try:
                result = response.json()
                # Look for URL in various places
                presigned_url = (result.get('url') or 
                               result.get('data', {}).get('url') or 
                               result.get('presignedUrl') or
                               result.get('downloadUrl'))
                
                if presigned_url:
                    print(f"🎉 SUCCESS! Got presigned URL: {presigned_url[:50]}...")
                    
                    # Test the presigned URL - try both HEAD and GET
                    print(f"🔍 Testing presigned URL...")
                    
                    # Try HEAD request first
                    try:
                        head_response = requests.head(presigned_url, timeout=10)
                        print(f"HEAD status: {head_response.status_code}")
                        
                        if head_response.status_code == 200:
                            file_size = head_response.headers.get('content-length', 'unknown')
                            print(f"✅ HEAD successful! File size: {file_size} bytes")
                            return True
                    except Exception as e:
                        print(f"HEAD failed: {e}")
                    
                    # Try GET request with partial content
                    try:
                        get_response = requests.get(presigned_url, stream=True, timeout=30)
                        print(f"GET status: {get_response.status_code}")
                        
                        if get_response.status_code == 200:
                            # Read first 1024 bytes to verify it's a real file
                            content_sample = get_response.raw.read(1024)
                            print(f"✅ GET successful! Got {len(content_sample)} sample bytes")
                            print(f"Content type: {get_response.headers.get('content-type', 'unknown')}")
                            print(f"Total size: {get_response.headers.get('content-length', 'unknown')} bytes")
                            
                            # Check if it looks like a PDF
                            if content_sample.startswith(b'%PDF'):
                                print(f"✅ Confirmed PDF file!")
                            elif len(content_sample) > 0:
                                print(f"✅ Got file content (not PDF)")
                            
                            return True
                        else:
                            print(f"❌ GET failed: {get_response.status_code}")
                            if get_response.text:
                                print(f"Error response: {get_response.text[:100]}")
                    
                    except Exception as e:
                        print(f"GET failed: {e}")
                
                else:
                    print(f"📋 No URL found in response. Keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                    
            except json.JSONDecodeError:
                if 'http' in response.text:
                    print(f"🎉 Got plain text URL: {response.text.strip()}")
                    return True
                else:
                    print(f"❌ Response is not valid JSON")
        
        elif response.status_code == 401:
            print(f"❌ Unauthorized - need proper authentication token")
        elif response.status_code == 403:
            print(f"❌ Forbidden - access denied")
        else:
            print(f"❌ API returned error: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Request failed: {e}")
    
    # Method 2: Try GET request (no payload)
    print(f"\n2️⃣ Testing GET request...")
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        print(f"GET Status: {response.status_code}")
        print(f"GET Response: {response.text[:200]}")
        
        if response.status_code == 200:
            print(f"🎉 GET request worked!")
            return True
            
    except Exception as e:
        print(f"❌ GET request failed: {e}")
    
    print(f"\n❌ Real API test failed")
    return False

if __name__ == "__main__":
    test_real_api()