#!/usr/bin/env python3
"""
Test Direct Salesforce File Access
==================================

Let's try the simplest approach - accessing files directly through Salesforce
since the PDF viewer can obviously see them.
"""

import requests
from simple_salesforce import Salesforce

# Import our configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    exit(1)

def test_salesforce_direct():
    """Test direct Salesforce file access approaches."""
    
    # Authenticate
    print("🔐 Authenticating with Salesforce...")
    sf = Salesforce(
        username=SALESFORCE_CONFIG["username"],
        password=SALESFORCE_CONFIG["password"],
        security_token=SALESFORCE_CONFIG["security_token"],
        domain=SALESFORCE_CONFIG["domain"]
    )
    print(f"✓ Authenticated with {sf.sf_instance}")
    
    # Get a test file
    print("\n📄 Getting test file info...")
    result = sf.query("""
        SELECT Id, Name, Document__c, Identifier__c 
        FROM DocListEntry__c 
        WHERE Document__c != NULL 
        AND Identifier__c != NULL 
        LIMIT 1
    """)
    
    if not result['records']:
        print("❌ No records found")
        return
    
    record = result['records'][0]
    doclist_id = record['Id']
    original_url = record['Document__c']
    identifier_c = record['Identifier__c']
    
    print(f"Test record: {record['Name']}")
    print(f"DocListEntry ID: {doclist_id}")
    print(f"Original URL: {original_url}")
    print(f"Identifier__c: {identifier_c}")
    
    # Standard Salesforce headers
    headers = {
        'Authorization': f'Bearer {sf.session_id}',
        'User-Agent': 'simple-salesforce/1.0'
    }
    
    print("\n🔍 Testing Salesforce approaches...")
    
    # Method 1: Try the original URL with Salesforce session
    print(f"\n1️⃣ Testing original URL with Salesforce session...")
    try:
        response = requests.get(original_url, headers=headers, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"   Content-Length: {len(response.content)} bytes")
        
        if response.status_code == 200 and len(response.content) > 1000:
            print("   ✅ SUCCESS! Got file content with Salesforce session")
            return True
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Method 2: Try ContentDocument/ContentVersion API
    print(f"\n2️⃣ Testing ContentDocument API...")
    try:
        # Look for ContentDocumentLinks
        content_query = f"""
            SELECT ContentDocumentId, ContentDocument.LatestPublishedVersionId
            FROM ContentDocumentLink 
            WHERE LinkedEntityId = '{doclist_id}'
            LIMIT 1
        """
        
        content_result = sf.query(content_query)
        if content_result['records']:
            version_id = content_result['records'][0]['ContentDocument']['LatestPublishedVersionId']
            
            # Try to download via ContentVersion
            version_url = f"{sf.base_url}sobjects/ContentVersion/{version_id}/VersionData"
            print(f"   Trying: {version_url}")
            
            version_response = requests.get(version_url, headers=headers, timeout=30)
            print(f"   Status: {version_response.status_code}")
            print(f"   Content-Length: {len(version_response.content)} bytes")
            
            if version_response.status_code == 200 and len(version_response.content) > 1000:
                print("   ✅ SUCCESS! Got file via ContentVersion")
                return True
        else:
            print("   No ContentDocumentLinks found")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
    
    # Method 3: Try different Salesforce REST endpoints  
    print(f"\n3️⃣ Testing different Salesforce REST patterns...")
    
    rest_patterns = [
        # Try different object types
        f"/sobjects/Attachment/{doclist_id}/Body",
        f"/sobjects/Document/{doclist_id}/Body", 
        f"/sobjects/ContentVersion/{identifier_c}/VersionData",
        # Try with the identifier
        f"/sobjects/ContentDocument/{identifier_c}",
        f"/sobjects/Attachment/{identifier_c}/Body",
    ]
    
    for pattern in rest_patterns:
        try:
            rest_url = f"{sf.base_url}{pattern.lstrip('/')}"
            print(f"   Trying: {rest_url}")
            
            rest_response = requests.get(rest_url, headers=headers, timeout=10)
            print(f"   Status: {rest_response.status_code}")
            
            if rest_response.status_code == 200 and len(rest_response.content) > 1000:
                print("   ✅ SUCCESS! Got file via REST pattern")
                return True
                
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    # Method 4: Query for actual file storage info
    print(f"\n4️⃣ Checking what Salesforce knows about this file...")
    
    try:
        # Check if there are Attachments
        attach_query = f"SELECT Id, Name, Body FROM Attachment WHERE ParentId = '{doclist_id}' LIMIT 1"
        attach_result = sf.query(attach_query)
        
        if attach_result['records']:
            print(f"   Found Attachment: {attach_result['records'][0]['Name']}")
            attachment_id = attach_result['records'][0]['Id']
            
            # Try to get attachment body
            attach_url = f"{sf.base_url}sobjects/Attachment/{attachment_id}/Body"
            print(f"   Trying attachment: {attach_url}")
            
            attach_response = requests.get(attach_url, headers=headers, timeout=30)
            print(f"   Status: {attach_response.status_code}")
            print(f"   Content-Length: {len(attach_response.content)} bytes")
            
            if attach_response.status_code == 200 and len(attach_response.content) > 1000:
                print("   ✅ SUCCESS! Got file via Attachment")
                return True
        else:
            print("   No Attachments found")
    except Exception as e:
        print(f"   ❌ Attachment check failed: {e}")
    
    # Method 5: Try the PDF viewer URLs we discovered
    print(f"\n5️⃣ Testing PDF viewer page URLs...")
    
    viewer_urls = [
        f"https://{sf.sf_instance}/lightning/n/TL_PDF_Editor",
        f"https://{sf.sf_instance}/apex/TL_PDF_Editor", 
        f"https://{sf.sf_instance}/apex/TL_DocumentManager"
    ]
    
    for viewer_url in viewer_urls:
        try:
            print(f"   Accessing: {viewer_url}")
            
            # Add more browser-like headers
            browser_headers = {
                'Authorization': f'Bearer {sf.session_id}',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5'
            }
            
            viewer_response = requests.get(viewer_url, headers=browser_headers, timeout=10)
            print(f"   Status: {viewer_response.status_code}")
            
            if viewer_response.status_code == 200:
                # Look for any file URLs in the response
                if identifier_c in viewer_response.text:
                    print(f"   ✅ Found identifier {identifier_c} in page source!")
                
                # Look for any direct file patterns
                import re
                file_patterns = re.findall(r'https://[^"\'\s]+\.(?:pdf|doc|docx|txt)', viewer_response.text)
                if file_patterns:
                    print(f"   📁 Found file URLs in page: {file_patterns[:3]}")
                
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    
    print(f"\n❌ All direct Salesforce methods failed")
    return False

if __name__ == "__main__":
    test_salesforce_direct()