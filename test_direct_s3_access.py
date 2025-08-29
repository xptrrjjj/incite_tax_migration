#!/usr/bin/env python3
"""
Direct S3 Access Testing Script
===============================

Tests various methods to access the known working S3 URL:
https://trackland-doc-storage.s3.us-west-2.amazonaws.com/incitetax-pdf-manager/71e92668-c08a-434d-b708-15a67a6b1c0e

Since the PDF viewer works in Salesforce, there must be a way to access these files.
This script tests different authentication and access methods.

Usage:
python test_direct_s3_access.py
"""

import os
import sys
import logging
import requests
import json
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from typing import Dict, List, Optional, Any
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


class S3AccessTester:
    """Tests various methods to access S3 files directly."""
    
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
    
    def test_comprehensive_s3_access(self, test_url: str) -> Dict:
        """Test comprehensive S3 access methods with the known working URL."""
        self.logger.info(f"🔍 Testing comprehensive S3 access for: {test_url}")
        
        test_results = {
            'test_url': test_url,
            'test_timestamp': datetime.now().isoformat(),
            'methods': []
        }
        
        # Method 1: Direct access (no authentication)
        try:
            self.logger.info("📄 Method 1: Direct access (no auth)")
            response = requests.get(test_url, timeout=30, allow_redirects=True)
            
            test_results['methods'].append({
                'method': 'Direct Access (No Auth)',
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'content_length': len(response.content) if response.content else 0,
                'content_type': response.headers.get('Content-Type', ''),
                'final_url': response.url,
                'redirect_count': len(response.history),
                'success': response.status_code == 200 and len(response.content) > 100,
                'error_details': response.text[:500] if response.status_code != 200 else None
            })
            
        except Exception as e:
            test_results['methods'].append({
                'method': 'Direct Access (No Auth)',
                'error': str(e)
            })
        
        # Method 2: With Salesforce session token
        try:
            self.logger.info("📄 Method 2: Salesforce session token")
            headers = {
                'Authorization': f'Bearer {self.sf.session_id}',
                'User-Agent': 'simple-salesforce/1.0'
            }
            
            response = requests.get(test_url, headers=headers, timeout=30, allow_redirects=True)
            
            test_results['methods'].append({
                'method': 'Salesforce Bearer Token',
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'content_length': len(response.content) if response.content else 0,
                'content_type': response.headers.get('Content-Type', ''),
                'final_url': response.url,
                'redirect_count': len(response.history),
                'success': response.status_code == 200 and len(response.content) > 100,
                'error_details': response.text[:500] if response.status_code != 200 else None
            })
            
        except Exception as e:
            test_results['methods'].append({
                'method': 'Salesforce Bearer Token',
                'error': str(e)
            })
        
        # Method 3: With various user agents
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (compatible; Salesforce; +http://www.salesforce.com)',
            'Salesforce/1.0 (+https://www.salesforce.com)',
            'TracklandDocumentViewer/1.0'
        ]
        
        for user_agent in user_agents:
            try:
                self.logger.info(f"📄 Method 3: User Agent: {user_agent[:30]}...")
                headers = {
                    'User-Agent': user_agent,
                    'Accept': 'application/pdf,*/*'
                }
                
                response = requests.get(test_url, headers=headers, timeout=30, allow_redirects=True)
                
                if response.status_code == 200 and len(response.content) > 100:
                    test_results['methods'].append({
                        'method': f'User Agent: {user_agent[:50]}...',
                        'status_code': response.status_code,
                        'content_length': len(response.content),
                        'content_type': response.headers.get('Content-Type', ''),
                        'success': True
                    })
                    break  # Found a working user agent
                    
            except Exception as e:
                continue  # Try next user agent
        
        # Method 4: Check if URL might be a redirect or proxy
        try:
            self.logger.info("📄 Method 4: HEAD request analysis")
            head_response = requests.head(test_url, timeout=30, allow_redirects=False)
            
            test_results['methods'].append({
                'method': 'HEAD Request Analysis',
                'status_code': head_response.status_code,
                'headers': dict(head_response.headers),
                'redirect_location': head_response.headers.get('Location'),
                'cache_control': head_response.headers.get('Cache-Control'),
                'expires': head_response.headers.get('Expires')
            })
            
        except Exception as e:
            test_results['methods'].append({
                'method': 'HEAD Request Analysis',
                'error': str(e)
            })
        
        # Method 5: Try with different HTTP methods
        http_methods = ['GET', 'POST', 'OPTIONS']
        
        for method in http_methods:
            try:
                self.logger.info(f"📄 Method 5: HTTP {method}")
                
                if method == 'GET':
                    continue  # Already tested above
                
                response = requests.request(method, test_url, timeout=30, allow_redirects=True)
                
                test_results['methods'].append({
                    'method': f'HTTP {method}',
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'content_length': len(response.content) if response.content else 0,
                    'success': response.status_code == 200 and len(response.content) > 100
                })
                
            except Exception as e:
                test_results['methods'].append({
                    'method': f'HTTP {method}',
                    'error': str(e)
                })
        
        # Method 6: Try to access via Salesforce proxy
        try:
            self.logger.info("📄 Method 6: Salesforce proxy attempt")
            
            # Try various Salesforce proxy patterns
            proxy_patterns = [
                f"{self.sf.base_url}servlet/servlet.FileDownload?file=",
                f"{self.sf.base_url}sfc/servlet.shepherd/document/download/",
                f"{self.sf.base_url}services/data/v59.0/sobjects/ContentVersion/",
                f"{self.sf.base_url}services/proxy?url="
            ]
            
            for pattern in proxy_patterns:
                try:
                    proxy_url = f"{pattern}{test_url}"
                    headers = {
                        'Authorization': f'Bearer {self.sf.session_id}'
                    }
                    
                    proxy_response = requests.get(proxy_url, headers=headers, timeout=15)
                    
                    if proxy_response.status_code == 200 and len(proxy_response.content) > 100:
                        test_results['methods'].append({
                            'method': f'Salesforce Proxy: {pattern}',
                            'status_code': proxy_response.status_code,
                            'content_length': len(proxy_response.content),
                            'content_type': proxy_response.headers.get('Content-Type', ''),
                            'success': True
                        })
                        break
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            test_results['methods'].append({
                'method': 'Salesforce Proxy',
                'error': str(e)
            })
        
        return test_results
    
    def test_url_variations(self, base_url: str) -> Dict:
        """Test variations of the URL to see if any work."""
        self.logger.info("🔍 Testing URL variations...")
        
        variations = []
        
        # Parse the original URL
        parsed = urlparse(base_url)
        
        # Test URL variations
        url_variations = [
            base_url,  # Original
            base_url.replace('https://', 'http://'),  # HTTP instead of HTTPS
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}",  # Remove query params if any
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}?t={int(time.time())}",  # Add timestamp
            f"{parsed.scheme}://{parsed.netloc}{parsed.path}?download=1",  # Add download flag
        ]
        
        for variation in url_variations:
            try:
                response = requests.get(variation, timeout=15, allow_redirects=True)
                variations.append({
                    'url': variation,
                    'status_code': response.status_code,
                    'content_length': len(response.content) if response.content else 0,
                    'content_type': response.headers.get('Content-Type', ''),
                    'success': response.status_code == 200 and len(response.content) > 100
                })
                
            except Exception as e:
                variations.append({
                    'url': variation,
                    'error': str(e)
                })
        
        return {'variations': variations}
    
    def get_additional_test_urls(self) -> List[str]:
        """Get additional test URLs from DocListEntry records."""
        try:
            self.logger.info("🔍 Getting additional test URLs...")
            
            query = """
                SELECT Id, Name, Document__c
                FROM DocListEntry__c
                WHERE Document__c != NULL
                AND Document__c LIKE '%trackland-doc-storage%'
                LIMIT 5
            """
            
            result = self.sf.query(query)
            return [r['Document__c'] for r in result['records'] if r.get('Document__c')]
            
        except Exception as e:
            self.logger.error(f"Error getting additional test URLs: {e}")
            return []
    
    def comprehensive_analysis(self) -> Dict:
        """Perform comprehensive S3 access analysis."""
        self.logger.info("🔍 Starting comprehensive S3 access analysis...")
        
        # Known working URL from previous analysis
        test_url = "https://trackland-doc-storage.s3.us-west-2.amazonaws.com/incitetax-pdf-manager/71e92668-c08a-434d-b708-15a67a6b1c0e"
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'primary_test': {},
            'url_variations': {},
            'additional_urls_tested': []
        }
        
        # Test primary URL comprehensively
        analysis_results['primary_test'] = self.test_comprehensive_s3_access(test_url)
        
        # Test URL variations
        analysis_results['url_variations'] = self.test_url_variations(test_url)
        
        # Test additional URLs
        additional_urls = self.get_additional_test_urls()
        for additional_url in additional_urls[:2]:  # Test 2 additional URLs
            if additional_url != test_url:
                additional_test = self.test_comprehensive_s3_access(additional_url)
                analysis_results['additional_urls_tested'].append(additional_test)
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        print("\n" + "=" * 80)
        print("DIRECT S3 ACCESS TESTING RESULTS")
        print("=" * 80)
        
        # Primary test results
        primary_test = analysis.get('primary_test', {})
        if primary_test:
            print(f"\n🎯 PRIMARY URL TEST")
            print(f"URL: {primary_test.get('test_url', '')}")
            print("-" * 50)
            
            methods = primary_test.get('methods', [])
            successful_methods = [m for m in methods if m.get('success')]
            
            print(f"Methods tested: {len(methods)}")
            print(f"Successful methods: {len(successful_methods)}")
            
            if successful_methods:
                print(f"\n✅ SUCCESSFUL ACCESS METHODS:")
                for method in successful_methods:
                    print(f"  🔥 {method['method']}")
                    print(f"     Status: {method['status_code']}")
                    print(f"     Content: {method['content_length']} bytes")
                    print(f"     Type: {method.get('content_type', 'Unknown')}")
                    if method.get('redirect_count', 0) > 0:
                        print(f"     Redirects: {method['redirect_count']}")
                    print()
            else:
                print(f"\n❌ NO SUCCESSFUL METHODS FOUND")
                
                # Show error details for failed methods
                for method in methods[:3]:  # Show first 3 failures
                    if not method.get('success') and not method.get('error'):
                        print(f"  ❌ {method['method']}")
                        print(f"     Status: {method.get('status_code', 'N/A')}")
                        if method.get('error_details'):
                            print(f"     Error: {method['error_details'][:200]}...")
                        print()
        
        # URL variations test
        variations = analysis.get('url_variations', {}).get('variations', [])
        if variations:
            print(f"\n🔄 URL VARIATIONS TEST")
            print("-" * 50)
            
            successful_variations = [v for v in variations if v.get('success')]
            if successful_variations:
                print(f"✅ Working URL variations:")
                for var in successful_variations:
                    print(f"  • {var['url']}")
                    print(f"    Content: {var['content_length']} bytes")
            else:
                print(f"❌ No URL variations worked")
        
        # Additional URLs tested
        additional_tests = analysis.get('additional_urls_tested', [])
        if additional_tests:
            print(f"\n📊 ADDITIONAL URLS TESTED: {len(additional_tests)}")
            print("-" * 50)
            
            for i, test in enumerate(additional_tests, 1):
                successful_methods = [m for m in test.get('methods', []) if m.get('success')]
                print(f"URL {i}: {len(successful_methods)} successful methods")
                if successful_methods:
                    print(f"  ✅ Working: {successful_methods[0]['method']}")
        
        # Final conclusions and recommendations
        print("\n" + "=" * 80)
        print("🎯 CONCLUSIONS & RECOMMENDATIONS")
        print("=" * 80)
        
        # Analyze all results
        all_successful_methods = []
        
        # From primary test
        if primary_test.get('methods'):
            all_successful_methods.extend([m for m in primary_test['methods'] if m.get('success')])
        
        # From additional tests
        for test in additional_tests:
            if test.get('methods'):
                all_successful_methods.extend([m for m in test['methods'] if m.get('success')])
        
        if all_successful_methods:
            print(f"✅ BREAKTHROUGH: Found {len(all_successful_methods)} working access methods!")
            
            # Group by method type
            method_types = {}
            for method in all_successful_methods:
                method_name = method['method'].split(':')[0].strip()
                if method_name not in method_types:
                    method_types[method_name] = []
                method_types[method_name].append(method)
            
            print(f"\n🔧 IMPLEMENTATION STRATEGY:")
            for method_type, methods in method_types.items():
                print(f"  • Use {method_type} method")
                print(f"    Success rate: {len(methods)} files")
                example = methods[0]
                print(f"    Content size: {example.get('content_length', 0)} bytes")
                print(f"    Content type: {example.get('content_type', 'Unknown')}")
            
            print(f"\n💡 BACKUP SCRIPT UPDATE:")
            print(f"  1. Implement working authentication method in backup script")
            print(f"  2. Update download_file() method to use successful approach")
            print(f"  3. Test with remaining 1.3M+ files")
            
        else:
            print(f"❌ NO WORKING ACCESS METHODS FOUND")
            print(f"💡 NEXT STEPS:")
            print(f"  1. The PDF viewer in Salesforce may be using a different mechanism")
            print(f"  2. Files might be accessed through a browser-based proxy")
            print(f"  3. Consider browser developer tools inspection")
            print(f"  4. May need pre-signed URLs or special AWS credentials")
            print(f"  5. Check if files are publicly accessible with different timing")
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("Direct S3 Access Testing")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        tester = S3AccessTester(logger)
        
        if not tester.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = tester.comprehensive_analysis()
        tester.print_analysis_results(analysis)
        
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