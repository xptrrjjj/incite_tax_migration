#!/usr/bin/env python3
"""
Comprehensive File Discovery Debug
=================================

This script finds ALL files associated with an account through any relationship.
"""

import sys
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)

def comprehensive_file_search():
    """Find ALL files associated with BBarth2559 account through any relationship."""
    
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
        
        all_related_ids = [account_id]  # Start with the account itself
        all_files = {}  # Dictionary to store unique files
        
        # 2. Get all Contacts related to this account
        print(f"\n2. Finding related Contacts...")
        try:
            contacts_query = f"""
                SELECT Id, Name
                FROM Contact
                WHERE AccountId = '{account_id}'
                AND IsDeleted = FALSE
                ORDER BY Name
                LIMIT 100
            """
            
            contacts_result = sf.query_all(contacts_query)
            contact_ids = [c['Id'] for c in contacts_result['records']]
            all_related_ids.extend(contact_ids)
            
            print(f"✓ Found {len(contact_ids)} related Contacts")
            for contact in contacts_result['records'][:5]:  # Show first 5
                print(f"   - {contact['Name']} ({contact['Id']})")
            if len(contacts_result['records']) > 5:
                print(f"   ... and {len(contacts_result['records']) - 5} more")
                
        except SalesforceError as e:
            print(f"Error querying Contacts: {e}")
        
        # 3. Get all Opportunities related to this account
        print(f"\n3. Finding related Opportunities...")
        try:
            opps_query = f"""
                SELECT Id, Name
                FROM Opportunity
                WHERE AccountId = '{account_id}'
                AND IsDeleted = FALSE
                ORDER BY Name
                LIMIT 100
            """
            
            opps_result = sf.query_all(opps_query)
            opp_ids = [o['Id'] for o in opps_result['records']]
            all_related_ids.extend(opp_ids)
            
            print(f"✓ Found {len(opp_ids)} related Opportunities")
            for opp in opps_result['records'][:5]:  # Show first 5
                print(f"   - {opp['Name']} ({opp['Id']})")
            if len(opps_result['records']) > 5:
                print(f"   ... and {len(opps_result['records']) - 5} more")
                
        except SalesforceError as e:
            print(f"Error querying Opportunities: {e}")
        
        # 4. Get all Cases related to this account
        print(f"\n4. Finding related Cases...")
        try:
            cases_query = f"""
                SELECT Id, CaseNumber, Subject
                FROM Case
                WHERE AccountId = '{account_id}'
                AND IsDeleted = FALSE
                ORDER BY CaseNumber
                LIMIT 100
            """
            
            cases_result = sf.query_all(cases_query)
            case_ids = [c['Id'] for c in cases_result['records']]
            all_related_ids.extend(case_ids)
            
            print(f"✓ Found {len(case_ids)} related Cases")
            for case in cases_result['records'][:5]:  # Show first 5
                print(f"   - {case['CaseNumber']}: {case['Subject']} ({case['Id']})")
            if len(cases_result['records']) > 5:
                print(f"   ... and {len(cases_result['records']) - 5} more")
                
        except SalesforceError as e:
            print(f"Error querying Cases: {e}")
        
        # 5. Try to find other standard objects that might be related
        print(f"\n5. Checking for other related records...")
        
        # Check Leads (if they have AccountId field)
        try:
            leads_query = f"""
                SELECT Id, Name, Company
                FROM Lead
                WHERE Company = '{account_name}'
                AND IsDeleted = FALSE
                ORDER BY Name
                LIMIT 50
            """
            
            leads_result = sf.query_all(leads_query)
            lead_ids = [l['Id'] for l in leads_result['records']]
            all_related_ids.extend(lead_ids)
            print(f"✓ Found {len(lead_ids)} related Leads (by company name)")
            
        except SalesforceError as e:
            print(f"Note: Could not query Leads: {e}")
        
        print(f"\n📊 Total related record IDs to check: {len(all_related_ids)}")
        
        # 6. Now search for files linked to ANY of these related records
        print(f"\n6. Searching for files linked to all related records...")
        
        # Process in batches due to Salesforce query limits
        batch_size = 20
        total_files_found = 0
        
        for i in range(0, len(all_related_ids), batch_size):
            batch_ids = all_related_ids[i:i + batch_size]
            ids_str = "', '".join(batch_ids)
            
            print(f"   Checking batch {i//batch_size + 1}/{(len(all_related_ids) + batch_size - 1)//batch_size} ({len(batch_ids)} records)...")
            
            try:
                batch_files_query = f"""
                    SELECT Id, ContentDocumentId, LinkedEntityId, LinkedEntity.Type, LinkedEntity.Name,
                           ContentDocument.Title, ContentDocument.FileExtension,
                           ContentDocument.ContentSize, ContentDocument.CreatedDate,
                           ContentDocument.LastModifiedDate, ContentDocument.IsDeleted
                    FROM ContentDocumentLink 
                    WHERE LinkedEntityId IN ('{ids_str}')
                    ORDER BY ContentDocument.Title
                """
                
                batch_result = sf.query_all(batch_files_query)
                batch_file_count = len(batch_result['records'])
                total_files_found += batch_file_count
                
                print(f"   Found {batch_file_count} files in this batch")
                
                # Store files (avoiding duplicates)
                for record in batch_result['records']:
                    content_doc_id = record['ContentDocumentId']
                    if content_doc_id not in all_files:
                        all_files[content_doc_id] = {
                            'title': record['ContentDocument']['Title'],
                            'extension': record['ContentDocument']['FileExtension'],
                            'size': record['ContentDocument']['ContentSize'],
                            'linked_entity_id': record['LinkedEntityId'],
                            'linked_entity_type': record['LinkedEntity']['Type'],
                            'linked_entity_name': record['LinkedEntity']['Name'],
                            'created_date': record['ContentDocument']['CreatedDate'],
                            'is_deleted': record['ContentDocument']['IsDeleted']
                        }
                
            except SalesforceError as e:
                print(f"   Error with batch: {e}")
                continue
        
        # 7. Show all unique files found
        unique_files = list(all_files.values())
        active_files = [f for f in unique_files if not f['is_deleted']]
        
        print(f"\n" + "=" * 80)
        print(f"7. ALL FILES FOUND ({len(active_files)} active files):")
        print("=" * 80)
        
        # Group files by linked entity type
        files_by_type = {}
        for file_info in active_files:
            entity_type = file_info['linked_entity_type']
            if entity_type not in files_by_type:
                files_by_type[entity_type] = []
            files_by_type[entity_type].append(file_info)
        
        for entity_type, files in files_by_type.items():
            print(f"\n📁 Files linked to {entity_type} records ({len(files)} files):")
            for i, file_info in enumerate(files[:10], 1):  # Show first 10 per type
                size_mb = file_info['size'] / (1024 * 1024) if file_info['size'] else 0
                print(f"  {i:2d}. {file_info['title']}")
                print(f"      Extension: {file_info['extension']}")
                print(f"      Size: {size_mb:.2f} MB")
                print(f"      Linked to: {file_info['linked_entity_name']} ({file_info['linked_entity_type']})")
                print()
            
            if len(files) > 10:
                print(f"      ... and {len(files) - 10} more files")
                print()
        
        # Summary
        print(f"\n" + "=" * 80)
        print("COMPREHENSIVE SUMMARY:")
        print(f"- Total unique active files found: {len(active_files)}")
        print(f"- Total related records checked: {len(all_related_ids)}")
        print("- Files by entity type:")
        for entity_type, files in files_by_type.items():
            print(f"  * {entity_type}: {len(files)} files")
        
        if len(active_files) >= 30:
            print(f"\n🎯 FOUND THE 31 FILES! They are attached to related records, not just the account directly.")
        elif len(active_files) > 1:
            print(f"\n✓ Found more files than just the direct account attachment!")
        else:
            print(f"\n⚠️  Still only finding {len(active_files)} file(s). The 31 files might be in a different system.")
        
        print("=" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    comprehensive_file_search() 