#!/usr/bin/env python3
"""
Hidden Files & S3 References Debug
==================================

This script finds hidden file references in custom fields, notes, and other objects.
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

def find_hidden_files():
    """Find hidden file references in Salesforce."""
    
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
        
        # Get related record IDs (reuse logic from comprehensive script)
        all_related_ids = [account_id]
        
        # Get Contacts
        try:
            contacts_query = f"""
                SELECT Id, Name
                FROM Contact
                WHERE AccountId = '{account_id}'
                AND IsDeleted = FALSE
            """
            contacts_result = sf.query_all(contacts_query)
            contact_ids = [c['Id'] for c in contacts_result['records']]
            all_related_ids.extend(contact_ids)
            print(f"✓ Found {len(contact_ids)} related Contacts")
        except SalesforceError as e:
            print(f"Error querying Contacts: {e}")
        
        # Get Opportunities
        try:
            opps_query = f"""
                SELECT Id, Name
                FROM Opportunity
                WHERE AccountId = '{account_id}'
                AND IsDeleted = FALSE
            """
            opps_result = sf.query_all(opps_query)
            opp_ids = [o['Id'] for o in opps_result['records']]
            all_related_ids.extend(opp_ids)
            print(f"✓ Found {len(opp_ids)} related Opportunities")
        except SalesforceError as e:
            print(f"Error querying Opportunities: {e}")
        
        # Get Cases
        try:
            cases_query = f"""
                SELECT Id, CaseNumber
                FROM Case
                WHERE AccountId = '{account_id}'
                AND IsDeleted = FALSE
            """
            cases_result = sf.query_all(cases_query)
            case_ids = [c['Id'] for c in cases_result['records']]
            all_related_ids.extend(case_ids)
            print(f"✓ Found {len(case_ids)} related Cases")
        except SalesforceError as e:
            print(f"Error querying Cases: {e}")
        
        print(f"\n📊 Total related record IDs: {len(all_related_ids)}")
        
        # 2. Check for Notes with file references
        print(f"\n2. Checking Notes for file references...")
        try:
            # Process in batches
            batch_size = 20
            total_notes = 0
            notes_with_files = []
            
            for i in range(0, len(all_related_ids), batch_size):
                batch_ids = all_related_ids[i:i + batch_size]
                ids_str = "', '".join(batch_ids)
                
                notes_query = f"""
                    SELECT Id, Title, Body, ParentId, Parent.Type, Parent.Name
                    FROM Note
                    WHERE ParentId IN ('{ids_str}')
                    AND IsDeleted = FALSE
                    AND (Body LIKE '%s3%' OR Body LIKE '%http%' OR Body LIKE '%file%' OR Body LIKE '%document%')
                    ORDER BY Title
                """
                
                notes_result = sf.query_all(notes_query)
                total_notes += len(notes_result['records'])
                
                for note in notes_result['records']:
                    if any(keyword in note['Body'].lower() for keyword in ['s3', 'http', 'file', 'document', 'upload']):
                        notes_with_files.append(note)
            
            print(f"✓ Found {len(notes_with_files)} Notes with potential file references (out of {total_notes} total)")
            
            for note in notes_with_files[:5]:  # Show first 5
                print(f"   - {note['Title']} (Parent: {note['Parent']['Name']})")
                body_preview = note['Body'][:100] + "..." if len(note['Body']) > 100 else note['Body']
                print(f"     Body: {body_preview}")
        
        except SalesforceError as e:
            print(f"Error querying Notes: {e}")
        
        # 3. Check for Tasks with file references
        print(f"\n3. Checking Tasks for file references...")
        try:
            batch_size = 20
            total_tasks = 0
            tasks_with_files = []
            
            for i in range(0, len(all_related_ids), batch_size):
                batch_ids = all_related_ids[i:i + batch_size]
                ids_str = "', '".join(batch_ids)
                
                tasks_query = f"""
                    SELECT Id, Subject, Description, WhatId, What.Type, What.Name
                    FROM Task
                    WHERE WhatId IN ('{ids_str}')
                    AND IsDeleted = FALSE
                    AND (Description LIKE '%s3%' OR Description LIKE '%http%' OR Description LIKE '%file%' OR Description LIKE '%document%')
                    ORDER BY Subject
                """
                
                tasks_result = sf.query_all(tasks_query)
                total_tasks += len(tasks_result['records'])
                
                for task in tasks_result['records']:
                    if task['Description'] and any(keyword in task['Description'].lower() for keyword in ['s3', 'http', 'file', 'document', 'upload']):
                        tasks_with_files.append(task)
            
            print(f"✓ Found {len(tasks_with_files)} Tasks with potential file references (out of {total_tasks} total)")
            
            for task in tasks_with_files[:5]:  # Show first 5
                print(f"   - {task['Subject']} (Related to: {task['What']['Name']})")
                if task['Description']:
                    desc_preview = task['Description'][:100] + "..." if len(task['Description']) > 100 else task['Description']
                    print(f"     Description: {desc_preview}")
        
        except SalesforceError as e:
            print(f"Error querying Tasks: {e}")
        
        # 4. Check for custom objects (more comprehensive)
        print(f"\n4. Checking for ALL custom objects...")
        try:
            # Get all custom objects
            custom_objects = []
            
            # Use describe to get all objects
            all_objects = sf.describe()['sobjects']
            
            for obj in all_objects:
                if obj['name'].endswith('__c'):  # Custom objects end with __c
                    custom_objects.append(obj['name'])
            
            print(f"✓ Found {len(custom_objects)} custom objects")
            
            # Check each custom object for records related to our account
            for obj_name in custom_objects[:10]:  # Check first 10
                try:
                    # Try to find records related to our account
                    test_query = f"SELECT Id FROM {obj_name} WHERE IsDeleted = FALSE LIMIT 1"
                    test_result = sf.query(test_query)
                    
                    if test_result['records']:
                        print(f"   - {obj_name}: Has {test_result['totalSize']} records")
                        
                        # Try to find records with account references
                        account_ref_query = f"""
                            SELECT Id, Name 
                            FROM {obj_name} 
                            WHERE Account__c = '{account_id}' 
                            AND IsDeleted = FALSE 
                            LIMIT 5
                        """
                        try:
                            account_ref_result = sf.query(account_ref_query)
                            if account_ref_result['records']:
                                print(f"     → {len(account_ref_result['records'])} records linked to BBarth2559!")
                        except:
                            # Try with different field names
                            for field_name in ['AccountId__c', 'Account_Id__c', 'RelatedAccount__c']:
                                try:
                                    alt_query = f"""
                                        SELECT Id, Name 
                                        FROM {obj_name} 
                                        WHERE {field_name} = '{account_id}' 
                                        AND IsDeleted = FALSE 
                                        LIMIT 5
                                    """
                                    alt_result = sf.query(alt_query)
                                    if alt_result['records']:
                                        print(f"     → {len(alt_result['records'])} records linked via {field_name}!")
                                        break
                                except:
                                    continue
                
                except SalesforceError:
                    continue
        
        except Exception as e:
            print(f"Error checking custom objects: {e}")
        
        # 5. Check for Email Messages with attachments
        print(f"\n5. Checking Email Messages for file references...")
        try:
            batch_size = 20
            total_emails = 0
            emails_with_files = []
            
            for i in range(0, len(all_related_ids), batch_size):
                batch_ids = all_related_ids[i:i + batch_size]
                ids_str = "', '".join(batch_ids)
                
                emails_query = f"""
                    SELECT Id, Subject, TextBody, HtmlBody, RelatedToId, RelatedTo.Type, RelatedTo.Name
                    FROM EmailMessage
                    WHERE RelatedToId IN ('{ids_str}')
                    AND (TextBody LIKE '%s3%' OR TextBody LIKE '%http%' OR TextBody LIKE '%file%' OR TextBody LIKE '%document%'
                         OR HtmlBody LIKE '%s3%' OR HtmlBody LIKE '%http%' OR HtmlBody LIKE '%file%' OR HtmlBody LIKE '%document%')
                    ORDER BY Subject
                """
                
                emails_result = sf.query_all(emails_query)
                total_emails += len(emails_result['records'])
                
                for email in emails_result['records']:
                    body_text = (email['TextBody'] or '') + (email['HtmlBody'] or '')
                    if any(keyword in body_text.lower() for keyword in ['s3', 'http', 'file', 'document', 'upload']):
                        emails_with_files.append(email)
            
            print(f"✓ Found {len(emails_with_files)} Email Messages with potential file references (out of {total_emails} total)")
            
            for email in emails_with_files[:3]:  # Show first 3
                print(f"   - {email['Subject']} (Related to: {email['RelatedTo']['Name']})")
        
        except SalesforceError as e:
            print(f"Error querying Email Messages: {e}")
        
        print(f"\n" + "=" * 80)
        print("SUMMARY:")
        print(f"- Notes with file references: {len(notes_with_files)}")
        print(f"- Tasks with file references: {len(tasks_with_files)}")
        print(f"- Email Messages with file references: {len(emails_with_files)}")
        print(f"- Custom objects found: {len(custom_objects) if 'custom_objects' in locals() else 0}")
        print("=" * 80)
        
        # Show details of most promising findings
        if notes_with_files:
            print(f"\n🔍 DETAILED NOTES WITH FILE REFERENCES:")
            for note in notes_with_files:
                print(f"\nTitle: {note['Title']}")
                print(f"Parent: {note['Parent']['Name']} ({note['Parent']['Type']})")
                print(f"Body: {note['Body']}")
                print("-" * 40)
        
        if tasks_with_files:
            print(f"\n🔍 DETAILED TASKS WITH FILE REFERENCES:")
            for task in tasks_with_files:
                print(f"\nSubject: {task['Subject']}")
                print(f"Related to: {task['What']['Name']} ({task['What']['Type']})")
                print(f"Description: {task['Description']}")
                print("-" * 40)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    find_hidden_files() 