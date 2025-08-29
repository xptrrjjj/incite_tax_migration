#!/usr/bin/env python3
"""
Test Different API Request Formats
==================================

Try different request formats - GET, form data, query params.
"""

import requests
import json
from simple_salesforce import Salesforce
from urllib.parse import urlencode

# Import our configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    exit(1)

def test_api_formats():
    """Test different request formats."""
    
    # Authenticate with Salesforce
    print("🔐 Authenticating with Salesforce...")
    sf = Salesforce(
        username=SALESFORCE_CONFIG["username"],
        password=SALESFORCE_CONFIG["password"],
        security_token=SALESFORCE_CONFIG["security_token"],
        domain=SALESFORCE_CONFIG["domain"]
    )
    print(f"✓ Authenticated with {sf.sf_instance}")
    
    base_url = "https://incitetax.trackland.com"
    test_identifier = "33601740-6488-11ef-8437-af86946e29d2"
    
    # Standard headers
    headers = {
        "Authorization": f"Bearer {sf.session_id}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*"
    }
    
    print(f"\n🔍 Testing different API formats...")
    print(f"Test identifier: {test_identifier}")
    
    # Method 1: GET requests with query parameters
    print(f"\n1️⃣ GET requests with query parameters")
    get_urls = [
        f"{base_url}/api/generate/presigned-url?identifier={test_identifier}",
        f"{base_url}/api/generate/presigned-url?identifier={test_identifier}&action=read",
        f"{base_url}/api/generate/presigned-url?identifier={test_identifier}&app=pdf-editor-sf&action=read",
        f"{base_url}/api/files/{test_identifier}/download",
        f"{base_url}/api/documents/{test_identifier}",
        f"{base_url}/api/documents/{test_identifier}/download",
        f"{base_url}/api/document/versions/{test_identifier}",
    ]
    
    for url in get_urls:
        try:
            print(f"   GET: {url}")
            response = requests.get(url, headers=headers, timeout=10)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:100]}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    # Look for URL in response
                    found_url = result.get('url') or result.get('data', {}).get('url') or result.get('presignedUrl')
                    if found_url:
                        print(f"   🎉 SUCCESS! Found URL: {found_url[:50]}...")
                        return True
                except:
                    if 'http' in response.text:
                        print(f"   🎉 SUCCESS! Plain text URL: {response.text.strip()}")
                        return True
                        
        except Exception as e:
            print(f"   Error: {e}")
    
    # Method 2: POST with form data
    print(f"\n2️⃣ POST with form data")
    form_data_sets = [
        {"identifier": test_identifier},
        {"identifier": test_identifier, "action": "read"},
        {"identifier": test_identifier, "app": "pdf-editor-sf", "action": "read"},
        {"identifiers": test_identifier},  # Single value instead of array
    ]
    
    form_headers = headers.copy()
    form_headers["Content-Type"] = "application/x-www-form-urlencoded"
    
    for data in form_data_sets:
        try:
            print(f"   Form data: {data}")
            response = requests.post(
                f"{base_url}/api/generate/presigned-url",
                data=data,
                headers=form_headers,
                timeout=10
            )
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.text[:100]}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    found_url = result.get('url') or result.get('data', {}).get('url') or result.get('presignedUrl')
                    if found_url:
                        print(f"   🎉 SUCCESS! Found URL: {found_url[:50]}...")
                        return True
                except:
                    if 'http' in response.text:
                        print(f"   🎉 SUCCESS! Plain text URL: {response.text.strip()}")
                        return True
                        
        except Exception as e:
            print(f"   Error: {e}")
    
    # Method 3: Try without Authorization header (maybe it uses cookies)
    print(f"\n3️⃣ Requests without Authorization header")
    no_auth_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        "Content-Type": "application/json"
    }
    
    simple_payload = {"identifier": test_identifier}
    
    try:
        print(f"   No auth JSON: {simple_payload}")
        response = requests.post(
            f"{base_url}/api/generate/presigned-url",
            json=simple_payload,
            headers=no_auth_headers,
            timeout=10
        )
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
        if response.status_code == 200:
            print(f"   🎉 SUCCESS! No auth needed")
            return True
            
    except Exception as e:
        print(f"   Error: {e}")
    
    # Method 4: Try the direct S3 URL approach
    print(f"\n4️⃣ Try constructing S3 URL directly")
    s3_url = f"https://trackland-doc-storage.s3.us-west-2.amazonaws.com/incitetax-pdf-manager/{test_identifier}.pdf"
    
    try:
        print(f"   Direct S3: {s3_url}")
        response = requests.head(s3_url, headers=headers, timeout=10)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"   🎉 SUCCESS! Direct S3 access works")
            print(f"   File size: {response.headers.get('content-length', 'unknown')} bytes")
            return True
        elif response.status_code == 403:
            print(f"   ❌ 403 Forbidden - S3 bucket requires proper auth")
        elif response.status_code == 404:
            print(f"   ❌ 404 Not Found - File doesn't exist at this URL")
            
    except Exception as e:
        print(f"   Error: {e}")
    
    print(f"\n❌ No working API format found")
    return False

if __name__ == "__main__":
    test_api_formats()