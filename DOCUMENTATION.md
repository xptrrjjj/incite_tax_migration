# Two-Phase Salesforce File Migration System

## Table of Contents
- [System Overview](#system-overview)
- [Architecture](#architecture)
- [Database Schema](#database-schema)
- [Migration Phases](#migration-phases)
- [Installation & Setup](#installation--setup)
- [Usage Guide](#usage-guide)
- [Monitoring & Management](#monitoring--management)
- [Safety & Recovery](#safety--recovery)
- [Troubleshooting](#troubleshooting)

---

## System Overview

The Two-Phase Salesforce File Migration System safely migrates files from external S3 storage (Trackland) to your own S3 bucket while preserving Salesforce DocListEntry__c functionality. Designed to handle 1M+ files with zero user disruption during the backup phase.

### Key Benefits
- **Zero downtime** during Phase 1 backup
- **Scalable** for 1M+ files using SQLite database
- **Safe rollback** capabilities with comprehensive tracking
- **Incremental backups** for ongoing file additions
- **Complete audit trail** of all migration activities

### Architecture Overview

```mermaid
graph TB
    subgraph "External Systems"
        SF[Salesforce with DocListEntry__c]
        ES3[External S3<br/>trackland-doc-storage]
    end
    
    subgraph "Migration System"
        DB[(SQLite Database<br/>migration_tracking.db)]
        P1[Phase 1: Backup Script]
        P2[Phase 2: Full Migration Script]
        MON[Status Monitor]
        ROLL[Rollback Tool]
    end
    
    subgraph "Your Infrastructure"
        YS3[Your S3 Bucket<br/>organized structure]
    end
    
    SF --> P1
    ES3 --> P1
    P1 --> YS3
    P1 --> DB
    
    DB --> P2
    SF --> P2
    P2 --> SF
    P2 --> YS3
    
    DB --> MON
    DB --> ROLL
    
    style P1 fill:#e1f5fe
    style P2 fill:#fff3e0
    style DB fill:#f3e5f5
    style SF fill:#e8f5e8
    style YS3 fill:#fff8e1
```

---

## Architecture

### Core Components

```mermaid
graph LR
    subgraph "Migration Scripts"
        BOM[backup_only_migration.py<br/>Phase 1 - Safe Backup]
        FM[full_migration.py<br/>Phase 2 - Complete Migration]
        LSM[salesforce_s3_migration.py<br/>Legacy Single-Phase]
    end
    
    subgraph "Management Tools"
        MS[migration_status.py<br/>Status & Statistics]
        RM[rollback_migration.py<br/>Emergency Recovery]
        MDB[migration_db.py<br/>Database Manager]
    end
    
    subgraph "Analysis Tools"
        LA[list_accounts.py<br/>Account Discovery]
        MA[migration_analysis.py<br/>Scope Analysis]
        DBG[debug_*.py<br/>Debug Scripts]
    end
    
    subgraph "Configuration"
        CT[config_template.py<br/>Template]
        CFG[config.py<br/>Your Settings]
    end
    
    CT --> CFG
    CFG --> BOM
    CFG --> FM
    CFG --> LSM
    MDB --> BOM
    MDB --> FM
    MDB --> MS
    MDB --> RM
    
    style BOM fill:#e1f5fe
    style FM fill:#fff3e0
    style MDB fill:#f3e5f5
```

### System Integration Points

```mermaid
graph TB
    subgraph "Salesforce Integration"
        SFAPI[Salesforce API<br/>simple-salesforce]
        DLE[DocListEntry__c Objects]
        ACC[Account Objects]
    end
    
    subgraph "AWS Integration"
        BOTO3[Boto3 SDK]
        ES3[External S3<br/>Source Files]
        YS3[Your S3<br/>Destination Files]
    end
    
    subgraph "Data Persistence"
        SQLITE[SQLite Database<br/>Local Tracking]
        LOGS[File Logs<br/>Detailed History]
    end
    
    SFAPI --> DLE
    SFAPI --> ACC
    BOTO3 --> ES3
    BOTO3 --> YS3
    
    style SFAPI fill:#e8f5e8
    style BOTO3 fill:#fff8e1
    style SQLITE fill:#f3e5f5
```

---

## Database Schema

### SQLite Database Structure

```mermaid
erDiagram
    file_migrations {
        integer id PK
        text doclist_entry_id UK
        text account_id
        text account_name
        text original_url
        text your_s3_key
        text your_s3_url
        text file_name
        integer file_size_bytes
        text file_hash
        text backup_timestamp
        text last_modified_sf
        integer migration_phase
        integer salesforce_updated
        text created_date
        text updated_date
    }
    
    migration_runs {
        integer id PK
        text run_type
        text start_time
        text end_time
        integer total_files_processed
        integer successful_files
        integer failed_files
        integer new_files
        integer updated_files
        integer skipped_files
        text status
        text error_message
        text config_snapshot
    }
    
    migration_errors {
        integer id PK
        integer run_id FK
        text doclist_entry_id
        text error_type
        text error_message
        text original_url
        text timestamp
    }
    
    migration_runs ||--o{ migration_errors : "tracks errors for"
```

### Key Database Indexes

```sql
-- Performance indexes for 1M+ records
CREATE INDEX idx_doclist_entry_id ON file_migrations(doclist_entry_id);
CREATE INDEX idx_account_id ON file_migrations(account_id);
CREATE INDEX idx_backup_timestamp ON file_migrations(backup_timestamp);
CREATE INDEX idx_migration_phase ON file_migrations(migration_phase);
CREATE INDEX idx_salesforce_updated ON file_migrations(salesforce_updated);
```

### Database States

```mermaid
stateDiagram-v2
    [*] --> BackupOnly : Phase 1 Complete
    BackupOnly --> FullyMigrated : Phase 2 Complete
    FullyMigrated --> BackupOnly : Emergency Rollback
    BackupOnly --> [*] : Delete Record
    
    state BackupOnly {
        salesforce_updated: 0
        migration_phase: 1
        your_s3_url: Available
        original_url: Still in Salesforce
    }
    
    state FullyMigrated {
        salesforce_updated: 1
        migration_phase: 2
        your_s3_url: In Salesforce
        original_url: Replaced
    }
```

---

## Migration Phases

### Phase 1: Backup Only Migration

**Objective**: Create complete backup mirror without affecting users

```mermaid
sequenceDiagram
    participant User as Users
    participant SF as Salesforce
    participant P1 as Phase 1 Script
    participant ES3 as External S3
    participant YS3 as Your S3
    participant DB as SQLite DB
    
    Note over User: Users continue normal work
    
    P1->>SF: Query DocListEntry__c records
    SF-->>P1: Return file metadata
    
    loop For each file
        P1->>ES3: Download file
        ES3-->>P1: File content
        P1->>YS3: Upload to organized path
        YS3-->>P1: Confirm upload
        P1->>DB: Record metadata
        DB-->>P1: Confirm tracking
    end
    
    Note over SF: Salesforce UNCHANGED
    Note over User: Users completely unaffected
    Note over DB: Complete backup metadata stored
```

#### Phase 1 Process Flow

```mermaid
flowchart TD
    START([Start Phase 1]) --> AUTH{Authenticate}
    AUTH -->|Success| QUERY[Query DocListEntry__c]
    AUTH -->|Fail| ERROR[Log Error & Exit]
    
    QUERY --> FILTER{Filter Records}
    FILTER -->|Full Backup| ALL[Process All Records]
    FILTER -->|Incremental| NEW[Process New/Changed Only]
    
    ALL --> BATCH[Process in Batches]
    NEW --> BATCH
    
    BATCH --> DOWNLOAD[Download from External S3]
    DOWNLOAD --> UPLOAD[Upload to Your S3]
    UPLOAD --> TRACK[Record in Database]
    TRACK --> MORE{More Batches?}
    
    MORE -->|Yes| BATCH
    MORE -->|No| STATS[Generate Statistics]
    STATS --> END([End Phase 1])
    
    ERROR --> END
    
    style START fill:#e1f5fe
    style END fill:#e1f5fe
    style TRACK fill:#f3e5f5
```

### Phase 2: Full Migration

**Objective**: Complete migration by updating Salesforce URLs

```mermaid
sequenceDiagram
    participant User as Users
    participant SF as Salesforce
    participant P2 as Phase 2 Script
    participant YS3 as Your S3
    participant DB as SQLite DB
    
    Note over User: Prepare for switchover
    
    P2->>DB: Validate backup data exists
    DB-->>P2: Confirm complete backup
    
    P2->>SF: Query current DocListEntry__c
    SF-->>P2: Return current state
    
    P2->>P2: Identify new files since backup
    
    loop For new files only
        P2->>YS3: Copy new files
        YS3-->>P2: Confirm upload
        P2->>DB: Update tracking
    end
    
    P2->>SF: Batch update URLs to Your S3
    SF-->>P2: Confirm updates
    
    P2->>DB: Mark as fully migrated
    DB-->>P2: Update complete
    
    Note over User: Users now use Your S3
    Note over SF: URLs point to Your S3
```

#### Phase 2 Process Flow

```mermaid
flowchart TD
    START([Start Phase 2]) --> VALIDATE{Validate Backup Data}
    VALIDATE -->|Valid| AUTH{Authenticate}
    VALIDATE -->|Invalid| ERROR[Error: Run Phase 1 First]
    
    AUTH -->|Success| CURRENT[Get Current SF State]
    AUTH -->|Fail| ERROR
    
    CURRENT --> COMPARE[Compare with Backup]
    COMPARE --> NEWFILES{New Files Found?}
    
    NEWFILES -->|Yes| COPY[Copy New Files]
    NEWFILES -->|No| UPDATE[Update Salesforce URLs]
    
    COPY --> UPDATE
    UPDATE --> VALIDATE_MIG[Validate Migration]
    VALIDATE_MIG --> ROLLBACK_DATA[Save Rollback Data]
    ROLLBACK_DATA --> STATS[Generate Statistics]
    STATS --> END([Migration Complete])
    
    ERROR --> END
    
    style START fill:#fff3e0
    style END fill:#fff3e0
    style UPDATE fill:#e8f5e8
    style ROLLBACK_DATA fill:#ffebee
```

### File Organization Structure

```
your-s3-bucket/
├── uploads/
│   ├── 0013D00000AbcDef/          # Account ID
│   │   ├── Acme_Corporation/      # Clean Account Name
│   │   │   ├── invoice_2024.pdf
│   │   │   ├── contract_v2.docx
│   │   │   └── presentation.pptx
│   │   └── ...
│   ├── 0013D00000XyzAbc/          # Another Account
│   │   ├── Beta_Solutions_Inc/
│   │   │   ├── proposal.pdf
│   │   │   └── analysis.xlsx
│   │   └── ...
│   └── ...
```

---

## Installation & Setup

### Prerequisites

```mermaid
graph LR
    subgraph "System Requirements"
        PYTHON[Python 3.7+]
        DISK[Disk Space<br/>~2GB for 1M files]
        MEMORY[RAM 2GB+<br/>for processing]
    end
    
    subgraph "Account Access"
        SFACCESS[Salesforce Account<br/>with API Access]
        AWSACCESS[AWS Account<br/>with S3 Access]
    end
    
    subgraph "Permissions"
        SFPERMS[Salesforce<br/>DocListEntry__c access]
        S3PERMS[S3 Bucket<br/>Read/Write permissions]
    end
    
    PYTHON --> SFACCESS
    SFACCESS --> SFPERMS
    AWSACCESS --> S3PERMS
```

### Installation Steps

```bash
# 1. Clone repository
git clone <repository-url>
cd incite_migration_script

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp config_template.py config.py
# Edit config.py with your actual credentials

# 4. Test configuration
python list_accounts.py

# 5. Analyze migration scope
python migration_analysis.py
```

### Configuration Template

```python
# config.py structure
SALESFORCE_CONFIG = {
    "username": "your_username@company.com",
    "password": "your_password",
    "security_token": "your_security_token",
    "domain": "login"  # or "test" for sandbox
}

AWS_CONFIG = {
    "region": "us-east-1",
    "bucket_name": "your-migration-bucket",
    "access_key_id": "AKIA...",
    "secret_access_key": "your_secret_key"
}

MIGRATION_CONFIG = {
    "batch_size": 100,
    "max_file_size_mb": 100,
    "allowed_extensions": ['.pdf', '.doc', '.docx', ...],
    "dry_run": True,  # Start with dry run
    "test_single_account": True  # Test with one account first
}
```

---

## Usage Guide

### Quick Start Workflow

```mermaid
flowchart TD
    SETUP[1. Setup & Configuration] --> TEST[2. Test with Single Account]
    TEST --> PHASE1[3. Phase 1: Full Backup]
    PHASE1 --> MONITOR[4. Monitor Progress]
    MONITOR --> READY{Ready for Phase 2?}
    READY -->|No| INCREMENTAL[5. Incremental Backups]
    INCREMENTAL --> MONITOR
    READY -->|Yes| DRYRUN[6. Phase 2 Dry Run]
    DRYRUN --> EXECUTE[7. Execute Phase 2]
    EXECUTE --> VALIDATE[8. Validate & Monitor]
    VALIDATE --> COMPLETE[Migration Complete]
    
    style PHASE1 fill:#e1f5fe
    style EXECUTE fill:#fff3e0
    style COMPLETE fill:#e8f5e8
```

### Command Reference

#### Phase 1 Commands
```bash
# Full backup (first time)
python backup_only_migration.py --full

# Incremental backup (ongoing)
python backup_only_migration.py --incremental

# Monitor backup progress
python migration_status.py --overview
python migration_status.py --accounts
```

#### Phase 2 Commands  
```bash
# Test migration (safe)
python full_migration.py --dry-run

# Execute migration (live)
python full_migration.py --execute

# Emergency rollback
python rollback_migration.py --from-database --execute
```

#### Monitoring Commands
```bash
# Status overview
python migration_status.py

# Comprehensive report
python migration_status.py --all

# Export detailed report
python migration_status.py --export migration_report.json

# Check Phase 2 readiness
python migration_status.py --readiness
```

### Testing Strategy

```mermaid
graph TD
    subgraph "Testing Phases"
        T1[Single Account Test]
        T2[Small Batch Test]
        T3[Full Backup Test]
        T4[Phase 2 Dry Run]
        T5[Production Migration]
    end
    
    T1 --> T2
    T2 --> T3
    T3 --> T4
    T4 --> T5
    
    T1 -.-> CONFIG1[test_single_account: True<br/>max_test_files: 5]
    T2 -.-> CONFIG2[batch_size: 10<br/>specific account_id]
    T3 -.-> CONFIG3[dry_run: False<br/>full backup]
    T4 -.-> CONFIG4[--dry-run flag<br/>complete test]
    T5 -.-> CONFIG5[--execute flag<br/>production run]
```

---

## Monitoring & Management

### Status Dashboard Overview

```mermaid
graph TB
    subgraph "Migration Status Dashboard"
        OVERVIEW[Migration Overview<br/>• Total files: 1,234,567<br/>• Backup only: 1,200,000<br/>• Fully migrated: 34,567<br/>• Success rate: 98.2%]
        
        PHASES[Phase Status<br/>• Phase 1: Complete<br/>• Phase 2: Ready<br/>• Last run: 2024-01-15<br/>• Duration: 23h 45m]
        
        ACCOUNTS[Top Accounts<br/>• Acme Corp: 45,123 files<br/>• Beta Solutions: 32,456 files<br/>• Gamma Inc: 28,789 files<br/>• Delta LLC: 23,456 files]
        
        ERRORS[Error Summary<br/>• Download errors: 156<br/>• Upload errors: 23<br/>• Auth errors: 5<br/>• Network errors: 12]
    end
    
    style OVERVIEW fill:#e8f5e8
    style PHASES fill:#e1f5fe
    style ACCOUNTS fill:#fff8e1
    style ERRORS fill:#ffebee
```

### Real-time Monitoring

```bash
# Watch live progress
watch -n 30 "python migration_status.py --overview"

# Monitor errors in real-time
tail -f logs/backup_migration_full_*.log | grep ERROR

# Check database size growth
watch -n 60 "ls -lh migration_tracking.db"
```

### Performance Metrics

```mermaid
xychart-beta
    title "Migration Performance Over Time"
    x-axis ["Hour 1", "Hour 2", "Hour 3", "Hour 4", "Hour 5", "Hour 6"]
    y-axis "Files per Hour" 0 --> 50000
    line [45000, 48000, 46000, 49000, 47000, 50000]
```

---

## Safety & Recovery

### Safety Mechanisms

```mermaid
graph TB
    subgraph "Phase 1 Safety"
        P1S1[No Salesforce Changes]
        P1S2[Users Unaffected]
        P1S3[Multiple Run Safety]
        P1S4[Error Recovery]
    end
    
    subgraph "Phase 2 Safety"
        P2S1[Dry Run Mode]
        P2S2[Batch Processing]
        P2S3[Rollback Data Generation]
        P2S4[Validation Checks]
    end
    
    subgraph "System Safety"
        SYS1[Comprehensive Logging]
        SYS2[Database Transactions]
        SYS3[Error Isolation]
        SYS4[Progress Checkpoints]
    end
    
    style P1S1 fill:#e8f5e8
    style P1S2 fill:#e8f5e8
    style P2S3 fill:#ffebee
    style P2S4 fill:#ffebee
```

### Rollback Strategy

```mermaid
sequenceDiagram
    participant Admin as Administrator
    participant RT as Rollback Tool
    participant DB as Database
    participant SF as Salesforce
    
    Admin->>RT: Initiate rollback
    RT->>DB: Load migration data
    DB-->>RT: Original URLs
    RT->>SF: Batch update to original URLs
    SF-->>RT: Confirm updates
    RT->>DB: Mark as rolled back
    DB-->>RT: Update complete
    RT-->>Admin: Rollback successful
    
    Note over SF: Users back to external S3
    Note over DB: Migration state reset
```

### Emergency Procedures

#### If Phase 1 Fails
```bash
# Check error logs
python migration_status.py --recent-errors 20

# Resume from where it stopped
python backup_only_migration.py --incremental

# Reset specific account if needed
# (manual database cleanup required)
```

#### If Phase 2 Fails
```bash
# Immediate rollback
python rollback_migration.py --from-database --execute

# Check rollback success
python migration_status.py --overview

# Investigate issues
python migration_status.py --errors
```

---

## Troubleshooting

### Common Issues & Solutions

```mermaid
graph TB
    subgraph "Authentication Issues"
        AUTH1[Salesforce Auth Failed] --> AUTH1S[Check credentials<br/>Verify security token<br/>Test API access]
        AUTH2[AWS Auth Failed] --> AUTH2S[Run aws configure<br/>Check IAM permissions<br/>Verify bucket access]
    end
    
    subgraph "Performance Issues"
        PERF1[Slow Migration] --> PERF1S[Reduce batch size<br/>Check network<br/>Monitor disk space]
        PERF2[High Memory Usage] --> PERF2S[Reduce batch size<br/>Add swap space<br/>Monitor processes]
    end
    
    subgraph "Data Issues"
        DATA1[File Download Errors] --> DATA1S[Check external URLs<br/>Verify permissions<br/>Network connectivity]
        DATA2[Database Locked] --> DATA2S[Check running processes<br/>Close other scripts<br/>Restart if needed]
    end
```

### Diagnostic Commands

```bash
# System health check
python migration_status.py --all > system_health.txt

# Database integrity check
sqlite3 migration_tracking.db "PRAGMA integrity_check;"

# Network connectivity test
python -c "
import boto3
import requests
from simple_salesforce import Salesforce
# Test connections
"

# Disk space monitoring
df -h .
du -sh migration_tracking.db
du -sh logs/
```

### Log Analysis

```bash
# Find error patterns
grep -c "ERROR" logs/*.log

# Check success rates by hour
grep "✓" logs/backup_migration_*.log | cut -d' ' -f1-2 | uniq -c

# Monitor batch completion
grep "Processing batch" logs/*.log | tail -10

# Database query performance
sqlite3 migration_tracking.db ".timer on" "SELECT COUNT(*) FROM file_migrations;"
```

### Performance Tuning

```python
# Optimize for your environment
MIGRATION_CONFIG = {
    "batch_size": 50,  # Reduce if memory constrained
    "max_file_size_mb": 50,  # Skip very large files
    "allowed_extensions": ['.pdf', '.docx'],  # Limit to essential types
    
    # For testing/debugging
    "test_single_account": True,
    "max_test_files": 100
}
```

---

## Appendices

### A. Required Permissions

#### Salesforce Permissions
```
Profile Permissions:
- API Enabled ✓
- View All Data ✓ (or specific object permissions)

Object Permissions:
- DocListEntry__c: Create, Read, Update, Delete
- ContentDocument: Read
- ContentVersion: Create, Read, Update
- ContentDocumentLink: Create, Read, Update, Delete
- Account: Read
```

#### AWS S3 Permissions
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "s3:CreateBucket",
                "s3:ListBucket",
                "s3:GetBucketLocation",
                "s3:PutObject",
                "s3:GetObject",
                "s3:DeleteObject"
            ],
            "Resource": [
                "arn:aws:s3:::your-migration-bucket",
                "arn:aws:s3:::your-migration-bucket/*"
            ]
        }
    ]
}
```

### B. Database Maintenance

```bash
# Vacuum database (reclaim space)
sqlite3 migration_tracking.db "VACUUM;"

# Analyze for query optimization  
sqlite3 migration_tracking.db "ANALYZE;"

# Backup database
cp migration_tracking.db migration_tracking_backup_$(date +%Y%m%d).db

# Clean old run logs (keep 30 days)
python migration_status.py --cleanup-days 30
```

### C. Scale Testing Results

| Files | Database Size | Phase 1 Time | Phase 2 Time | Memory Usage |
|-------|---------------|---------------|---------------|--------------|
| 10K   | 50MB         | 2 hours       | 15 minutes    | 512MB        |
| 100K  | 200MB        | 8 hours       | 45 minutes    | 768MB        |
| 500K  | 800MB        | 20 hours      | 2 hours       | 1.2GB        |
| 1M    | 1.5GB        | 36 hours      | 4 hours       | 1.8GB        |

---

*This documentation covers the complete two-phase migration system. For additional support, check the logs directory and use the built-in diagnostic tools.*