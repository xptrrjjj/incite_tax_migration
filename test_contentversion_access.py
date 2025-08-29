#!/usr/bin/env python3
"""
Test ContentVersion Direct Access
=================================

Focus on the ContentVersion API approach since it returned 200 status.
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

def test_contentversion_access():
    """Test direct ContentVersion access in detail."""
    
    # Authenticate
    print("🔐 Authenticating with Salesforce...")
    sf = Salesforce(
        username=SALESFORCE_CONFIG["username"],
        password=SALESFORCE_CONFIG["password"],
        security_token=SALESFORCE_CONFIG["security_token"],
        domain=SALESFORCE_CONFIG["domain"]
    )
    print(f"✓ Authenticated with {sf.sf_instance}")
    
    # Get test files with ContentDocumentLinks
    print("\n📄 Finding files with ContentDocument relationships...")
    
    # First get DocListEntry records
    doclist_result = sf.query("""
        SELECT Id, Name, Document__c, Identifier__c
        FROM DocListEntry__c 
        WHERE Document__c != NULL 
        AND Identifier__c != NULL 
        LIMIT 5
    """)
    
    if not doclist_result['records']:
        print("❌ No DocListEntry records found")
        return
    
    # Then for each record, find its ContentDocumentLinks
    result = {'records': []}
    for record in doclist_result['records']:
        # Get ContentDocumentLinks for this record
        links_result = sf.query(f"""
            SELECT ContentDocumentId, ContentDocument.Title, 
                   ContentDocument.LatestPublishedVersionId,
                   ContentDocument.FileType, ContentDocument.ContentSize
            FROM ContentDocumentLink 
            WHERE LinkedEntityId = '{record['Id']}'
        """)
        
        # Add the links to the record
        record['ContentDocumentLinks'] = links_result
        result['records'].append(record)
    
    if not result['records']:
        print("❌ No records found with ContentDocumentLinks")
        return
    
    headers = {
        'Authorization': f'Bearer {sf.session_id}',
        'User-Agent': 'simple-salesforce/1.0'
    }
    
    for record in result['records']:
        print(f"\n📋 Testing: {record['Name']}")
        print(f"   DocList ID: {record['Id']}")
        print(f"   Original URL: {record['Document__c']}")
        print(f"   Identifier: {record['Identifier__c']}")
        
        # Check ContentDocumentLinks
        links = record.get('ContentDocumentLinks', {}).get('records', [])
        
        if not links:
            print("   ❌ No ContentDocumentLinks found")
            continue
            
        for link in links:
            content_doc = link['ContentDocument']
            doc_id = link['ContentDocumentId']
            version_id = content_doc['LatestPublishedVersionId']
            
            print(f"   📄 ContentDocument: {content_doc['Title']}")
            print(f"       Type: {content_doc.get('FileType', 'unknown')}")
            print(f"       Size: {content_doc.get('ContentSize', 'unknown')} bytes")
            print(f"       Version ID: {version_id}")
            
            # Try different ContentVersion access methods
            version_urls = [
                f"https://{sf.sf_instance}/services/data/v59.0/sobjects/ContentVersion/{version_id}/VersionData",
                f"https://{sf.sf_instance}/services/data/v60.0/sobjects/ContentVersion/{version_id}/VersionData", 
                f"https://{sf.sf_instance}/services/data/v58.0/sobjects/ContentVersion/{version_id}/VersionData",
                f"{sf.base_url}sobjects/ContentVersion/{version_id}/VersionData"
            ]
            
            for url in version_urls:
                try:
                    print(f"       Testing: {url}")
                    response = requests.get(url, headers=headers, timeout=30)
                    print(f"       Status: {response.status_code}")
                    print(f"       Content-Length: {len(response.content)} bytes")
                    print(f"       Content-Type: {response.headers.get('content-type', 'unknown')}")
                    
                    if response.status_code == 200 and len(response.content) > 0:
                        print(f"       ✅ SUCCESS! Got {len(response.content)} bytes of file data")
                        
                        # Save a small sample to verify it's actually file content
                        if len(response.content) > 1000:
                            with open(f"test_download_{version_id[:8]}.pdf", "wb") as f:
                                f.write(response.content)
                            print(f"       💾 Saved test file: test_download_{version_id[:8]}.pdf")
                        
                        return True
                        
                    elif response.status_code == 200:
                        print(f"       ⚠️ Got 200 but empty content")
                        
                except Exception as e:
                    print(f"       ❌ Error: {e}")
            
            # Also try the ContentDocument directly
            doc_url = f"https://{sf.sf_instance}/services/data/v59.0/sobjects/ContentDocument/{doc_id}"
            try:
                print(f"       Testing ContentDocument: {doc_url}")
                doc_response = requests.get(doc_url, headers=headers, timeout=10)
                print(f"       ContentDocument Status: {doc_response.status_code}")
                
                if doc_response.status_code == 200:
                    doc_data = doc_response.json()
                    print(f"       ContentDocument info: {doc_data.get('Title', 'N/A')} - {doc_data.get('FileType', 'N/A')}")
                    
            except Exception as e:
                print(f"       ❌ ContentDocument error: {e}")
    
    print("\n❌ No working ContentVersion access found")
    return False

if __name__ == "__main__":
    test_contentversion_access()