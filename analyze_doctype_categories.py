"""
DocType Analysis Script
=======================

Analyzes DocType__c field on DocListEntry__c records to understand
the categories/types of documents in Salesforce.

This helps understand what kinds of documents are being stored and
how they're categorized.
"""

import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from simple_salesforce import Salesforce
from collections import defaultdict

# Import config
try:
    import config
    SALESFORCE_CONFIG = config.SALESFORCE_CONFIG
except ImportError:
    print("❌ Error: config.py not found. Copy config_template.py to config.py and configure.")
    sys.exit(1)


class DocTypeAnalyzer:
    """Analyze DocType__c categories in DocListEntry__c records."""

    def __init__(self):
        self.sf = None
        self.connect_salesforce()

    def connect_salesforce(self):
        """Connect to Salesforce API."""
        try:
            sf_config = SALESFORCE_CONFIG
            self.sf = Salesforce(
                username=sf_config['username'],
                password=sf_config['password'],
                security_token=sf_config['security_token'],
                domain=sf_config['domain']
            )
            print("✅ Connected to Salesforce\n")
        except Exception as e:
            print(f"❌ Failed to connect to Salesforce: {e}")
            sys.exit(1)

    def get_doctype_field_info(self):
        """Get information about the DocType__c field."""
        print("=" * 100)
        print("STEP 1: ANALYZING DocType__c FIELD")
        print("=" * 100)

        try:
            # Describe the DocListEntry__c object
            describe = self.sf.DocListEntry__c.describe()

            # Find the DocType__c field
            doctype_field = None
            for field in describe['fields']:
                if field['name'] == 'DocType__c':
                    doctype_field = field
                    break

            if not doctype_field:
                print("\n❌ DocType__c field not found on DocListEntry__c object")
                return None

            print(f"\n📋 Field Information:")
            print(f"   Name:       {doctype_field['name']}")
            print(f"   Label:      {doctype_field['label']}")
            print(f"   Type:       {doctype_field['type']}")
            print(f"   Length:     {doctype_field.get('length', 'N/A')}")
            print(f"   Required:   {not doctype_field['nillable']}")

            # Check if it's a picklist
            if doctype_field['type'] == 'picklist':
                print(f"\n   📌 Picklist Values:")
                for value in doctype_field.get('picklistValues', []):
                    active = "✓" if value['active'] else "✗"
                    print(f"      {active} {value['label']} ({value['value']})")

            # Check if it's a reference (lookup/master-detail)
            if doctype_field['type'] == 'reference':
                print(f"\n   🔗 References: {', '.join(doctype_field['referenceTo'])}")

            return doctype_field

        except Exception as e:
            print(f"\n❌ Error describing field: {e}")
            return None

    def get_doctype_distribution(self):
        """Get distribution of DocType__c values using aggregate query."""
        print("\n" + "=" * 100)
        print("STEP 2: DOCTYPE DISTRIBUTION ANALYSIS")
        print("=" * 100)

        try:
            # Use aggregate query to count by DocType__c
            query = """
                SELECT DocType__c, COUNT(Id) record_count
                FROM DocListEntry__c
                GROUP BY DocType__c
                ORDER BY COUNT(Id) DESC
            """

            print(f"\n⏳ Running aggregate query...")
            print(f"   Query: {query}\n")

            result = self.sf.query_all(query)
            records = result['records']

            if not records:
                print("❌ No records found")
                return []

            print(f"✅ Found {len(records)} unique DocType values\n")

            # Calculate totals
            total_records = sum(r['record_count'] for r in records)

            print("=" * 100)
            print("DOCTYPE DISTRIBUTION")
            print("=" * 100)
            print(f"\n{'DocType__c':<40} {'Count':>15} {'Percentage':>12}")
            print("-" * 70)

            distribution = []
            for record in records:
                doctype = record['DocType__c'] or '(blank/null)'
                count = record['record_count']
                percentage = (count / total_records * 100) if total_records > 0 else 0

                distribution.append({
                    'doctype': doctype,
                    'count': count,
                    'percentage': percentage
                })

                print(f"{doctype:<40} {count:>15,} {percentage:>11.2f}%")

            print("-" * 70)
            print(f"{'TOTAL':<40} {total_records:>15,} {100.0:>11.2f}%")

            return distribution

        except Exception as e:
            print(f"\n❌ Error querying DocType distribution: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_doctype_by_account_sample(self):
        """Get sample of DocType usage by account (top 10 accounts)."""
        print("\n" + "=" * 100)
        print("STEP 3: DOCTYPE BY ACCOUNT (Top 10 Accounts)")
        print("=" * 100)

        try:
            # First, get top 10 accounts by file count
            query = """
                SELECT Account__c, COUNT(Id) file_count
                FROM DocListEntry__c
                WHERE Account__c != NULL
                GROUP BY Account__c
                ORDER BY COUNT(Id) DESC
                LIMIT 10
            """

            print(f"\n⏳ Getting top 10 accounts...")
            result = self.sf.query_all(query)
            top_accounts = result['records']

            if not top_accounts:
                print("❌ No accounts found")
                return

            print(f"✅ Analyzing DocType distribution for top 10 accounts\n")

            for i, acc_data in enumerate(top_accounts, 1):
                account_id = acc_data['Account__c']
                total_files = acc_data['file_count']

                # Get account name
                try:
                    account = self.sf.Account.get(account_id)
                    account_name = account['Name']
                except:
                    account_name = 'Unknown'

                print(f"\n{i}. Account: {account_name} ({account_id})")
                print(f"   Total Files: {total_files:,}")
                print(f"   DocType Breakdown:")

                # Get DocType distribution for this account
                doctype_query = f"""
                    SELECT DocType__c, COUNT(Id) record_count
                    FROM DocListEntry__c
                    WHERE Account__c = '{account_id}'
                    GROUP BY DocType__c
                    ORDER BY COUNT(Id) DESC
                    LIMIT 5
                """

                doctype_result = self.sf.query_all(doctype_query)

                for doc_record in doctype_result['records']:
                    doctype = doc_record['DocType__c'] or '(blank/null)'
                    count = doc_record['record_count']
                    pct = (count / total_files * 100) if total_files > 0 else 0
                    print(f"      - {doctype:<30} {count:>8,} ({pct:>5.1f}%)")

        except Exception as e:
            print(f"\n❌ Error analyzing by account: {e}")
            import traceback
            traceback.print_exc()

    def analyze_null_doctypes(self):
        """Analyze records with NULL/blank DocType__c."""
        print("\n" + "=" * 100)
        print("STEP 4: NULL/BLANK DOCTYPE ANALYSIS")
        print("=" * 100)

        try:
            # Count null/blank DocTypes
            query = """
                SELECT COUNT(Id) total
                FROM DocListEntry__c
                WHERE DocType__c = NULL
            """

            print(f"\n⏳ Counting NULL DocType records...")
            result = self.sf.query(query)
            null_count = result['records'][0]['total']

            # Get total count
            total_query = "SELECT COUNT(Id) total FROM DocListEntry__c"
            total_result = self.sf.query(total_query)
            total_count = total_result['records'][0]['total']

            null_pct = (null_count / total_count * 100) if total_count > 0 else 0

            print(f"\n📊 NULL DocType Analysis:")
            print(f"   Records with NULL DocType: {null_count:,} ({null_pct:.2f}%)")
            print(f"   Records with value:         {total_count - null_count:,} ({100 - null_pct:.2f}%)")
            print(f"   Total records:              {total_count:,}")

            if null_count > 0:
                print(f"\n   ⚠️  {null_pct:.1f}% of records have no DocType category")

        except Exception as e:
            print(f"\n❌ Error analyzing NULL DocTypes: {e}")

    def run_analysis(self):
        """Run complete DocType analysis."""
        print("\n" + "=" * 100)
        print("DOCTYPE ANALYSIS FOR DocListEntry__c")
        print("=" * 100)
        print("\nThis analyzes the DocType__c field to understand document categories.\n")

        # Step 1: Get field information
        field_info = self.get_doctype_field_info()

        # Step 2: Get distribution
        distribution = self.get_doctype_distribution()

        # Step 3: Analyze by account (sample)
        self.get_doctype_by_account_sample()

        # Step 4: Analyze NULL values
        self.analyze_null_doctypes()

        # Summary
        print("\n" + "=" * 100)
        print("📋 SUMMARY")
        print("=" * 100)

        if distribution:
            print(f"\n✅ Total DocType Categories: {len(distribution)}")
            print(f"\n📌 Top 5 Categories:")
            for i, item in enumerate(distribution[:5], 1):
                print(f"   {i}. {item['doctype']:<30} {item['count']:>10,} records ({item['percentage']:.1f}%)")

            # Check if there's a dominant category
            if distribution and distribution[0]['percentage'] > 50:
                print(f"\n⚠️  Note: '{distribution[0]['doctype']}' represents {distribution[0]['percentage']:.1f}% of all documents")

        print("\n" + "=" * 100)
        print("✅ ANALYSIS COMPLETE")
        print("=" * 100)


def main():
    try:
        analyzer = DocTypeAnalyzer()
        analyzer.run_analysis()
    except KeyboardInterrupt:
        print("\n\n⚠️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
