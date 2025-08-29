#!/usr/bin/env python3
"""
PDF Editor Extraction Script
============================

Downloads and extracts the TL_PDF_Editor static resource to analyze the PDF viewer code.
Fixes permission issues and URL construction from the previous attempt.

Usage:
python extract_pdf_editor.py
"""

import os
import sys
import logging
import requests
import json
import re
import zipfile
import io
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


class PDFEditorExtractor:
    """Downloads and extracts the TL_PDF_Editor to understand file access."""
    
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
    
    def download_and_extract_resource(self) -> Dict:
        """Download and extract the TL_PDF_Editor static resource."""
        try:
            self.logger.info("📦 Downloading TL_PDF_Editor static resource...")
            
            # Get resource via REST API (most reliable method)
            resource_url = f"{self.sf.base_url}sobjects/StaticResource"
            
            # First, find the resource
            query_url = f"{self.sf.base_url}query/?q=SELECT Id,Name,BodyLength FROM StaticResource WHERE Name='TL_PDF_Editor'"
            
            headers = {
                'Authorization': f'Bearer {self.sf.session_id}',
                'Content-Type': 'application/json'
            }
            
            query_response = requests.get(query_url, headers=headers)
            query_data = query_response.json()
            
            if not query_data.get('records'):
                return {'error': 'TL_PDF_Editor resource not found'}
            
            resource_id = query_data['records'][0]['Id']
            body_length = query_data['records'][0]['BodyLength']
            
            self.logger.info(f"✓ Found resource: {resource_id} ({body_length} bytes)")
            
            # Download the resource body
            body_url = f"{self.sf.base_url}sobjects/StaticResource/{resource_id}/Body"
            body_response = requests.get(body_url, headers=headers, timeout=60)
            
            if body_response.status_code != 200:
                return {'error': f'Download failed: {body_response.status_code}'}
            
            zip_content = body_response.content
            self.logger.info(f"✅ Downloaded {len(zip_content)} bytes")
            
            # Extract ZIP content using in-memory approach
            return self.extract_zip_content(zip_content)
            
        except Exception as e:
            self.logger.error(f"❌ Error downloading resource: {e}")
            return {'error': str(e)}
    
    def extract_zip_content(self, zip_content: bytes) -> Dict:
        """Extract ZIP content using in-memory processing."""
        try:
            self.logger.info("📦 Extracting ZIP content...")
            
            extracted_files = {}
            
            with zipfile.ZipFile(io.BytesIO(zip_content), 'r') as zip_file:
                file_list = zip_file.namelist()
                self.logger.info(f"✓ Found {len(file_list)} files in ZIP")
                
                # Extract all files
                for filename in file_list:
                    try:
                        file_content = zip_file.read(filename)
                        
                        # Try to decode as text if possible
                        if filename.endswith(('.html', '.js', '.css', '.json', '.txt', '.md')):
                            try:
                                text_content = file_content.decode('utf-8', errors='ignore')
                                extracted_files[filename] = {
                                    'type': 'text',
                                    'size': len(text_content),
                                    'content': text_content
                                }
                                self.logger.info(f"✓ Extracted text file: {filename} ({len(text_content)} chars)")
                            except:
                                extracted_files[filename] = {
                                    'type': 'binary',
                                    'size': len(file_content),
                                    'content': file_content
                                }
                        else:
                            extracted_files[filename] = {
                                'type': 'binary',
                                'size': len(file_content),
                                'content': file_content
                            }
                            self.logger.debug(f"✓ Extracted binary file: {filename} ({len(file_content)} bytes)")
                            
                    except Exception as e:
                        self.logger.warning(f"⚠️ Could not extract {filename}: {e}")
            
            return {
                'success': True,
                'total_files': len(file_list),
                'extracted_files': extracted_files
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error extracting ZIP: {e}")
            return {'error': str(e)}
    
    def analyze_extracted_files(self, extracted_files: Dict) -> Dict:
        """Analyze extracted files for S3 access patterns."""
        try:
            self.logger.info("🔍 Analyzing extracted files for S3 patterns...")
            
            analysis = {
                's3_patterns': [],
                'api_patterns': [],
                'authentication_patterns': [],
                'url_construction_patterns': [],
                'key_findings': []
            }
            
            # Focus on key files first
            key_files = ['index.html', 'app.js', 'main.js', 'viewer.js', 'pdf.js', 'config.js']
            
            for filename, file_data in extracted_files.items():
                if file_data['type'] != 'text':
                    continue
                    
                content = file_data['content']
                self.logger.info(f"🔍 Analyzing: {filename}")
                
                # Look for S3 patterns
                s3_patterns = [
                    r'https?://[^/]*s3[^/]*\.amazonaws\.com[^\s"\'<>]+',
                    r'trackland-doc-storage[^\s"\'<>]*',
                    r'incitetax-pdf-manager[^\s"\'<>]*',
                    r'presigned.*url',
                    r'aws.*signature',
                    r'x-amz-[^\s"\'<>]+',
                    r'Bucket["\']?\s*[:=]\s*["\'][^"\']+["\']'
                ]
                
                for pattern in s3_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                    for match in matches:
                        analysis['s3_patterns'].append({
                            'file': filename,
                            'pattern': pattern,
                            'match': match,
                            'context': self.get_context_around_match(content, match)
                        })
                
                # Look for API endpoints
                api_patterns = [
                    r'/services/apexrest/[^\s"\'<>]+',
                    r'/services/data/v\d+\.\d+/[^\s"\'<>]+',
                    r'callout:[^\s"\'<>]+',
                    r'fetch\s*\(\s*["\']([^"\']+)["\']',
                    r'XMLHttpRequest\s*\(',
                    r'\.get\s*\(\s*["\']([^"\']+)["\']',
                    r'\.post\s*\(\s*["\']([^"\']+)["\']',
                    r'/aura\?[^\s"\'<>]+',
                    r'action["\']?\s*:\s*["\']([^"\']+)["\']'
                ]
                
                for pattern in api_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                    for match in matches:
                        analysis['api_patterns'].append({
                            'file': filename,
                            'pattern': pattern,
                            'match': match,
                            'context': self.get_context_around_match(content, str(match))
                        })
                
                # Look for authentication patterns
                auth_patterns = [
                    r'Authorization["\']?\s*:\s*["\'][^"\']+["\']',
                    r'Bearer\s+[^\s"\'<>]+',
                    r'session[Ii]d["\']?\s*:\s*["\'][^"\']+["\']',
                    r'token["\']?\s*:\s*["\'][^"\']+["\']',
                    r'credential[s]?["\']?\s*:\s*["\'][^"\']+["\']',
                    r'Cookie["\']?\s*:\s*["\'][^"\']+["\']'
                ]
                
                for pattern in auth_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                    for match in matches:
                        analysis['authentication_patterns'].append({
                            'file': filename,
                            'pattern': pattern,
                            'match': match,
                            'context': self.get_context_around_match(content, str(match))
                        })
                
                # Look for URL construction patterns
                url_patterns = [
                    r'document\s*\.\s*location',
                    r'window\s*\.\s*location',
                    r'href\s*=',
                    r'src\s*=',
                    r'url\s*=',
                    r'endpoint\s*=',
                    r'baseURL',
                    r'apiUrl'
                ]
                
                for pattern in url_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                    if matches:
                        analysis['url_construction_patterns'].append({
                            'file': filename,
                            'pattern': pattern,
                            'matches': len(matches),
                            'context': self.get_context_around_pattern(content, pattern)
                        })
                
                # Special analysis for key files
                if any(key in filename.lower() for key in key_files):
                    analysis['key_findings'].append({
                        'file': filename,
                        'size': file_data['size'],
                        'content_preview': content[:2000] + "..." if len(content) > 2000 else content
                    })
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing files: {e}")
            return {'error': str(e)}
    
    def get_context_around_match(self, content: str, match: str, lines_before: int = 2, lines_after: int = 2) -> str:
        """Get context around a match."""
        try:
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                if match in line:
                    start = max(0, i - lines_before)
                    end = min(len(lines), i + lines_after + 1)
                    
                    context_lines = []
                    for j in range(start, end):
                        marker = " → " if j == i else "   "
                        context_lines.append(f"{j+1:3d}{marker}{lines[j]}")
                    
                    return '\n'.join(context_lines)
            
            return f"Match found: {match[:100]}"
            
        except Exception as e:
            return f"Context error: {e}"
    
    def get_context_around_pattern(self, content: str, pattern: str, lines_before: int = 2, lines_after: int = 2) -> str:
        """Get context around a regex pattern."""
        try:
            lines = content.split('\n')
            
            for i, line in enumerate(lines):
                if re.search(pattern, line, re.IGNORECASE):
                    start = max(0, i - lines_before)
                    end = min(len(lines), i + lines_after + 1)
                    
                    context_lines = []
                    for j in range(start, end):
                        marker = " → " if j == i else "   "
                        context_lines.append(f"{j+1:3d}{marker}{lines[j]}")
                    
                    return '\n'.join(context_lines)
            
            return f"Pattern found: {pattern}"
            
        except Exception as e:
            return f"Context error: {e}"
    
    def test_iframe_access(self) -> Dict:
        """Test access to the iframe URLs we discovered."""
        try:
            self.logger.info("🔍 Testing iframe access...")
            
            # Fix the base URL
            base_url = self.sf.base_url.replace('/services/data/v59.0/', '/')
            
            test_urls = [
                f"{base_url}resource/1748037284000/TL_PDF_Editor/index.html",
                f"{base_url}resource/TL_PDF_Editor/index.html",
                f"{base_url}resource/1748037284000/TL_PDF_Editor",
                f"{base_url}resource/TL_PDF_Editor"
            ]
            
            access_results = []
            
            for url in test_urls:
                try:
                    self.logger.info(f"Testing: {url}")
                    
                    headers = {
                        'Cookie': f"sid={self.sf.session_id}",
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    }
                    
                    response = requests.get(url, headers=headers, timeout=30)
                    
                    result = {
                        'url': url,
                        'status_code': response.status_code,
                        'content_type': response.headers.get('Content-Type', ''),
                        'content_length': len(response.content) if response.content else 0,
                        'success': response.status_code == 200
                    }
                    
                    if response.status_code == 200 and response.content:
                        if 'text/html' in response.headers.get('Content-Type', ''):
                            result['content_preview'] = response.text[:1500] + "..." if len(response.text) > 1500 else response.text
                            self.logger.info(f"✅ Successfully accessed HTML content")
                        else:
                            result['content_preview'] = f"Binary content: {len(response.content)} bytes"
                    
                    access_results.append(result)
                    
                except Exception as e:
                    access_results.append({
                        'url': url,
                        'error': str(e)
                    })
            
            return {'iframe_tests': access_results}
            
        except Exception as e:
            self.logger.error(f"❌ Error testing iframe access: {e}")
            return {'error': str(e)}
    
    def comprehensive_extraction(self) -> Dict:
        """Perform comprehensive extraction and analysis."""
        self.logger.info("🔍 Starting comprehensive PDF Editor extraction...")
        
        # Download and extract
        extraction_result = self.download_and_extract_resource()
        
        if 'error' in extraction_result:
            return extraction_result
        
        extracted_files = extraction_result.get('extracted_files', {})
        
        # Analyze extracted files
        analysis_result = self.analyze_extracted_files(extracted_files)
        
        # Test iframe access
        iframe_result = self.test_iframe_access()
        
        return {
            'extraction': extraction_result,
            'analysis': analysis_result,
            'iframe_access': iframe_result,
            'timestamp': datetime.now().isoformat()
        }
    
    def print_results(self, results: Dict):
        """Print comprehensive results."""
        print("\n" + "=" * 80)
        print("TL_PDF_EDITOR EXTRACTION & ANALYSIS")
        print("=" * 80)
        
        # Extraction Results
        extraction = results.get('extraction', {})
        if extraction.get('success'):
            print(f"✅ Extraction Success: {extraction.get('total_files', 0)} files extracted")
            
            extracted_files = extraction.get('extracted_files', {})
            text_files = {k: v for k, v in extracted_files.items() if v.get('type') == 'text'}
            binary_files = {k: v for k, v in extracted_files.items() if v.get('type') == 'binary'}
            
            print(f"📄 Text files: {len(text_files)}")
            print(f"📦 Binary files: {len(binary_files)}")
            
            # Show key text files
            key_files = [f for f in text_files.keys() if any(key in f.lower() for key in ['index.html', 'app.js', 'main.js', 'viewer.js'])]
            if key_files:
                print(f"\n🔑 Key files found:")
                for file in key_files:
                    print(f"  • {file} ({text_files[file]['size']} chars)")
        
        # Analysis Results
        analysis = results.get('analysis', {})
        if analysis and 'error' not in analysis:
            print(f"\n🔍 ANALYSIS RESULTS")
            print("-" * 50)
            
            s3_patterns = analysis.get('s3_patterns', [])
            api_patterns = analysis.get('api_patterns', [])
            auth_patterns = analysis.get('authentication_patterns', [])
            
            print(f"🌐 S3 patterns found: {len(s3_patterns)}")
            print(f"📞 API patterns found: {len(api_patterns)}")
            print(f"🔐 Auth patterns found: {len(auth_patterns)}")
            
            # Show S3 patterns
            if s3_patterns:
                print(f"\n🌐 S3 PATTERNS:")
                for pattern in s3_patterns[:5]:
                    print(f"  📍 {pattern['file']}: {pattern['match']}")
                    print(f"     Context:")
                    for line in pattern['context'].split('\n')[:3]:
                        print(f"       {line}")
                    print()
            
            # Show API patterns
            if api_patterns:
                print(f"\n📞 API PATTERNS:")
                unique_apis = list(set(p['match'] for p in api_patterns if isinstance(p['match'], str)))
                for api in unique_apis[:5]:
                    print(f"  • {api}")
            
            # Show key findings
            key_findings = analysis.get('key_findings', [])
            if key_findings:
                print(f"\n🔑 KEY FILE ANALYSIS:")
                for finding in key_findings[:2]:  # Show first 2
                    print(f"\n📄 {finding['file']} ({finding['size']} chars)")
                    print(f"Content preview:")
                    preview_lines = finding['content_preview'].split('\n')[:15]
                    for line in preview_lines:
                        print(f"  {line}")
                    if len(finding['content_preview'].split('\n')) > 15:
                        print(f"  ... (truncated)")
        
        # Iframe Access Results
        iframe_access = results.get('iframe_access', {})
        if iframe_access and 'error' not in iframe_access:
            iframe_tests = iframe_access.get('iframe_tests', [])
            successful_access = [t for t in iframe_tests if t.get('success')]
            
            print(f"\n🖼️ IFRAME ACCESS TESTS: {len(iframe_tests)} tested, {len(successful_access)} successful")
            
            if successful_access:
                print("✅ SUCCESSFUL IFRAME ACCESS:")
                for test in successful_access:
                    print(f"  • {test['url']}")
                    print(f"    Type: {test.get('content_type', 'Unknown')}")
                    if test.get('content_preview'):
                        preview_lines = test['content_preview'].split('\n')[:10]
                        print(f"    Preview:")
                        for line in preview_lines:
                            print(f"      {line}")
                        print()
        
        # Final Analysis
        print("\n" + "=" * 80)
        print("🎯 FINAL ANALYSIS - S3 ACCESS MECHANISM")
        print("=" * 80)
        
        breakthroughs = []
        
        if extraction.get('success'):
            breakthroughs.append("✅ Successfully extracted PDF viewer source code")
        
        if analysis.get('s3_patterns'):
            breakthroughs.append(f"🌐 Found {len(analysis['s3_patterns'])} S3-related patterns in source")
        
        if analysis.get('api_patterns'):
            breakthroughs.append(f"📞 Found {len(analysis['api_patterns'])} API endpoints in source")
        
        if analysis.get('authentication_patterns'):
            breakthroughs.append(f"🔐 Found {len(analysis['authentication_patterns'])} authentication patterns")
        
        if iframe_access.get('iframe_tests'):
            successful = len([t for t in iframe_access['iframe_tests'] if t.get('success')])
            if successful > 0:
                breakthroughs.append(f"📄 Successfully accessed {successful} iframe URLs")
        
        if breakthroughs:
            print("🔥 BREAKTHROUGHS ACHIEVED:")
            for breakthrough in breakthroughs:
                print(breakthrough)
            
            print(f"\n💡 NEXT STEPS:")
            print("1. Analyze extracted JavaScript for exact S3 access method")
            print("2. Look for authentication tokens or session handling")  
            print("3. Find URL construction logic for S3 file access")
            print("4. Implement discovered method in Python backup script")
            
        else:
            print("❌ Limited breakthroughs - need deeper analysis")
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("PDF Editor Extraction & Analysis")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        extractor = PDFEditorExtractor(logger)
        
        if not extractor.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        results = extractor.comprehensive_extraction()
        extractor.print_results(results)
        
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