# How to Extract Salesforce Package Code

This guide shows you multiple ways to extract and review Salesforce code to investigate the PDF viewer/annotator implementation.

## Method 1: Salesforce CLI (SFDX) - Most Comprehensive

### Install Salesforce CLI
```bash
# Install Salesforce CLI
npm install -g @salesforce/cli

# Verify installation
sf --version
```

### Authenticate and Extract Code
```bash
# Authenticate with your org
sf org login web --alias myorg

# Create a new SFDX project
sf project generate --name salesforce-code-review
cd salesforce-code-review

# Retrieve all metadata (this will take a while)
sf project retrieve start --metadata "*"

# Or retrieve specific components
sf project retrieve start --metadata "LightningComponentBundle,ApexClass,CustomObject"
```

### Target Specific Components
```bash
# Retrieve Lightning Components (most likely to contain PDF viewer)
sf project retrieve start --metadata "LightningComponentBundle"

# Retrieve Apex Classes
sf project retrieve start --metadata "ApexClass"

# Retrieve Custom Objects
sf project retrieve start --metadata "CustomObject:DocListEntry__c"

# Retrieve Static Resources (might contain PDF libraries)
sf project retrieve start --metadata "StaticResource"
```

## Method 2: VS Code with Salesforce Extensions

### Setup
1. Install VS Code
2. Install "Salesforce Extension Pack" from VS Code marketplace
3. Create new SFDX project: `Ctrl+Shift+P` → "SFDX: Create Project"
4. Authorize org: `Ctrl+Shift+P` → "SFDX: Authorize an Org"

### Retrieve Code
1. `Ctrl+Shift+P` → "SFDX: Retrieve Source from Org"
2. Select metadata types to retrieve
3. Browse code in VS Code with syntax highlighting

## Method 3: Package.xml Method

### Create package.xml file
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Package xmlns="http://soap.sforce.com/2006/04/metadata">
    <types>
        <members>*</members>
        <name>LightningComponentBundle</name>
    </types>
    <types>
        <members>*</members>
        <name>ApexClass</name>
    </types>
    <types>
        <members>*</members>
        <name>StaticResource</name>
    </types>
    <types>
        <members>DocListEntry__c</members>
        <name>CustomObject</name>
    </types>
    <types>
        <members>*</members>
        <name>Flow</name>
    </types>
    <version>59.0</version>
</Package>
```

### Use with Salesforce CLI
```bash
sf project retrieve start --manifest package.xml
```

## Method 4: Workbench (Web-based)

1. Go to https://workbench.developerforce.com
2. Login with your Salesforce credentials
3. Go to **Utilities** → **Retrieve**
4. Select **Unpackaged** and upload your package.xml
5. Download the zip file containing your code

## Method 5: Browser Developer Tools (Quick Investigation)

### For Lightning Components
1. Open DocListEntry__c record in Salesforce
2. Open PDF viewer
3. Press F12 (Developer Tools)
4. In Console, run:
```javascript
// Find Lightning components
$A.getContext().getApp().getType()
$A.getContext().getApp().getDef().getComponentDefs()

// Look for PDF-related components
Array.from(document.querySelectorAll('[data-aura-class*="pdf" i], [data-aura-class*="document" i], [data-aura-class*="viewer" i]'))

// Check for iframes (common for PDF viewers)
Array.from(document.querySelectorAll('iframe')).map(f => f.src)
```

5. In **Network** tab, reload page and look for:
   - JavaScript files with "pdf", "viewer", "document" in names
   - API calls to load components
   - Static resource requests

## What to Look For in the Code

### Lightning Components (.cmp, .js, .css files)
```bash
# Search for PDF-related components
find . -name "*.cmp" -o -name "*.js" | xargs grep -l -i "pdf\|viewer\|document\|annotation"

# Look for component definitions
find . -name "*.cmp" | xargs grep -l "PageCount\|Document__c\|trackland"
```

### Apex Classes (.cls files)
```bash
# Search for PDF-related Apex classes
find . -name "*.cls" | xargs grep -l -i "pdf\|viewer\|document\|s3\|trackland"

# Look for HTTP callouts or file handling
find . -name "*.cls" | xargs grep -l "HttpRequest\|HttpResponse\|Blob\|Document__c"
```

### Static Resources (.resource files)
```bash
# Look for PDF libraries
find . -name "*.resource" | xargs file | grep -i "zip\|javascript\|pdf"

# Common PDF libraries to look for:
# - pdf.js
# - PDFTron
# - PDF-lib
# - Adobe PDF SDK
```

### Custom Objects (.object files)
```bash
# Check DocListEntry__c definition
cat force-app/main/default/objects/DocListEntry__c/DocListEntry__c.object-meta.xml

# Look for field definitions
ls force-app/main/default/objects/DocListEntry__c/fields/
```

## Automated Script to Find PDF Components

```bash
#!/bin/bash
echo "🔍 Searching for PDF/Document related code..."

echo "\n📁 Lightning Components:"
find . -path "*/lwc/*" -name "*.js" -o -name "*.html" | xargs grep -l -i "pdf\|viewer\|document\|annotation" 2>/dev/null

echo "\n⚡ Aura Components:"
find . -path "*/aura/*" -name "*.cmp" -o -name "*.js" | xargs grep -l -i "pdf\|viewer\|document\|annotation" 2>/dev/null

echo "\n🎯 Apex Classes:"
find . -name "*.cls" | xargs grep -l -i "pdf\|viewer\|document\|trackland\|s3" 2>/dev/null

echo "\n📦 Static Resources:"
find . -name "*.resource" -o -name "*.resource-meta.xml" | xargs grep -l -i "pdf\|viewer\|document" 2>/dev/null

echo "\n🔧 Custom Objects:"
find . -path "*/objects/*" -name "*.object-meta.xml" | xargs grep -l -i "pdf\|viewer\|document" 2>/dev/null

echo "\n🌊 Flows:"
find . -path "*/flows/*" -name "*.flow-meta.xml" | xargs grep -l -i "pdf\|viewer\|document" 2>/dev/null
```

## Quick Start for Your Situation

### 1. Install Salesforce CLI and extract Lightning Components:
```bash
npm install -g @salesforce/cli
sf org login web --alias incitetax
sf project generate --name pdf-investigation
cd pdf-investigation
sf project retrieve start --metadata "LightningComponentBundle"
```

### 2. Search the extracted code:
```bash
# Find PDF viewers
find . -name "*.js" -o -name "*.html" -o -name "*.cmp" | xargs grep -l -i "pdf\|viewer\|PageCount"

# Look for S3 or trackland references
find . -name "*.js" -o -name "*.cls" | xargs grep -l -i "trackland\|s3\|Document__c"
```

### 3. Check browser network tab:
- Open PDF viewer in Salesforce
- F12 → Network tab → reload
- Look for component loads and JavaScript files

## Expected Findings

You'll likely find:
- **Lightning Web Component** or **Aura Component** for PDF viewing
- **Static Resource** containing PDF.js, PDFTron, or similar library
- **Apex Controller** handling file URLs and metadata
- **Custom CSS/JS** for annotation functionality

Would you like me to create a script that automates this extraction process for you? 