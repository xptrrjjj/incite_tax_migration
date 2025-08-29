#!/usr/bin/env python3
"""
Static Resource Analysis Script
===============================

Analyzes the TL_PDF_Editor static resource to understand how it accesses S3 files.
We discovered the PDF viewer uses an iframe loading:
https://incitetax.lightning.force.com/resource/1748037284000/TL_PDF_Editor/index.html

Usage:
python analyze_static_resource.py
"""

import os
import sys
import logging
import requests
import json
import re
import zipfile
import tempfile
from datetime import datetime
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


class StaticResourceAnalyzer:
    """Analyzes the TL_PDF_Editor static resource to find S3 access patterns."""
    
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
    
    def download_static_resource(self, resource_name: str = "TL_PDF_Editor") -> Optional[bytes]:
        """Download the TL_PDF_Editor static resource."""
        try:
            self.logger.info(f"📦 Downloading static resource: {resource_name}")
            
            # Find the static resource
            static_query = f"""
                SELECT Id, Name, NamespacePrefix, ContentType, BodyLength,
                       Body, Description
                FROM StaticResource
                WHERE Name = '{resource_name}'
            """
            
            result = self.sf.query(static_query)
            if not result['records']:
                self.logger.error(f"❌ Static resource {resource_name} not found")
                return None
            
            resource_record = result['records'][0]
            
            # Get resource details
            resource_info = {
                'id': resource_record['Id'],
                'name': resource_record['Name'],
                'namespace': resource_record.get('NamespacePrefix'),
                'content_type': resource_record.get('ContentType'),
                'body_length': resource_record.get('BodyLength'),
                'description': resource_record.get('Description')
            }
            
            self.logger.info(f"✓ Found resource: {resource_info}")
            
            # Try to download via different methods
            download_urls = []
            
            # Method 1: Direct resource URL with timestamp (from iframe)
            if resource_record.get('NamespacePrefix'):
                download_urls.append(f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/1748037284000/{resource_record['NamespacePrefix']}__{resource_record['Name']}")
                download_urls.append(f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/{resource_record['NamespacePrefix']}__{resource_record['Name']}")
            else:
                download_urls.append(f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/1748037284000/{resource_record['Name']}")
                download_urls.append(f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/{resource_record['Name']}")
            
            # Method 2: REST API
            download_urls.append(f"{self.sf.base_url}sobjects/StaticResource/{resource_record['Id']}/Body")
            
            # Try each download method
            for download_url in download_urls:
                try:
                    self.logger.info(f"🔍 Trying download URL: {download_url}")
                    
                    headers = {
                        'Authorization': f'Bearer {self.sf.session_id}',
                        'Cookie': f"sid={self.sf.session_id}"
                    }
                    
                    response = requests.get(download_url, headers=headers, timeout=60)
                    
                    if response.status_code == 200 and response.content:
                        self.logger.info(f"✅ Successfully downloaded: {len(response.content)} bytes")
                        return response.content
                    else:
                        self.logger.debug(f"❌ Download failed: {response.status_code}")
                        
                except Exception as e:
                    self.logger.debug(f"❌ Download error: {e}")
                    continue
            
            self.logger.error("❌ All download methods failed")
            return None
            
        except Exception as e:
            self.logger.error(f"❌ Error downloading static resource: {e}")
            return None
    
    def analyze_static_resource_content(self, content: bytes) -> Dict:
        """Analyze the content of the TL_PDF_Editor static resource."""
        try:
            self.logger.info("🔍 Analyzing static resource content...")
            
            analysis = {
                'content_size': len(content),
                'content_type': 'unknown',
                'files': [],
                's3_patterns': [],
                'api_patterns': [],
                'authentication_patterns': [],
                'key_files': {}
            }
            
            # Determine if it's a ZIP file
            if content.startswith(b'PK'):
                analysis['content_type'] = 'zip'
                return self.analyze_zip_content(content, analysis)
            else:
                analysis['content_type'] = 'single_file'
                return self.analyze_single_file_content(content, analysis)
                
        except Exception as e:
            self.logger.error(f"❌ Error analyzing content: {e}")
            return {'error': str(e)}
    
    def analyze_zip_content(self, zip_content: bytes, analysis: Dict) -> Dict:
        """Analyze ZIP file content (common for static resources)."""
        try:
            self.logger.info("📦 Analyzing ZIP content...")
            
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(zip_content)
                temp_file.flush()
                
                with zipfile.ZipFile(temp_file.name, 'r') as zip_file:
                    file_list = zip_file.namelist()
                    analysis['files'] = file_list
                    
                    self.logger.info(f"✓ Found {len(file_list)} files in ZIP")
                    
                    # Look for key files
                    key_files = ['index.html', 'app.js', 'main.js', 'pdf.worker.js', 'config.js']
                    
                    for filename in file_list:
                        # Check if it's a key file
                        basename = os.path.basename(filename).lower()
                        if any(key in basename for key in key_files):
                            try:
                                file_content = zip_file.read(filename).decode('utf-8', errors='ignore')
                                analysis['key_files'][filename] = {
                                    'size': len(file_content),
                                    'content': file_content
                                }
                                self.logger.info(f"✓ Extracted key file: {filename} ({len(file_content)} chars)")
                            except Exception as e:
                                self.logger.debug(f"Could not read {filename}: {e}")
                        
                        # Also extract JS files that might contain S3 logic
                        if filename.endswith('.js') and len(filename.split('/')) <= 2:  # Top level JS files
                            try:
                                file_content = zip_file.read(filename).decode('utf-8', errors='ignore')
                                if any(keyword in file_content.lower() for keyword in ['s3', 'aws', 'document', 'url', 'download']):
                                    analysis['key_files'][filename] = {
                                        'size': len(file_content),
                                        'content': file_content
                                    }
                                    self.logger.info(f"✓ Extracted relevant JS file: {filename}")
                            except Exception as e:
                                self.logger.debug(f"Could not read {filename}: {e}")
                    
                    # Analyze all extracted files for patterns
                    self.extract_patterns_from_files(analysis)
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing ZIP: {e}")
            analysis['error'] = str(e)
            return analysis
    
    def analyze_single_file_content(self, content: bytes, analysis: Dict) -> Dict:
        """Analyze single file content."""
        try:
            content_str = content.decode('utf-8', errors='ignore')
            analysis['key_files']['single_file'] = {
                'size': len(content_str),
                'content': content_str
            }
            
            self.extract_patterns_from_files(analysis)
            return analysis
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing single file: {e}")
            analysis['error'] = str(e)
            return analysis
    
    def extract_patterns_from_files(self, analysis: Dict):
        """Extract S3 and authentication patterns from file contents."""
        for filename, file_data in analysis['key_files'].items():
            content = file_data['content']
            
            # Extract S3 patterns
            s3_patterns = [
                r'https?://[^/]*s3[^/]*\.amazonaws\.com[^\s"\'<>]+',
                r'trackland-doc-storage[^\s"\'<>]*',
                r'incitetax-pdf-manager[^\s"\'<>]*',
                r'presigned.*url',
                r'aws.*signature',
                r'x-amz-[^\s"\'<>]+',
                r'Bucket.*=.*["\'][^"\']+["\']'
            ]
            
            for pattern in s3_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    analysis['s3_patterns'].append({
                        'file': filename,
                        'pattern': pattern,
                        'match': match,
                        'context': self.get_context_around_pattern(content, match)
                    })
            
            # Extract API patterns
            api_patterns = [
                r'/services/apexrest/[^\s"\'<>]+',
                r'callout:[^\s"\'<>]+',
                r'fetch\s*\(\s*["\']([^"\']+)["\']',
                r'XMLHttpRequest\s*\(',
                r'\.get\s*\(\s*["\']([^"\']+)["\']',
                r'\.post\s*\(\s*["\']([^"\']+)["\']',
                r'action\s*:\s*["\']([^"\']+)["\']'
            ]
            
            for pattern in api_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    analysis['api_patterns'].append({
                        'file': filename,
                        'pattern': pattern,
                        'match': match,
                        'context': self.get_context_around_pattern(content, str(match))
                    })
            
            # Extract authentication patterns
            auth_patterns = [
                r'Authorization["\']?\s*:\s*["\'][^"\']+["\']',
                r'Bearer\s+[^\s"\'<>]+',
                r'session[Ii]d["\']?\s*:\s*["\'][^"\']+["\']',
                r'token["\']?\s*:\s*["\'][^"\']+["\']',
                r'credential[s]?["\']?\s*:\s*["\'][^"\']+["\']',
                r'key["\']?\s*:\s*["\'][^"\']+["\']'
            ]
            
            for pattern in auth_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    analysis['authentication_patterns'].append({
                        'file': filename,
                        'pattern': pattern,
                        'match': match,
                        'context': self.get_context_around_pattern(content, str(match))
                    })
    
    def get_context_around_pattern(self, content: str, pattern_match: str, context_lines: int = 3) -> str:
        """Get context lines around a pattern match."""
        try:
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                if pattern_match in line:
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    
                    context_lines_list = []
                    for j in range(start, end):
                        marker = " → " if j == i else "   "
                        context_lines_list.append(f"{j+1:3d}{marker}{lines[j]}")
                    
                    return '\n'.join(context_lines_list)
            
            return f"Pattern found but context extraction failed: {pattern_match[:100]}"
            
        except Exception as e:
            return f"Context extraction error: {e}"
    
    def test_resource_access(self) -> Dict:
        """Test direct access to the TL_PDF_Editor resource."""
        try:
            self.logger.info("🔍 Testing resource access methods...")
            
            # URLs to test (from the iframe discovery)
            test_urls = [
                f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/1748037284000/TL_PDF_Editor/index.html",
                f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/TL_PDF_Editor/index.html",
                f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/1748037284000/TL_PDF_Editor",
                f"{self.sf.base_url.replace('/services/data/v59.0/', '')}resource/TL_PDF_Editor"
            ]
            
            access_results = []
            
            for url in test_urls:
                try:
                    self.logger.info(f"Testing access: {url}")
                    
                    headers = {
                        'Cookie': f"sid={self.sf.session_id}",
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    response = requests.get(url, headers=headers, timeout=30)
                    
                    result = {
                        'url': url,
                        'status_code': response.status_code,
                        'content_type': response.headers.get('Content-Type'),
                        'content_length': len(response.content) if response.content else 0,
                        'success': response.status_code == 200
                    }
                    
                    if response.status_code == 200 and response.content:
                        # Check if it's HTML content
                        if 'text/html' in response.headers.get('Content-Type', ''):
                            result['content_preview'] = response.text[:1000] + "..." if len(response.text) > 1000 else response.text
                        else:
                            result['content_preview'] = f"Binary content: {len(response.content)} bytes"
                    
                    access_results.append(result)
                    
                except Exception as e:
                    access_results.append({
                        'url': url,
                        'error': str(e)
                    })
            
            return {'access_tests': access_results}
            
        except Exception as e:
            self.logger.error(f"❌ Error testing resource access: {e}")
            return {'error': str(e)}
    
    def comprehensive_analysis(self) -> Dict:
        """Perform comprehensive analysis of the TL_PDF_Editor static resource."""
        self.logger.info("🔍 Starting comprehensive static resource analysis...")
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'resource_name': 'TL_PDF_Editor',
            'download_success': False,
            'content_analysis': {},
            'access_tests': {}
        }
        
        # Download the static resource
        resource_content = self.download_static_resource()
        
        if resource_content:
            analysis_results['download_success'] = True
            analysis_results['content_analysis'] = self.analyze_static_resource_content(resource_content)
        
        # Test resource access methods
        analysis_results['access_tests'] = self.test_resource_access()
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        print("\n" + "=" * 80)
        print("STATIC RESOURCE ANALYSIS - TL_PDF_EDITOR")
        print("=" * 80)
        
        resource_name = analysis.get('resource_name')
        download_success = analysis.get('download_success')
        
        print(f"Resource: {resource_name}")
        print(f"Download Success: {'✅' if download_success else '❌'}")
        
        # Content Analysis
        content_analysis = analysis.get('content_analysis', {})
        if content_analysis and 'error' not in content_analysis:
            print(f"\n📦 CONTENT ANALYSIS")
            print("-" * 50)
            print(f"Content Type: {content_analysis.get('content_type')}")
            print(f"Content Size: {content_analysis.get('content_size', 0):,} bytes")
            
            files = content_analysis.get('files', [])
            if files:
                print(f"Files in Archive: {len(files)}")
                
                # Show important files
                important_files = [f for f in files if any(key in f.lower() for key in ['index.html', 'app.js', 'main.js', 'config.js'])]
                if important_files:
                    print(f"Important Files:")
                    for file in important_files:
                        print(f"  • {file}")
            
            # Key Files Analysis
            key_files = content_analysis.get('key_files', {})
            if key_files:
                print(f"\n📄 KEY FILES EXTRACTED: {len(key_files)}")
                print("-" * 30)
                
                for filename, file_data in key_files.items():
                    print(f"🔍 {filename} ({file_data['size']} chars)")
                    
                    # Show preview of important files
                    if filename.endswith('.html') or 'index' in filename.lower():
                        content_preview = file_data['content'][:500] + "..." if len(file_data['content']) > 500 else file_data['content']
                        print(f"   Preview: {content_preview}")
                    
                    print()
            
            # S3 Patterns
            s3_patterns = content_analysis.get('s3_patterns', [])
            if s3_patterns:
                print(f"\n🌐 S3 PATTERNS FOUND: {len(s3_patterns)}")
                print("-" * 30)
                
                for pattern in s3_patterns[:5]:  # Show top 5
                    print(f"📍 File: {pattern['file']}")
                    print(f"   Match: {pattern['match']}")
                    print(f"   Context:")
                    for line in pattern['context'].split('\n')[:3]:
                        print(f"     {line}")
                    print()
            
            # API Patterns  
            api_patterns = content_analysis.get('api_patterns', [])
            if api_patterns:
                print(f"\n📞 API PATTERNS FOUND: {len(api_patterns)}")
                print("-" * 30)
                
                for pattern in api_patterns[:5]:  # Show top 5
                    print(f"📍 File: {pattern['file']}")
                    print(f"   Match: {pattern['match']}")
                    print(f"   Context:")
                    for line in pattern['context'].split('\n')[:3]:
                        print(f"     {line}")
                    print()
            
            # Authentication Patterns
            auth_patterns = content_analysis.get('authentication_patterns', [])
            if auth_patterns:
                print(f"\n🔐 AUTHENTICATION PATTERNS FOUND: {len(auth_patterns)}")
                print("-" * 30)
                
                for pattern in auth_patterns[:3]:  # Show top 3
                    print(f"📍 File: {pattern['file']}")
                    print(f"   Match: {pattern['match']}")
                    print()
        
        # Access Tests
        access_tests = analysis.get('access_tests', {}).get('access_tests', [])
        if access_tests:
            successful_access = [t for t in access_tests if t.get('success')]
            
            print(f"\n🔍 RESOURCE ACCESS TESTS: {len(access_tests)} tested, {len(successful_access)} successful")
            print("-" * 50)
            
            if successful_access:
                print("✅ SUCCESSFUL ACCESS METHODS:")
                for test in successful_access:
                    print(f"  • {test['url']}")
                    print(f"    Status: {test['status_code']}")
                    print(f"    Type: {test.get('content_type', 'Unknown')}")
                    print(f"    Size: {test.get('content_length', 0)} bytes")
                    if test.get('content_preview'):
                        print(f"    Preview: {test['content_preview'][:200]}...")
                    print()
        
        # Final Breakthrough Analysis
        print("\n" + "=" * 80)
        print("🎯 BREAKTHROUGH ANALYSIS - PDF VIEWER MECHANISM REVEALED")
        print("=" * 80)
        
        breakthroughs = []
        
        if download_success and content_analysis.get('key_files'):
            breakthroughs.append("✅ Successfully extracted PDF viewer application source code")
            
        if content_analysis.get('s3_patterns'):
            breakthroughs.append(f"🌐 Found {len(content_analysis['s3_patterns'])} S3-related patterns in source code")
            
        if content_analysis.get('api_patterns'):
            breakthroughs.append(f"📞 Found {len(content_analysis['api_patterns'])} API call patterns")
            
        if content_analysis.get('authentication_patterns'):
            breakthroughs.append(f"🔐 Found {len(content_analysis['authentication_patterns'])} authentication patterns")
        
        # Check for successful access to index.html
        if access_tests:
            html_access = [t for t in access_tests if t.get('success') and 'index.html' in t.get('url', '')]
            if html_access:
                breakthroughs.append("📄 Successfully accessed PDF viewer HTML - can analyze live application")
        
        if breakthroughs:
            print("🔥 MAJOR BREAKTHROUGHS:")
            for breakthrough in breakthroughs:
                print(breakthrough)
            
            print(f"\n💡 IMPLEMENTATION STRATEGY:")
            print("1. Analyze extracted source code to understand file access mechanism")
            print("2. Reverse engineer JavaScript logic for S3 authentication") 
            print("3. Implement same authentication method in Python backup script")
            print("4. Test with sample files before full 1.3M+ file migration")
            
        else:
            print("❌ No major breakthroughs - PDF viewer mechanism still unclear")
            print("💡 Next steps: Manual browser inspection with developer tools")
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("Static Resource Analysis - TL_PDF_Editor")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        analyzer = StaticResourceAnalyzer(logger)
        
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