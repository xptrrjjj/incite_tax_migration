#!/usr/bin/env python3
"""
S3 Access Pattern Analysis
==========================

Analyzes the S3 access patterns for DocListEntry__c files to understand:
1. URL structure and patterns
2. How Trackland authenticates S3 access
3. Potential pre-signed URL generation
4. Alternative access methods

Usage:
python analyze_s3_access.py
"""

import os
import sys
import logging
import requests
import re
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from typing import Dict, List, Optional, Tuple
from simple_salesforce import Salesforce
from simple_salesforce.exceptions import SalesforceError

# Import configuration
try:
    from config import SALESFORCE_CONFIG, MIGRATION_CONFIG
    print("✓ Using configuration from config.py")
except ImportError:
    print("❌ config.py not found. Please copy config_template.py to config.py and update it.")
    sys.exit(1)


def setup_logging() -> logging.Logger:
    """Set up logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    
    logger = logging.getLogger(__name__)
    return logger


class S3AccessAnalyzer:
    """Analyzes S3 access patterns and authentication methods."""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.sf = None
        
    def authenticate(self) -> bool:
        """Authenticate with Salesforce."""
        try:
            self.sf = Salesforce(
                username=SALESFORCE_CONFIG["username"],
                password=SALESFORCE_CONFIG["password"],
                security_token=SALESFORCE_CONFIG["security_token"],
                domain=SALESFORCE_CONFIG["domain"]
            )
            
            self.logger.info("✓ Successfully authenticated with Salesforce")
            return True
            
        except SalesforceError as e:
            self.logger.error(f"❌ Salesforce authentication failed: {e}")
            return False
        except Exception as e:
            self.logger.error(f"❌ Unexpected error during Salesforce authentication: {e}")
            return False
    
    def get_detailed_file_samples(self, limit: int = 20) -> List[Dict]:
        """Get detailed file samples with all relevant fields."""
        try:
            self.logger.info(f"📄 Getting {limit} detailed file samples...")
            
            query = f"""
                SELECT Id, Name, Document__c, Identifier__c, 
                       Account__c, Account__r.Name,
                       CreatedDate, LastModifiedDate,
                       DocType__c, Source__c, Verified__c
                FROM DocListEntry__c
                WHERE Document__c != NULL 
                AND Document__c LIKE '%trackland-doc-storage%'
                AND IsDeleted = FALSE
                ORDER BY CreatedDate DESC
                LIMIT {limit}
            """
            
            result = self.sf.query(query)
            return result['records']
            
        except Exception as e:
            self.logger.error(f"❌ Error getting file samples: {e}")
            return []
    
    def analyze_url_patterns(self, records: List[Dict]) -> Dict:
        """Analyze URL patterns to understand structure and authentication."""
        patterns = {
            'base_domains': {},
            'path_patterns': {},
            'query_parameters': {},
            'url_components': []
        }
        
        for record in records:
            url = record.get('Document__c', '')
            if not url:
                continue
                
            # Parse URL components
            parsed = urlparse(url)
            
            # Track base domains
            base_domain = f"{parsed.scheme}://{parsed.netloc}"
            patterns['base_domains'][base_domain] = patterns['base_domains'].get(base_domain, 0) + 1
            
            # Track path patterns
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) >= 2:
                path_pattern = f"{path_parts[0]}/[identifier]"
                patterns['path_patterns'][path_pattern] = patterns['path_patterns'].get(path_pattern, 0) + 1
            
            # Track query parameters (might contain auth info)
            if parsed.query:
                query_params = parse_qs(parsed.query)
                for param_name in query_params.keys():
                    patterns['query_parameters'][param_name] = patterns['query_parameters'].get(param_name, 0) + 1
            
            # Store component analysis
            url_analysis = {
                'original_url': url,
                'scheme': parsed.scheme,
                'domain': parsed.netloc,
                'path': parsed.path,
                'query': parsed.query,
                'fragment': parsed.fragment,
                'identifier': record.get('Identifier__c'),
                'filename': record.get('Name'),
                'doc_type': record.get('DocType__c')
            }
            patterns['url_components'].append(url_analysis)
        
        return patterns
    
    def test_access_methods(self, sample_urls: List[str], limit: int = 3) -> Dict:
        """Test different access methods on sample URLs."""
        access_results = {
            'direct_access': [],
            'salesforce_auth': [],
            'head_requests': [],
            'redirect_analysis': []
        }
        
        # Test only a few URLs to avoid being blocked
        test_urls = sample_urls[:limit]
        
        for url in test_urls:
            self.logger.info(f"🔍 Testing access methods for: {url[:80]}...")
            
            # Method 1: Direct access
            try:
                response = requests.get(url, timeout=10, allow_redirects=False)
                access_results['direct_access'].append({
                    'url': url,
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'content_length': len(response.content) if response.content else 0,
                    'redirects_to': response.headers.get('Location')
                })
            except Exception as e:
                access_results['direct_access'].append({
                    'url': url,
                    'error': str(e)
                })
            
            # Method 2: HEAD request (faster, less data)
            try:
                head_response = requests.head(url, timeout=10, allow_redirects=False)
                access_results['head_requests'].append({
                    'url': url,
                    'status_code': head_response.status_code,
                    'headers': dict(head_response.headers),
                    'redirects_to': head_response.headers.get('Location')
                })
            except Exception as e:
                access_results['head_requests'].append({
                    'url': url,
                    'error': str(e)
                })
            
            # Method 3: With Salesforce authentication
            try:
                sf_headers = {
                    'Authorization': f'Bearer {self.sf.session_id}',
                    'User-Agent': 'simple-salesforce/1.0'
                }
                sf_response = requests.get(url, headers=sf_headers, timeout=10, allow_redirects=False)
                access_results['salesforce_auth'].append({
                    'url': url,
                    'status_code': sf_response.status_code,
                    'headers': dict(sf_response.headers),
                    'content_length': len(sf_response.content) if sf_response.content else 0,
                    'redirects_to': sf_response.headers.get('Location')
                })
            except Exception as e:
                access_results['salesforce_auth'].append({
                    'url': url,
                    'error': str(e)
                })
            
            # Method 4: Follow redirects to see final destination
            try:
                redirect_response = requests.get(url, timeout=10, allow_redirects=True)
                access_results['redirect_analysis'].append({
                    'url': url,
                    'final_url': redirect_response.url,
                    'status_code': redirect_response.status_code,
                    'redirect_history': [r.url for r in redirect_response.history],
                    'content_length': len(redirect_response.content) if redirect_response.content else 0
                })
            except Exception as e:
                access_results['redirect_analysis'].append({
                    'url': url,
                    'error': str(e)
                })
        
        return access_results
    
    def check_salesforce_file_apis(self, doclist_ids: List[str]) -> Dict:
        """Check if files can be accessed via Salesforce APIs."""
        api_results = {
            'content_document_links': [],
            'attachment_queries': [],
            'document_queries': []
        }
        
        # Test a few DocListEntry IDs
        test_ids = doclist_ids[:3]
        
        for doclist_id in test_ids:
            self.logger.info(f"🔍 Testing Salesforce APIs for DocListEntry: {doclist_id}")
            
            # Check ContentDocumentLink
            try:
                content_query = f"""
                    SELECT Id, ContentDocumentId, LinkedEntityId,
                           ContentDocument.Title, ContentDocument.FileType,
                           ContentDocument.ContentSize, ContentDocument.CreatedDate,
                           ContentDocument.LatestPublishedVersionId
                    FROM ContentDocumentLink
                    WHERE LinkedEntityId = '{doclist_id}'
                """
                content_result = self.sf.query(content_query)
                api_results['content_document_links'].append({
                    'doclist_id': doclist_id,
                    'found': len(content_result['records']) > 0,
                    'records': content_result['records']
                })
            except Exception as e:
                api_results['content_document_links'].append({
                    'doclist_id': doclist_id,
                    'error': str(e)
                })
            
            # Check for Attachments
            try:
                attachment_query = f"""
                    SELECT Id, Name, ContentType, BodyLength, CreatedDate
                    FROM Attachment
                    WHERE ParentId = '{doclist_id}'
                """
                attachment_result = self.sf.query(attachment_query)
                api_results['attachment_queries'].append({
                    'doclist_id': doclist_id,
                    'found': len(attachment_result['records']) > 0,
                    'records': attachment_result['records']
                })
            except Exception as e:
                api_results['attachment_queries'].append({
                    'doclist_id': doclist_id,
                    'error': str(e)
                })
            
            # Check for Document records
            try:
                document_query = f"""
                    SELECT Id, Name, Type, Url, FolderId, CreatedDate
                    FROM Document
                    WHERE Name LIKE '%{doclist_id}%'
                    OR Description LIKE '%{doclist_id}%'
                """
                document_result = self.sf.query(document_query)
                api_results['document_queries'].append({
                    'doclist_id': doclist_id,
                    'found': len(document_result['records']) > 0,
                    'records': document_result['records']
                })
            except Exception as e:
                api_results['document_queries'].append({
                    'doclist_id': doclist_id,
                    'error': str(e)
                })
        
        return api_results
    
    def comprehensive_analysis(self) -> Dict:
        """Perform comprehensive S3 access analysis."""
        self.logger.info("🔍 Starting comprehensive S3 access analysis...")
        
        # Get sample records
        records = self.get_detailed_file_samples(20)
        if not records:
            return {'error': 'No records found'}
        
        # Analyze URL patterns
        url_patterns = self.analyze_url_patterns(records)
        
        # Test access methods on sample URLs
        sample_urls = [r.get('Document__c') for r in records[:5] if r.get('Document__c')]
        access_tests = self.test_access_methods(sample_urls)
        
        # Test Salesforce APIs
        doclist_ids = [r.get('Id') for r in records[:3] if r.get('Id')]
        salesforce_apis = self.check_salesforce_file_apis(doclist_ids)
        
        return {
            'analysis_timestamp': datetime.now().isoformat(),
            'total_records_analyzed': len(records),
            'sample_records': records[:3],  # First 3 for reference
            'url_patterns': url_patterns,
            'access_method_tests': access_tests,
            'salesforce_api_tests': salesforce_apis
        }
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        if 'error' in analysis:
            self.logger.error(f"Analysis failed: {analysis['error']}")
            return
        
        print("\n" + "=" * 80)
        print("S3 ACCESS PATTERN ANALYSIS")
        print("=" * 80)
        
        # URL Pattern Analysis
        url_patterns = analysis['url_patterns']
        print(f"\n🌐 URL PATTERNS ({analysis['total_records_analyzed']} files analyzed)")
        print("-" * 50)
        
        print("Base domains:")
        for domain, count in url_patterns['base_domains'].items():
            print(f"  • {domain}: {count} files")
        
        print("\nPath patterns:")
        for pattern, count in url_patterns['path_patterns'].items():
            print(f"  • {pattern}: {count} files")
        
        if url_patterns['query_parameters']:
            print("\nQuery parameters found:")
            for param, count in url_patterns['query_parameters'].items():
                print(f"  • {param}: {count} occurrences")
        else:
            print("\n❌ No query parameters found (no pre-signed URLs or tokens)")
        
        # Access Method Tests
        access_tests = analysis['access_method_tests']
        print(f"\n🔐 ACCESS METHOD TESTS")
        print("-" * 50)
        
        print("Direct access results:")
        for result in access_tests['direct_access']:
            if 'error' in result:
                print(f"  ❌ Error: {result['error']}")
            else:
                status = result['status_code']
                length = result.get('content_length', 0)
                redirect = result.get('redirects_to', 'None')
                print(f"  • Status: {status}, Length: {length}, Redirects: {redirect}")
        
        print("\nSalesforce authentication results:")
        for result in access_tests['salesforce_auth']:
            if 'error' in result:
                print(f"  ❌ Error: {result['error']}")
            else:
                status = result['status_code']
                length = result.get('content_length', 0)
                redirect = result.get('redirects_to', 'None')
                print(f"  • Status: {status}, Length: {length}, Redirects: {redirect}")
        
        print("\nRedirect analysis:")
        for result in access_tests['redirect_analysis']:
            if 'error' in result:
                print(f"  ❌ Error: {result['error']}")
            else:
                final_status = result['status_code']
                redirect_count = len(result.get('redirect_history', []))
                final_length = result.get('content_length', 0)
                print(f"  • Final status: {final_status}, Redirects: {redirect_count}, Length: {final_length}")
        
        # Salesforce API Tests
        sf_apis = analysis['salesforce_api_tests']
        print(f"\n📎 SALESFORCE API TESTS")
        print("-" * 50)
        
        cdl_found = sum(1 for r in sf_apis['content_document_links'] if r.get('found', False))
        att_found = sum(1 for r in sf_apis['attachment_queries'] if r.get('found', False))
        doc_found = sum(1 for r in sf_apis['document_queries'] if r.get('found', False))
        
        print(f"ContentDocumentLink matches: {cdl_found}")
        print(f"Attachment matches: {att_found}")
        print(f"Document matches: {doc_found}")
        
        if cdl_found > 0:
            print("\nContentDocument details found:")
            for result in sf_apis['content_document_links']:
                if result.get('found') and result.get('records'):
                    for record in result['records'][:1]:  # Show first match
                        title = record.get('ContentDocument', {}).get('Title', 'Unknown')
                        file_type = record.get('ContentDocument', {}).get('FileType', 'Unknown')
                        size = record.get('ContentDocument', {}).get('ContentSize', 0)
                        print(f"  • Title: {title}, Type: {file_type}, Size: {size}")
        
        print("\n" + "=" * 80)
        print("SUMMARY & RECOMMENDATIONS")
        print("=" * 80)
        
        # Generate recommendations based on results
        recommendations = []
        
        if url_patterns['query_parameters']:
            recommendations.append("✅ URLs contain query parameters - may include auth tokens")
        else:
            recommendations.append("❌ No query parameters - URLs appear to be direct S3 links")
        
        if cdl_found > 0:
            recommendations.append("✅ Files are also stored as ContentDocuments - use Salesforce API")
        else:
            recommendations.append("❌ No ContentDocument integration found")
        
        # Check access test results
        direct_success = any(r.get('status_code') == 200 for r in access_tests['direct_access'] if 'status_code' in r)
        sf_auth_success = any(r.get('status_code') == 200 for r in access_tests['salesforce_auth'] if 'status_code' in r)
        
        if direct_success:
            recommendations.append("✅ Direct access works - S3 bucket allows public read")
        elif sf_auth_success:
            recommendations.append("✅ Salesforce authentication works - use SF session")
        else:
            recommendations.append("❌ Neither direct nor SF auth worked - need alternative method")
        
        for rec in recommendations:
            print(rec)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("S3 Access Pattern Analysis")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        analyzer = S3AccessAnalyzer(logger)
        
        if not analyzer.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = analyzer.comprehensive_analysis()
        analyzer.print_analysis_results(analysis)
        
        return True
        
    except KeyboardInterrupt:
        logger.info("⚠️ Analysis interrupted by user")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)