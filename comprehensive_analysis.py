#!/usr/bin/env python3
"""
Comprehensive Pre-Migration Analysis Script

This script provides accurate totals for:
- Total accounts with DocListEntry records  
- Total files across all accounts
- File size estimates for storage planning
- Detailed breakdown by account

Run this BEFORE starting any migration to get accurate baseline numbers.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from simple_salesforce import Salesforce, SalesforceError
import json
from typing import Dict, List, Tuple, Optional

# Import configuration
try:
    from config import SALESFORCE_CONFIG
except ImportError:
    from config_template import SALESFORCE_CONFIG
    print("⚠️ Using config_template.py - Please copy to config.py and update with real credentials")

class ComprehensiveAnalysis:
    """Comprehensive analysis of migration scope."""
    
    def __init__(self):
        self.sf = None
        self.analysis_results = {
            'timestamp': datetime.now().isoformat(),
            'total_accounts': 0,
            'total_files': 0,
            'estimated_total_size_gb': 0,
            'account_breakdown': [],
            'summary_stats': {},
            'recommendations': []
        }
    
    def authenticate_salesforce(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            print("🔐 Authenticating with Salesforce...")
            self.sf = Salesforce(
                username=SALESFORCE_CONFIG["username"],
                password=SALESFORCE_CONFIG["password"],
                security_token=SALESFORCE_CONFIG["security_token"],
                domain=SALESFORCE_CONFIG["domain"]
            )
            print("✅ Successfully authenticated with Salesforce")
            return True
        except SalesforceError as e:
            print(f"❌ Salesforce authentication failed: {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error during Salesforce authentication: {e}")
            return False
    
    def get_total_accounts_with_files(self) -> List[Dict]:
        """Get comprehensive list of all accounts with DocListEntry records."""
        print("\n📊 Analyzing accounts with DocListEntry records...")
        
        try:
            # Get comprehensive account data with file counts
            # Note: Aggregate queries require LIMIT and manual pagination with OFFSET
            all_accounts = []
            batch_size = 2000
            offset = 0
            
            while True:
                query = f"""
                SELECT 
                    Account__c,
                    Account__r.Name,
                    COUNT(Id)
                FROM DocListEntry__c 
                WHERE Account__c != NULL 
                GROUP BY Account__c, Account__r.Name 
                ORDER BY COUNT(Id) DESC
                LIMIT {batch_size} OFFSET {offset}
                """
                
                print(f"🔍 Fetching accounts {offset+1} to {offset+batch_size}...")
                result = self.sf.query(query)
                batch_accounts = result['records']
                
                if not batch_accounts:
                    print(f"✅ No more accounts found - pagination complete")
                    break
                
                all_accounts.extend(batch_accounts)
                print(f"📊 Retrieved {len(batch_accounts)} accounts (total so far: {len(all_accounts)})")
                
                # If we got fewer than batch_size, we're done
                if len(batch_accounts) < batch_size:
                    print(f"✅ Retrieved final batch - all accounts loaded")
                    break
                
                offset += batch_size
            
            accounts = all_accounts
            
            print(f"✅ Found {len(accounts)} accounts with DocListEntry records")
            
            # Process and enrich account data
            enriched_accounts = []
            total_files = 0
            
            for i, account in enumerate(accounts, 1):
                account_id = account['Account__c']
                account_name = account['Account__r']['Name'] if account.get('Account__r') else 'Unknown Account'
                file_count = account['expr0']  # Salesforce returns COUNT() as 'expr0'
                total_files += file_count
                
                # Get sample file info for size estimation
                size_estimate = self._estimate_account_size(account_id, file_count)
                
                enriched_account = {
                    'rank': i,
                    'account_id': account_id,
                    'account_name': account_name,
                    'file_count': file_count,
                    'estimated_size_gb': size_estimate,
                    'percentage_of_total': 0  # Will calculate after we have totals
                }
                
                enriched_accounts.append(enriched_account)
                
                # Progress indicator for large datasets
                if i % 10 == 0:
                    print(f"  📈 Processed {i}/{len(accounts)} accounts...")
            
            # Calculate percentages now that we have totals
            for account in enriched_accounts:
                account['percentage_of_total'] = (account['file_count'] / total_files * 100) if total_files > 0 else 0
            
            self.analysis_results['total_accounts'] = len(accounts)
            self.analysis_results['total_files'] = total_files
            self.analysis_results['account_breakdown'] = enriched_accounts
            
            return enriched_accounts
            
        except Exception as e:
            print(f"❌ Failed to analyze accounts: {e}")
            raise
    
    def _estimate_account_size(self, account_id: str, file_count: int) -> float:
        """Estimate total size for an account based on sample files."""
        try:
            # Sample up to 100 files from this account to estimate average size
            sample_query = f"""
            SELECT Id, Document__c, File_Size__c 
            FROM DocListEntry__c 
            WHERE Account__c = '{account_id}' 
            AND File_Size__c != NULL 
            LIMIT 100
            """
            
            result = self.sf.query(sample_query)
            sample_files = result['records']
            
            if not sample_files:
                # No size data available, use conservative estimate
                return file_count * 0.5  # Assume 0.5 MB per file average
            
            # Calculate average size from sample
            total_sample_size = sum(float(file.get('File_Size__c', 0)) for file in sample_files)
            avg_size_bytes = total_sample_size / len(sample_files)
            avg_size_gb = avg_size_bytes / (1024 * 1024 * 1024)  # Convert to GB
            
            # Estimate total size for account
            estimated_total_gb = avg_size_gb * file_count
            
            return round(estimated_total_gb, 2)
            
        except Exception as e:
            # If estimation fails, use conservative estimate
            print(f"⚠️ Size estimation failed for account {account_id}: {e}")
            return file_count * 0.0005  # 0.5 KB per file (very conservative)
    
    def generate_summary_statistics(self):
        """Generate summary statistics and recommendations."""
        print("\n📈 Generating summary statistics...")
        
        accounts = self.analysis_results['account_breakdown']
        total_files = self.analysis_results['total_files']
        total_accounts = self.analysis_results['total_accounts']
        total_size_gb = sum(account['estimated_size_gb'] for account in accounts)
        
        self.analysis_results['estimated_total_size_gb'] = round(total_size_gb, 2)
        
        # Calculate distribution statistics
        file_counts = [account['file_count'] for account in accounts]
        file_counts.sort(reverse=True)
        
        # Top account statistics
        top_10_files = sum(file_counts[:10]) if len(file_counts) >= 10 else sum(file_counts)
        top_50_files = sum(file_counts[:50]) if len(file_counts) >= 50 else sum(file_counts)
        
        summary_stats = {
            'largest_account_files': file_counts[0] if file_counts else 0,
            'smallest_account_files': file_counts[-1] if file_counts else 0,
            'average_files_per_account': round(total_files / total_accounts, 1) if total_accounts > 0 else 0,
            'median_files_per_account': file_counts[len(file_counts) // 2] if file_counts else 0,
            'top_10_accounts_percentage': round((top_10_files / total_files * 100), 1) if total_files > 0 else 0,
            'top_50_accounts_percentage': round((top_50_files / total_files * 100), 1) if total_files > 0 else 0,
            'accounts_with_1000_plus_files': len([c for c in file_counts if c >= 1000]),
            'accounts_with_10000_plus_files': len([c for c in file_counts if c >= 10000])
        }
        
        self.analysis_results['summary_stats'] = summary_stats
        
        # Generate recommendations
        recommendations = []
        
        if total_files > 500000:
            recommendations.append("🔶 Large dataset (500K+ files) - Strongly recommend two-phase migration approach")
        elif total_files > 100000:
            recommendations.append("🔷 Medium dataset (100K+ files) - Consider two-phase migration for safety")
        else:
            recommendations.append("🟢 Small dataset - Single-phase migration should work fine")
        
        if total_size_gb > 100:
            recommendations.append(f"💾 Large storage requirement ({total_size_gb:.1f} GB) - Ensure adequate S3 storage")
        
        if summary_stats['top_10_accounts_percentage'] > 50:
            recommendations.append("📊 Top 10 accounts contain >50% of files - Consider account-by-account processing")
        
        if summary_stats['accounts_with_10000_plus_files'] > 0:
            recommendations.append(f"⚠️ {summary_stats['accounts_with_10000_plus_files']} account(s) have 10K+ files each - Monitor these closely")
        
        self.analysis_results['recommendations'] = recommendations
    
    def print_analysis_report(self):
        """Print comprehensive analysis report to console."""
        print("\n" + "="*80)
        print("📋 COMPREHENSIVE MIGRATION ANALYSIS REPORT")
        print("="*80)
        
        # Basic totals
        print(f"\n🎯 MIGRATION SCOPE:")
        print(f"   Total Accounts with Files: {self.analysis_results['total_accounts']:,}")
        print(f"   Total Files to Migrate: {self.analysis_results['total_files']:,}")
        print(f"   Estimated Total Size: {self.analysis_results['estimated_total_size_gb']:.2f} GB")
        
        # Summary statistics
        stats = self.analysis_results['summary_stats']
        print(f"\n📊 DISTRIBUTION ANALYSIS:")
        print(f"   Largest Account: {stats['largest_account_files']:,} files")
        print(f"   Smallest Account: {stats['smallest_account_files']:,} files")
        print(f"   Average per Account: {stats['average_files_per_account']:,} files")
        print(f"   Median per Account: {stats['median_files_per_account']:,} files")
        print(f"   Top 10 Accounts: {stats['top_10_accounts_percentage']:.1f}% of all files")
        print(f"   Top 50 Accounts: {stats['top_50_accounts_percentage']:.1f}% of all files")
        print(f"   Accounts with 1,000+ files: {stats['accounts_with_1000_plus_files']}")
        print(f"   Accounts with 10,000+ files: {stats['accounts_with_10000_plus_files']}")
        
        # Top 20 accounts
        print(f"\n🏆 TOP 20 ACCOUNTS BY FILE COUNT:")
        top_20 = self.analysis_results['account_breakdown'][:20]
        for account in top_20:
            print(f"   {account['rank']:2d}. {account['account_name'][:40]:<40} | "
                  f"{account['file_count']:>7,} files | "
                  f"{account['estimated_size_gb']:>6.2f} GB | "
                  f"{account['percentage_of_total']:>5.1f}%")
        
        # Recommendations
        print(f"\n🎯 RECOMMENDATIONS:")
        for rec in self.analysis_results['recommendations']:
            print(f"   {rec}")
        
        # Migration strategy
        print(f"\n⚡ SUGGESTED MIGRATION STRATEGY:")
        total_files = self.analysis_results['total_files']
        if total_files > 1000000:
            print(f"   1. Use two-phase approach (backup-only first, then full migration)")
            print(f"   2. Process by account to manage chunk sizes")
            print(f"   3. Start with smaller accounts to test and build confidence")
            print(f"   4. Monitor progress closely - this will take significant time")
        elif total_files > 100000:
            print(f"   1. Consider two-phase approach for safety")
            print(f"   2. Use chunked processing with reasonable batch sizes")
            print(f"   3. Monitor for any authentication or rate limiting issues")
        else:
            print(f"   1. Single-phase migration should work fine")
            print(f"   2. Standard batch processing will be sufficient")
        
        print("\n" + "="*80)
    
    def save_analysis_to_file(self, filename: Optional[str] = None):
        """Save analysis results to JSON file."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"migration_analysis_{timestamp}.json"
        
        filepath = Path(filename)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(self.analysis_results, f, indent=2, default=str)
            
            print(f"\n💾 Analysis saved to: {filepath.absolute()}")
            return str(filepath.absolute())
            
        except Exception as e:
            print(f"❌ Failed to save analysis: {e}")
            return None
    
    def run_comprehensive_analysis(self) -> bool:
        """Run complete analysis workflow."""
        print("🚀 Starting Comprehensive Migration Analysis...")
        print(f"📅 Timestamp: {self.analysis_results['timestamp']}")
        
        try:
            # Step 1: Authenticate
            if not self.authenticate_salesforce():
                return False
            
            # Step 2: Get account data
            self.get_total_accounts_with_files()
            
            # Step 3: Generate statistics
            self.generate_summary_statistics()
            
            # Step 4: Print report
            self.print_analysis_report()
            
            # Step 5: Save to file
            self.save_analysis_to_file()
            
            print(f"\n✅ Comprehensive analysis completed successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Analysis failed: {e}")
            return False

def main():
    """Main execution function."""
    analyzer = ComprehensiveAnalysis()
    success = analyzer.run_comprehensive_analysis()
    
    if success:
        print(f"\n🎉 Use these numbers to:")
        print(f"   - Set accurate progress tracking in your dashboard")
        print(f"   - Plan storage requirements")
        print(f"   - Choose appropriate migration strategy")
        print(f"   - Set realistic time expectations")
        sys.exit(0)
    else:
        print(f"\n💥 Analysis failed - check configuration and connectivity")
        sys.exit(1)

if __name__ == "__main__":
    main()