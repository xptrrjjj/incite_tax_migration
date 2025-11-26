# Salesforce Storage Analysis

## Purpose

This analysis determines what is consuming Incite Tax's Salesforce storage capacity. This is **separate** from the S3 migration project.

## Running the Analysis

```bash
python complete_storage_analysis.py
```

This script will:
1. Discover all Salesforce objects (standard, custom, and file-related)
2. Count records in each object
3. Estimate storage consumption for files vs data
4. Identify top storage consumers
5. Provide definitive diagnosis of storage issue

## Expected Output

The script analyzes:

### 1. File Storage
- ContentDocument (primary file storage)
- ContentVersion (file versions)
- Attachment (legacy attachments)
- Document (classic documents)

### 2. Data Storage
- All custom objects (especially Trackland objects)
- Key standard objects (Account, Contact, etc.)

### 3. Limits
- ContentDocument limit (30M max)
- API available limits

## Understanding the Results

### If File Storage is the Issue
- **Symptom**: Many ContentDocuments/files (>10,000)
- **Solution**: S3 migration WILL help
- **Outcome**: Moving files to S3 frees file storage space

### If Data Storage is the Issue
- **Symptom**: Many records (>5M) but few files (<1,000)
- **Solution**: S3 migration will NOT help
- **Reason**: Records stay in Salesforce (only URLs change)
- **Real Solution**: Delete/archive old records

## Key Metrics to Check

After running the script, look for:

1. **File:Data Ratio**
   - <0.05 = Data storage issue
   - >0.5 = File storage issue
   - Between = Mixed usage

2. **Top Storage Consumers**
   - Which objects have the most records?
   - Is it Trackland objects (DocListEntry__c, etc.)?

3. **ContentDocument Limit**
   - Are you near the 30M limit?

## Verification

The script estimates storage based on:
- Files: ~1MB average per file
- Records: ~2KB average per record

**To verify actual limits:**
1. Go to Salesforce Setup
2. Navigate to System Overview
3. Check "Storage Usage" section
4. Compare actual vs estimated values

## Analysis Duration

Expected runtime: 3-10 minutes depending on number of custom objects.

## Next Steps

Based on results:
- **Data Storage Issue** → Implement archival/deletion strategy
- **File Storage Issue** → Proceed with S3 migration
- **Mixed** → May need both approaches
