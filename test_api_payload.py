#!/usr/bin/env python3
"""
Test Exact API Payload
======================

Test the exact payload format that the Trackland API expects.
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

def test_api_payload():
    """Test different payload formats with the working API endpoint."""
    
    # Authenticate with Salesforce to get session
    print("🔐 Authenticating with Salesforce...")
    sf = Salesforce(
        username=SALESFORCE_CONFIG["username"],
        password=SALESFORCE_CONFIG["password"],
        security_token=SALESFORCE_CONFIG["security_token"],
        domain=SALESFORCE_CONFIG["domain"]
    )
    print(f"✓ Authenticated with {sf.sf_instance}")
    
    api_url = "https://incitetax.trackland.com/api/generate/presigned-url"
    test_identifier = "33601740-6488-11ef-8437-af86946e29d2"  # From test file
    
    # The different payload formats to test
    payload_tests = [
        # From the JS code patterns we found earlier
        {"identifier": test_identifier, "app": "pdf-editor-sf", "action": "read"},
        {"identifier": test_identifier, "app": "pdf-editor-sf", "action": "save-new-version"},
        {"identifier": test_identifier, "app": "pdf-editor-sf", "action": "get-file"},
        
        # Array format since API said "undefined is not iterable" 
        {"identifiers": [test_identifier], "app": "pdf-editor-sf", "action": "read"},
        {"identifiers": [test_identifier], "app": "pdf-editor-sf", "action": "save-new-version"},
        
        # Simple formats
        {"identifier": test_identifier},
        {"identifiers": [test_identifier]},
        
        # Document-specific formats
        {"fileId": test_identifier, "type": "download"},
        {"documentId": test_identifier, "action": "download"},
    ]
    
    # Test headers
    header_sets = [
        {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {sf.session_id}",
            "Accept": "application/json"
        },
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {sf.session_id}",
            "Accept": "*/*"
        }
    ]
    
    print(f"\n🧪 Testing {len(payload_tests)} payload formats with {len(header_sets)} header sets...")
    print(f"Target API: {api_url}")
    print(f"Test identifier: {test_identifier}")
    
    for i, payload in enumerate(payload_tests, 1):
        for j, headers in enumerate(header_sets, 1):
            print(f"\n[Test {i}.{j}] Payload: {payload}")
            
            try:
                # Properly encode the JSON 
                json_data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
                
                response = requests.post(
                    api_url,
                    data=json_data,
                    headers=headers,
                    timeout=10
                )
                
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        # Look for URL in response
                        url = result.get('url') or result.get('data', {}).get('url') or result.get('presignedUrl')
                        if url:
                            print(f"   🎉 SUCCESS! Found URL: {url[:50]}...")
                            
                            # Test the returned URL
                            print(f"   🔍 Testing returned URL...")
                            test_response = requests.head(url, timeout=5)
                            print(f"   URL test status: {test_response.status_code}")
                            if test_response.status_code == 200:
                                print(f"   ✅ URL works! File size: {test_response.headers.get('content-length', 'unknown')} bytes")
                                return True
                        else:
                            print(f"   📋 Response structure: {list(result.keys()) if isinstance(result, dict) else type(result)}")
                    except:
                        # Maybe plain text URL
                        if 'http' in response.text:
                            print(f"   🎉 SUCCESS! Plain text URL: {response.text.strip()}")
                            return True
                            
            except Exception as e:
                print(f"   ❌ Error: {e}")
    
    print("\n❌ No working payload format found")
    return False

if __name__ == "__main__":
    test_api_payload()