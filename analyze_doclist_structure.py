#!/usr/bin/env python3
"""
DocListEntry Structure Analysis Script
====================================

Analyzes the DocListEntry__c object and its related objects to understand:
1. How files are stored and accessed
2. Potential S3 authentication mechanisms
3. Field structures that might contain access keys or tokens
4. Relationships between DocListEntry objects

Usage:
python analyze_doclist_structure.py
"""

import os
import sys
import logging
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


class DocListStructureAnalyzer:
    """Analyzes DocListEntry__c and related object structures."""
    
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
    
    def analyze_object_structure(self, object_name: str) -> Dict:
        """Get detailed field information for a Salesforce object."""
        try:
            self.logger.info(f"📋 Analyzing object structure: {object_name}")
            
            # Get object metadata
            obj_metadata = getattr(self.sf, object_name).describe()
            
            fields_info = {}
            for field in obj_metadata['fields']:
                field_name = field['name']
                field_info = {
                    'type': field['type'],
                    'label': field['label'],
                    'length': field.get('length'),
                    'custom': field['custom'],
                    'encrypted': field.get('encrypted', False),
                    'calculated': field.get('calculated', False),
                    'referenceTo': field.get('referenceTo', []),
                    'relationshipName': field.get('relationshipName'),
                    'picklistValues': [v['value'] for v in field.get('picklistValues', [])]
                }
                fields_info[field_name] = field_info
            
            return {
                'object_name': object_name,
                'label': obj_metadata['label'],
                'total_fields': len(fields_info),
                'custom_fields': sum(1 for f in fields_info.values() if f['custom']),
                'fields': fields_info
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing {object_name}: {e}")
            return {'error': str(e)}
    
    def find_s3_related_fields(self, structure: Dict) -> List[Dict]:
        """Find fields that might contain S3-related information."""
        s3_keywords = [
            's3', 'aws', 'bucket', 'key', 'access', 'secret', 'token', 
            'credential', 'auth', 'document', 'url', 'link', 'storage',
            'trackland', 'amazon', 'presigned'
        ]
        
        s3_fields = []
        
        if 'fields' not in structure:
            return s3_fields
        
        for field_name, field_info in structure['fields'].items():
            field_lower = field_name.lower()
            label_lower = field_info['label'].lower()
            
            # Check if field name or label contains S3-related keywords
            for keyword in s3_keywords:
                if keyword in field_lower or keyword in label_lower:
                    s3_fields.append({
                        'field_name': field_name,
                        'field_info': field_info,
                        'matched_keyword': keyword,
                        'match_in': 'name' if keyword in field_lower else 'label'
                    })
                    break
        
        return s3_fields
    
    def get_sample_records(self, object_name: str, limit: int = 5) -> List[Dict]:
        """Get sample records to see actual field values."""
        try:
            self.logger.info(f"📄 Getting sample records from {object_name}")
            
            # Build query with all available fields
            structure = self.analyze_object_structure(object_name)
            if 'error' in structure:
                return []
            
            # Select interesting fields (avoid very long text fields for readability)
            fields_to_query = []
            for field_name, field_info in structure['fields'].items():
                if field_info['type'] not in ['textarea', 'encryptedstring']:
                    fields_to_query.append(field_name)
            
            # Limit to prevent query being too long
            if len(fields_to_query) > 50:
                fields_to_query = fields_to_query[:50]
            
            query = f"""
                SELECT {', '.join(fields_to_query)}
                FROM {object_name}
                WHERE IsDeleted = FALSE
                ORDER BY CreatedDate DESC
                LIMIT {limit}
            """
            
            result = self.sf.query(query)
            return result['records']
            
        except Exception as e:
            self.logger.error(f"❌ Error getting sample records from {object_name}: {e}")
            return []
    
    def analyze_doclist_relationships(self) -> Dict:
        """Analyze relationships between DocList objects."""
        try:
            self.logger.info("🔗 Analyzing DocListEntry relationships...")
            
            # Check how DocListEntry__c relates to other objects
            relationships_query = """
                SELECT Id, Name, Document__c, Account__c, Account__r.Name,
                       Type_Current__c, CreatedDate, LastModifiedDate,
                       OwnerId, Owner.Name
                FROM DocListEntry__c
                WHERE IsDeleted = FALSE
                AND Document__c != NULL
                ORDER BY CreatedDate DESC
                LIMIT 10
            """
            
            result = self.sf.query(relationships_query)
            
            # Analyze Document__c URLs to understand patterns
            url_patterns = {}
            for record in result['records']:
                doc_url = record.get('Document__c', '')
                if doc_url:
                    # Extract domain/bucket patterns
                    if 'trackland-doc-storage' in doc_url:
                        # Parse S3 URL structure
                        parts = doc_url.replace('https://', '').split('/')
                        if len(parts) > 1:
                            bucket_info = parts[0]
                            path_structure = '/'.join(parts[1:])
                            
                            pattern_key = f"{bucket_info}/*"
                            if pattern_key not in url_patterns:
                                url_patterns[pattern_key] = {
                                    'count': 0,
                                    'examples': []
                                }
                            
                            url_patterns[pattern_key]['count'] += 1
                            if len(url_patterns[pattern_key]['examples']) < 3:
                                url_patterns[pattern_key]['examples'].append(path_structure)
            
            return {
                'sample_records': result['records'],
                'url_patterns': url_patterns,
                'total_analyzed': len(result['records'])
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error analyzing relationships: {e}")
            return {'error': str(e)}
    
    def check_content_document_access(self) -> Dict:
        """Check if files are also stored as ContentDocument/ContentVersion."""
        try:
            self.logger.info("📎 Checking ContentDocument access patterns...")
            
            # See if DocListEntry records are linked to ContentDocuments
            content_link_query = """
                SELECT Id, LinkedEntityId, ContentDocumentId, 
                       ContentDocument.Title, ContentDocument.FileType,
                       ContentDocument.ContentSize, ContentDocument.CreatedDate
                FROM ContentDocumentLink
                WHERE LinkedEntity.Type = 'DocListEntry__c'
                ORDER BY CreatedDate DESC
                LIMIT 10
            """
            
            try:
                content_links = self.sf.query(content_link_query)
                
                # For each ContentDocument, try to get version info
                version_info = []
                for link in content_links['records']:
                    if link.get('ContentDocumentId'):
                        version_query = f"""
                            SELECT Id, Title, FileType, ContentSize, 
                                   VersionNumber, CreatedDate, PathOnClient
                            FROM ContentVersion
                            WHERE ContentDocumentId = '{link['ContentDocumentId']}'
                            AND IsLatest = TRUE
                            LIMIT 1
                        """
                        
                        try:
                            version_result = self.sf.query(version_query)
                            if version_result['records']:
                                version_info.append(version_result['records'][0])
                        except Exception as ve:
                            self.logger.debug(f"Version query failed: {ve}")
                
                return {
                    'content_links_found': len(content_links['records']),
                    'content_links': content_links['records'],
                    'version_info': version_info
                }
                
            except Exception as e:
                self.logger.debug(f"ContentDocument query failed: {e}")
                return {'content_documents_available': False, 'error': str(e)}
                
        except Exception as e:
            self.logger.error(f"❌ Error checking ContentDocument access: {e}")
            return {'error': str(e)}
    
    def comprehensive_analysis(self) -> Dict:
        """Perform comprehensive analysis of all DocList objects."""
        analysis_results = {
            'analysis_timestamp': datetime.now().isoformat(),
            'objects_analyzed': {}
        }
        
        # Objects to analyze
        objects_to_analyze = [
            'DocListEntry__c',
            'DocListEntryPage__c', 
            'DocListEntryPageItem__c',
            'DocListEntryVersion__c'
        ]
        
        for obj_name in objects_to_analyze:
            self.logger.info(f"🔍 Analyzing {obj_name}...")
            
            # Get object structure
            structure = self.analyze_object_structure(obj_name)
            
            # Find S3-related fields
            s3_fields = []
            if 'fields' in structure:
                s3_fields = self.find_s3_related_fields(structure)
            
            # Get sample records
            sample_records = self.get_sample_records(obj_name, 3)
            
            analysis_results['objects_analyzed'][obj_name] = {
                'structure': structure,
                's3_related_fields': s3_fields,
                'sample_records': sample_records,
                'sample_count': len(sample_records)
            }
        
        # Add relationship analysis
        analysis_results['relationships'] = self.analyze_doclist_relationships()
        
        # Add ContentDocument analysis
        analysis_results['content_documents'] = self.check_content_document_access()
        
        return analysis_results
    
    def print_analysis_results(self, analysis: Dict):
        """Print formatted analysis results."""
        if 'error' in analysis:
            self.logger.error(f"Analysis failed: {analysis['error']}")
            return
        
        print("\n" + "=" * 80)
        print("DOCLISTENTRY STRUCTURE ANALYSIS")
        print("=" * 80)
        
        for obj_name, obj_analysis in analysis['objects_analyzed'].items():
            print(f"\n📋 {obj_name}")
            print("-" * 50)
            
            structure = obj_analysis['structure']
            if 'error' not in structure:
                print(f"Total Fields: {structure['total_fields']}")
                print(f"Custom Fields: {structure['custom_fields']}")
                print(f"Sample Records: {obj_analysis['sample_count']}")
            
            # Show S3-related fields
            s3_fields = obj_analysis['s3_related_fields']
            if s3_fields:
                print(f"\n🔑 S3-Related Fields ({len(s3_fields)}):")
                for field in s3_fields:
                    field_info = field['field_info']
                    print(f"  • {field['field_name']} ({field_info['type']})")
                    print(f"    Label: {field_info['label']}")
                    print(f"    Matched: '{field['matched_keyword']}' in {field['match_in']}")
                    if field_info['referenceTo']:
                        print(f"    References: {field_info['referenceTo']}")
            else:
                print("🔑 No obvious S3-related fields found")
            
            # Show interesting sample values
            if obj_analysis['sample_records']:
                print(f"\n📄 Sample Record Fields:")
                record = obj_analysis['sample_records'][0]
                for key, value in record.items():
                    if key not in ['attributes'] and value is not None:
                        value_str = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                        print(f"  • {key}: {value_str}")
        
        # Show relationships
        relationships = analysis.get('relationships', {})
        if 'error' not in relationships:
            print(f"\n🔗 URL PATTERNS FOUND")
            print("-" * 50)
            url_patterns = relationships.get('url_patterns', {})
            for pattern, info in url_patterns.items():
                print(f"Pattern: {pattern}")
                print(f"  Count: {info['count']}")
                for example in info['examples']:
                    print(f"  Example: {example}")
        
        # Show ContentDocument info
        content_docs = analysis.get('content_documents', {})
        if 'error' not in content_docs and content_docs.get('content_links_found', 0) > 0:
            print(f"\n📎 CONTENTDOCUMENT INTEGRATION")
            print("-" * 50)
            print(f"ContentDocument links found: {content_docs['content_links_found']}")
            print(f"Version info available: {len(content_docs.get('version_info', []))}")
        elif not content_docs.get('content_documents_available', True):
            print(f"\n📎 ContentDocument integration not available")
        
        print("\n" + "=" * 80)


def main():
    """Main execution function."""
    print("DocListEntry Structure Analysis")
    print("=" * 50)
    
    logger = setup_logging()
    
    try:
        analyzer = DocListStructureAnalyzer(logger)
        
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