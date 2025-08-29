#!/usr/bin/env python3
"""
Apex Code Examination Script
============================

Examines the specific TLND Apex classes to understand how they handle
S3 authentication and file access. Focuses on:
1. TL_Base, TL_Api, TL_BaseTracks classes
2. Methods that handle file downloads/authentication
3. S3 signature generation or credential handling

Usage:
python examine_apex_code.py
"""

import os
import sys
import logging
import re
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


class ApexCodeExaminer:
    """Examines Apex class code for S3 authentication patterns."""
    
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
    
    def get_apex_class_code(self, class_names: List[str]) -> Dict[str, Dict]:
        """Get the full source code for specified Apex classes."""
        class_code = {}
        
        for class_name in class_names:
            try:
                self.logger.info(f"🔍 Retrieving code for {class_name}...")
                
                query = f"""
                    SELECT Id, Name, NamespacePrefix, Body, ApiVersion, Status,
                           CreatedDate, LastModifiedDate, CreatedBy.Name, LastModifiedBy.Name
                    FROM ApexClass
                    WHERE Name = '{class_name}'
                    AND NamespacePrefix = 'tlnd'
                """
                
                result = self.sf.query(query)
                
                if result['records']:
                    record = result['records'][0]
                    class_code[class_name] = {
                        'id': record['Id'],
                        'name': record['Name'],
                        'namespace': record['NamespacePrefix'],
                        'body': record.get('Body', ''),
                        'api_version': record.get('ApiVersion'),
                        'status': record.get('Status'),
                        'created_date': record['CreatedDate'],
                        'modified_date': record['LastModifiedDate'],
                        'created_by': record.get('CreatedBy', {}).get('Name', 'Unknown') if record.get('CreatedBy') else 'Unknown',
                        'modified_by': record.get('LastModifiedBy', {}).get('Name', 'Unknown') if record.get('LastModifiedBy') else 'Unknown'
                    }
                else:
                    self.logger.warning(f"⚠️ No class found with name {class_name}")
                    
            except Exception as e:
                self.logger.error(f"❌ Error retrieving {class_name}: {e}")
                class_code[class_name] = {'error': str(e)}
        
        return class_code
    
    def analyze_code_for_s3_patterns(self, class_name: str, code: str) -> Dict:
        """Analyze Apex code for S3 authentication and file access patterns."""
        analysis = {
            'class_name': class_name,
            'methods': [],
            's3_patterns': [],
            'http_patterns': [],
            'authentication_patterns': [],
            'url_construction_patterns': [],
            'interesting_variables': [],
            'crypto_operations': []
        }
        
        if not code:
            return analysis
        
        # Split code into methods for analysis
        methods = self.extract_methods(code)
        analysis['methods'] = [{'name': name, 'signature': sig, 'body_length': len(body)} 
                              for name, sig, body in methods]
        
        # Look for S3-specific patterns
        s3_patterns = [
            r's3[\w\s]*\.amazonaws\.com',
            r'trackland-doc-storage',
            r'presigned.*url',
            r'aws.*signature',
            r'hmac.*sha',
            r'x-amz-.*',
            r'authorization.*aws',
            r'credential.*aws'
        ]
        
        for pattern in s3_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                context = self.get_context_around_match(code, match)
                analysis['s3_patterns'].append({
                    'pattern': pattern,
                    'match': match.group(),
                    'context': context,
                    'line_number': code[:match.start()].count('\n') + 1
                })
        
        # Look for HTTP request patterns
        http_patterns = [
            r'HttpRequest.*req.*=.*new.*HttpRequest\(\)',
            r'Http.*http.*=.*new.*Http\(\)',
            r'req\.setEndpoint\(',
            r'req\.setMethod\(',
            r'req\.setHeader\(',
            r'http\.send\(',
            r'HttpResponse.*response'
        ]
        
        for pattern in http_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                context = self.get_context_around_match(code, match)
                analysis['http_patterns'].append({
                    'pattern': pattern,
                    'match': match.group(),
                    'context': context,
                    'line_number': code[:match.start()].count('\n') + 1
                })
        
        # Look for authentication/credential patterns
        auth_patterns = [
            r'secret.*key',
            r'access.*key',
            r'token',
            r'credential',
            r'signature',
            r'hash',
            r'hmac',
            r'encrypt',
            r'auth',
            r'bearer'
        ]
        
        for pattern in auth_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                context = self.get_context_around_match(code, match)
                analysis['authentication_patterns'].append({
                    'pattern': pattern,
                    'match': match.group(),
                    'context': context,
                    'line_number': code[:match.start()].count('\n') + 1
                })
        
        # Look for URL construction patterns
        url_patterns = [
            r'String.*url.*=',
            r'\.replace\(',
            r'\+.*["\'].*["\']',
            r'String\.format\(',
            r'\.substring\(',
            r'\.indexOf\('
        ]
        
        for pattern in url_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                context = self.get_context_around_match(code, match)
                # Only include if the context mentions URLs or file paths
                if any(keyword in context.lower() for keyword in ['url', 'http', 'amazonaws', 's3', 'trackland', 'document']):
                    analysis['url_construction_patterns'].append({
                        'pattern': pattern,
                        'match': match.group(),
                        'context': context,
                        'line_number': code[:match.start()].count('\n') + 1
                    })
        
        # Look for interesting variables
        variable_patterns = [
            r'(String|final)\s+(\w*[Uu]rl\w*)\s*=',
            r'(String|final)\s+(\w*[Kk]ey\w*)\s*=',
            r'(String|final)\s+(\w*[Tt]oken\w*)\s*=',
            r'(String|final)\s+(\w*[Ss]ecret\w*)\s*=',
            r'(String|final)\s+(\w*[Cc]redential\w*)\s*=',
            r'(String|final)\s+(\w*[Ss]ignature\w*)\s*='
        ]
        
        for pattern in variable_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                context = self.get_context_around_match(code, match)
                analysis['interesting_variables'].append({
                    'variable_name': match.group(2) if len(match.groups()) > 1 else match.group(),
                    'declaration': match.group(),
                    'context': context,
                    'line_number': code[:match.start()].count('\n') + 1
                })
        
        # Look for crypto operations
        crypto_patterns = [
            r'Crypto\.',
            r'EncodingUtil\.',
            r'\.digest\(',
            r'\.sign\(',
            r'\.base64Encode\(',
            r'\.base64Decode\(',
            r'\.convertToHex\(',
            r'\.generateMac\('
        ]
        
        for pattern in crypto_patterns:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                context = self.get_context_around_match(code, match)
                analysis['crypto_operations'].append({
                    'operation': match.group(),
                    'context': context,
                    'line_number': code[:match.start()].count('\n') + 1
                })
        
        return analysis
    
    def extract_methods(self, code: str) -> List[tuple]:
        """Extract method signatures and bodies from Apex code."""
        methods = []
        
        # Regex to find method definitions
        method_pattern = r'((?:public|private|protected|global|static|\s)+)\s+(\w+\s+)?(\w+)\s*\([^)]*\)\s*\{'
        
        matches = list(re.finditer(method_pattern, code, re.IGNORECASE | re.MULTILINE))
        
        for i, match in enumerate(matches):
            method_start = match.start()
            method_signature = match.group().strip()
            method_name = match.group(3)
            
            # Find the end of this method by counting braces
            brace_count = 0
            method_end = method_start
            
            for j in range(match.end(), len(code)):
                if code[j] == '{':
                    brace_count += 1
                elif code[j] == '}':
                    brace_count -= 1
                    if brace_count == -1:  # We've closed the method
                        method_end = j + 1
                        break
            
            method_body = code[match.end():method_end-1] if method_end > match.end() else ""
            methods.append((method_name, method_signature, method_body))
        
        return methods
    
    def get_context_around_match(self, code: str, match, context_lines: int = 3) -> str:
        """Get context lines around a regex match."""
        lines = code.split('\n')
        match_line = code[:match.start()].count('\n')
        
        start_line = max(0, match_line - context_lines)
        end_line = min(len(lines), match_line + context_lines + 1)
        
        context_lines_list = []
        for i in range(start_line, end_line):
            marker = " → " if i == match_line else "   "
            if i < len(lines):
                context_lines_list.append(f"{i+1:3d}{marker}{lines[i]}")
        
        return '\n'.join(context_lines_list)
    
    def comprehensive_code_analysis(self) -> Dict:
        """Perform comprehensive analysis of TLND Apex classes."""
        self.logger.info("🔍 Starting comprehensive Apex code analysis...")
        
        # Target classes from our previous analysis
        target_classes = ['TL_Base', 'TL_Api', 'TL_BaseTracks']
        
        # Get the code for all classes
        class_codes = self.get_apex_class_code(target_classes)
        
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'classes_analyzed': [],
            'summary': {
                'total_classes': 0,
                'classes_with_s3_patterns': 0,
                'classes_with_http_patterns': 0,
                'classes_with_auth_patterns': 0,
                'most_relevant_class': None,
                'key_findings': []
            }
        }
        
        most_relevant_score = 0
        most_relevant_class = None
        
        for class_name, class_info in class_codes.items():
            if 'error' in class_info:
                self.logger.warning(f"⚠️ Skipping {class_name} due to error: {class_info['error']}")
                continue
            
            code = class_info.get('body', '')
            if not code:
                self.logger.warning(f"⚠️ No code found for {class_name}")
                continue
            
            # Analyze the code
            code_analysis = self.analyze_code_for_s3_patterns(class_name, code)
            
            # Calculate relevance score
            relevance_score = (
                len(code_analysis['s3_patterns']) * 10 +
                len(code_analysis['http_patterns']) * 5 +
                len(code_analysis['authentication_patterns']) * 3 +
                len(code_analysis['crypto_operations']) * 5 +
                len(code_analysis['url_construction_patterns']) * 2
            )
            
            class_analysis_result = {
                'class_info': class_info,
                'code_analysis': code_analysis,
                'relevance_score': relevance_score,
                'code_length': len(code),
                'method_count': len(code_analysis['methods'])
            }
            
            analysis_results['classes_analyzed'].append(class_analysis_result)
            
            # Update summary statistics
            analysis_results['summary']['total_classes'] += 1
            
            if code_analysis['s3_patterns']:
                analysis_results['summary']['classes_with_s3_patterns'] += 1
            
            if code_analysis['http_patterns']:
                analysis_results['summary']['classes_with_http_patterns'] += 1
            
            if code_analysis['authentication_patterns']:
                analysis_results['summary']['classes_with_auth_patterns'] += 1
            
            # Track most relevant class
            if relevance_score > most_relevant_score:
                most_relevant_score = relevance_score
                most_relevant_class = class_name
        
        analysis_results['summary']['most_relevant_class'] = most_relevant_class
        
        # Sort classes by relevance
        analysis_results['classes_analyzed'].sort(key=lambda x: x['relevance_score'], reverse=True)
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results focused on S3 authentication discovery."""
        print("\n" + "=" * 80)
        print("APEX CODE ANALYSIS - S3 AUTHENTICATION DISCOVERY")
        print("=" * 80)
        
        summary = analysis['summary']
        print(f"📊 ANALYSIS SUMMARY")
        print(f"   Total classes analyzed: {summary['total_classes']}")
        print(f"   Classes with S3 patterns: {summary['classes_with_s3_patterns']}")
        print(f"   Classes with HTTP patterns: {summary['classes_with_http_patterns']}")
        print(f"   Classes with auth patterns: {summary['classes_with_auth_patterns']}")
        print(f"   Most relevant class: {summary['most_relevant_class']}")
        
        # Detailed analysis for each class
        for class_result in analysis['classes_analyzed']:
            class_info = class_result['class_info']
            code_analysis = class_result['code_analysis']
            relevance_score = class_result['relevance_score']
            
            print(f"\n" + "=" * 60)
            print(f"🔍 CLASS: {class_info['name']} (Score: {relevance_score})")
            print(f"   Namespace: {class_info['namespace']}")
            print(f"   Code length: {class_result['code_length']} characters")
            print(f"   Methods: {class_result['method_count']}")
            print(f"   Last modified: {class_info['modified_date']} by {class_info['modified_by']}")
            
            # Show S3 patterns (most important)
            if code_analysis['s3_patterns']:
                print(f"\n🔥 S3 PATTERNS FOUND ({len(code_analysis['s3_patterns'])})")
                print("-" * 40)
                for pattern in code_analysis['s3_patterns']:
                    print(f"   Pattern: {pattern['pattern']}")
                    print(f"   Match: {pattern['match']}")
                    print(f"   Line: {pattern['line_number']}")
                    print(f"   Context:")
                    for line in pattern['context'].split('\n'):
                        print(f"     {line}")
                    print()
            
            # Show HTTP patterns
            if code_analysis['http_patterns']:
                print(f"\n🌐 HTTP PATTERNS FOUND ({len(code_analysis['http_patterns'])})")
                print("-" * 40)
                for pattern in code_analysis['http_patterns'][:3]:  # Show top 3
                    print(f"   Pattern: {pattern['pattern']}")
                    print(f"   Line: {pattern['line_number']}")
                    print(f"   Context:")
                    for line in pattern['context'].split('\n'):
                        print(f"     {line}")
                    print()
            
            # Show authentication patterns
            if code_analysis['authentication_patterns']:
                print(f"\n🔐 AUTHENTICATION PATTERNS FOUND ({len(code_analysis['authentication_patterns'])})")
                print("-" * 40)
                auth_by_type = {}
                for pattern in code_analysis['authentication_patterns']:
                    key = pattern['pattern']
                    if key not in auth_by_type:
                        auth_by_type[key] = []
                    auth_by_type[key].append(pattern)
                
                for pattern_type, matches in auth_by_type.items():
                    print(f"   {pattern_type.upper()}: {len(matches)} occurrences")
                    if matches:
                        # Show most relevant match
                        best_match = max(matches, key=lambda x: len(x['context']))
                        print(f"   Best match at line {best_match['line_number']}:")
                        for line in best_match['context'].split('\n'):
                            print(f"     {line}")
                        print()
            
            # Show crypto operations
            if code_analysis['crypto_operations']:
                print(f"\n🔒 CRYPTO OPERATIONS FOUND ({len(code_analysis['crypto_operations'])})")
                print("-" * 40)
                for crypto in code_analysis['crypto_operations'][:3]:  # Show top 3
                    print(f"   Operation: {crypto['operation']}")
                    print(f"   Line: {crypto['line_number']}")
                    print(f"   Context:")
                    for line in crypto['context'].split('\n'):
                        print(f"     {line}")
                    print()
            
            # Show interesting variables
            if code_analysis['interesting_variables']:
                print(f"\n📝 INTERESTING VARIABLES ({len(code_analysis['interesting_variables'])})")
                print("-" * 40)
                for var in code_analysis['interesting_variables'][:5]:  # Show top 5
                    print(f"   Variable: {var['variable_name']}")
                    print(f"   Declaration: {var['declaration']}")
                    print(f"   Line: {var['line_number']}")
                    print()
            
            # Show URL construction patterns
            if code_analysis['url_construction_patterns']:
                print(f"\n🔗 URL CONSTRUCTION PATTERNS ({len(code_analysis['url_construction_patterns'])})")
                print("-" * 40)
                for url_pattern in code_analysis['url_construction_patterns'][:3]:
                    print(f"   Pattern: {url_pattern['pattern']}")
                    print(f"   Line: {url_pattern['line_number']}")
                    print(f"   Context:")
                    for line in url_pattern['context'].split('\n'):
                        print(f"     {line}")
                    print()
        
        # Final recommendations
        print("\n" + "=" * 80)
        print("🎯 S3 ACCESS STRATEGY RECOMMENDATIONS")
        print("=" * 80)
        
        recommendations = []
        
        highest_scoring = analysis['classes_analyzed'][0] if analysis['classes_analyzed'] else None
        
        if highest_scoring and highest_scoring['relevance_score'] > 0:
            class_name = highest_scoring['class_info']['name']
            recommendations.append(f"✅ Focus on {class_name} class - highest relevance score ({highest_scoring['relevance_score']})")
            
            code_analysis = highest_scoring['code_analysis']
            
            if code_analysis['s3_patterns']:
                recommendations.append(f"🔥 Found {len(code_analysis['s3_patterns'])} S3-specific patterns - examine these closely")
            
            if code_analysis['crypto_operations']:
                recommendations.append(f"🔒 Found {len(code_analysis['crypto_operations'])} crypto operations - likely signature generation")
            
            if code_analysis['http_patterns']:
                recommendations.append(f"🌐 Found {len(code_analysis['http_patterns'])} HTTP patterns - examine request construction")
        
        if summary['classes_with_s3_patterns'] == 0:
            recommendations.append("❌ No S3-specific patterns found in analyzed classes")
            recommendations.append("💡 May need to examine other namespaces or contact Trackland for API documentation")
        
        for rec in recommendations:
            print(rec)
        
        print("=" * 80)


def main():
    """Main execution function."""
    print("Apex Code Examination")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        examiner = ApexCodeExaminer(logger)
        
        if not examiner.authenticate():
            logger.error("❌ Failed to authenticate with Salesforce")
            return False
        
        analysis = examiner.comprehensive_code_analysis()
        examiner.print_analysis_results(analysis)
        
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