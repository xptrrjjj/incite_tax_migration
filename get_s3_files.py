#!/usr/bin/env python3
"""
S3 Files Discovery
=================

This script gets all DocListEntry__c records and their S3 URLs for BBarth2559 account.
"""

import sys
import json
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

def get_s3_files():
    """Get all S3 file URLs from DocListEntry__c for BBarth2559 account."""
    
    try:
        # Authenticate with Salesforce
        print("Connecting to Salesforce...")
        sf = Salesforce(
            username=SALESFORCE_CONFIG["username"],
            password=SALESFORCE_CONFIG["password"],
            security_token=SALESFORCE_CONFIG["security_token"],
            domain=SALESFORCE_CONFIG["domain"]
        )
        print("✓ Successfully connected to Salesforce")
        
        # Get the Account ID
        print("\n1. Looking up Account ID for BBarth2559...")
        account_query = """
            SELECT Id, Name
            FROM Account
            WHERE Name = 'BBarth2559'
            AND IsDeleted = FALSE
            LIMIT 1
        """
        
        account_result = sf.query(account_query)
        if not account_result['records']:
            print("❌ No account found with name: BBarth2559")
            return
        
        account_id = account_result['records'][0]['Id']
        account_name = account_result['records'][0]['Name']
        print(f"✓ Found Account: {account_name} (ID: {account_id})")
        
        # 2. Get all DocListEntry__c records for this account
        print(f"\n2. Getting all DocListEntry__c records...")
        
        doclist_query = f"""
            SELECT Id, Name, Document__c, Type_Current__c, Type_Original__c, 
                   DocType__c, Parent_Folder__c, Visibility__c, Identifier__c,
                   Source__c, ClientName__c, ApplicableYear__c, TaxonomyStage__c,
                   CreatedDate, LastModifiedDate
            FROM DocListEntry__c
            WHERE Account__c = '{account_id}'
            AND IsDeleted = FALSE
            ORDER BY Name
        """
        
        doclist_result = sf.query_all(doclist_query)
        
        if not doclist_result['records']:
            print("❌ No DocListEntry__c records found")
            return
        
        print(f"✓ Found {len(doclist_result['records'])} DocListEntry__c records")
        
        # 3. Categorize and display all records
        folders = []
        documents = []
        
        for record in doclist_result['records']:
            record_info = {
                'id': record['Id'],
                'name': record['Name'],
                'document_url': record.get('Document__c'),
                'type_current': record.get('Type_Current__c'),
                'type_original': record.get('Type_Original__c'),
                'doc_type': record.get('DocType__c'),
                'parent_folder': record.get('Parent_Folder__c'),
                'identifier': record.get('Identifier__c'),
                'client_name': record.get('ClientName__c'),
                'year': record.get('ApplicableYear__c'),
                'created_date': record.get('CreatedDate'),
                'last_modified': record.get('LastModifiedDate')
            }
            
            if record.get('Type_Current__c') == 'Folder':
                folders.append(record_info)
            else:
                documents.append(record_info)
        
        # 4. Display results
        print(f"\n" + "=" * 80)
        print(f"FOLDERS FOUND ({len(folders)}):")
        print("=" * 80)
        
        for i, folder in enumerate(folders, 1):
            print(f"\n{i}. {folder['name']} (ID: {folder['id']})")
            print(f"   Type: {folder['type_current']}")
            print(f"   Year: {folder['year']}")
            print(f"   Identifier: {folder['identifier']}")
            print(f"   Created: {folder['created_date']}")
        
        print(f"\n" + "=" * 80)
        print(f"DOCUMENTS WITH S3 URLS ({len(documents)}):")
        print("=" * 80)
        
        s3_files = []
        
        for i, doc in enumerate(documents, 1):
            print(f"\n{i}. {doc['name']} (ID: {doc['id']})")
            print(f"   Client: {doc['client_name']}")
            print(f"   Year: {doc['year']}")
            print(f"   Type: {doc['type_current']}")
            print(f"   Doc Type: {doc['doc_type']}")
            print(f"   Created: {doc['created_date']}")
            
            if doc['document_url']:
                print(f"   🔗 S3 URL: {doc['document_url']}")
                s3_files.append({
                    'name': doc['name'],
                    'url': doc['document_url'],
                    'identifier': doc['identifier']
                })
            else:
                print(f"   ❌ No S3 URL found")
        
        # 5. Summary and next steps
        print(f"\n" + "=" * 80)
        print("SUMMARY:")
        print(f"- Total DocListEntry__c records: {len(doclist_result['records'])}")
        print(f"- Folders: {len(folders)}")
        print(f"- Documents: {len(documents)}")
        print(f"- Documents with S3 URLs: {len(s3_files)}")
        print("=" * 80)
        
        print(f"\nS3 BUCKET DETAILS:")
        print(f"- Bucket: trackland-doc-storage")
        print(f"- Region: us-west-2")
        print(f"- Path: /incitetax-pdf-manager/[file-id]")
        
        if s3_files:
            print(f"\nS3 FILES TO MIGRATE:")
            for s3_file in s3_files:
                print(f"- {s3_file['name']}: {s3_file['url']}")
        
        print(f"\n🎯 NEXT STEPS:")
        print(f"1. Update migration script to query DocListEntry__c instead of ContentDocumentLink")
        print(f"2. Download files from trackland-doc-storage S3 bucket")
        print(f"3. Upload files to your incite-tax S3 bucket")
        print(f"4. Update DocListEntry__c.Document__c URLs to point to new S3 bucket")
        
        # 6. Check for child records (documents within folders)
        print(f"\n6. Checking for documents within folders...")
        for folder in folders:
            folder_id = folder['id']
            
            child_query = f"""
                SELECT Id, Name, Document__c, Type_Current__c, ClientName__c
                FROM DocListEntry__c
                WHERE Parent_Folder__c = '{folder_id}'
                AND IsDeleted = FALSE
                ORDER BY Name
            """
            
            child_result = sf.query_all(child_query)
            
            if child_result['records']:
                print(f"\n📁 Folder '{folder['name']}' contains {len(child_result['records'])} documents:")
                for child in child_result['records']:
                    print(f"   - {child['Name']} (Type: {child.get('Type_Current__c')})")
                    if child.get('Document__c'):
                        print(f"     S3 URL: {child['Document__c']}")
                        s3_files.append({
                            'name': child['Name'],
                            'url': child['Document__c'],
                            'identifier': child['Id']
                        })
        
        print(f"\n🎯 FINAL COUNT:")
        print(f"Total S3 files found: {len(s3_files)}")
        
        if len(s3_files) >= 30:
            print(f"✅ FOUND THE FILES! We discovered {len(s3_files)} S3 files, which matches your expected 31 files.")
        else:
            print(f"⚠️  Found {len(s3_files)} S3 files, but expected ~31. May need to check deeper folder structures.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    get_s3_files() 