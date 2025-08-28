# Visual Workflow Diagrams

## Migration Decision Tree

```mermaid
flowchart TD
    START([Start Migration Project]) --> SIZE{How many files?}
    
    SIZE -->|< 100K files| SINGLE[Single-Phase Migration<br/>salesforce_s3_migration.py]
    SIZE -->|100K+ files| TWOPHASE[Two-Phase Migration<br/>Recommended]
    
    SINGLE --> CONFIG1[Configure for Single-Phase]
    TWOPHASE --> CONFIG2[Configure for Two-Phase]
    
    CONFIG1 --> STEST[Test with Single Account]
    CONFIG2 --> TTEST[Test with Single Account]
    
    STEST --> SRUN[Run Single Migration]
    TTEST --> P1[Phase 1: Backup Only]
    
    P1 --> P1CHECK{Phase 1 Complete?}
    P1CHECK -->|No| P1RESUME[Resume/Fix Issues]
    P1RESUME --> P1
    P1CHECK -->|Yes| P2[Phase 2: Full Migration]
    
    SRUN --> DONE[Migration Complete]
    P2 --> DONE
    
    style TWOPHASE fill:#e1f5fe
    style P1 fill:#e8f5e8
    style P2 fill:#fff3e0
    style DONE fill:#c8e6c9
```

## Two-Phase Migration Workflow

```mermaid
flowchart TB
    subgraph "Phase 1: Backup Only (Safe)"
        P1START([Phase 1 Start]) --> P1AUTH{Authenticate}
        P1AUTH --> P1QUERY[Query DocListEntry__c]
        P1QUERY --> P1PROCESS[Process Files in Batches]
        P1PROCESS --> P1DOWNLOAD[Download from External S3]
        P1DOWNLOAD --> P1UPLOAD[Upload to Your S3]
        P1UPLOAD --> P1TRACK[Track in Database]
        P1TRACK --> P1MORE{More Files?}
        P1MORE -->|Yes| P1PROCESS
        P1MORE -->|No| P1DONE[Phase 1 Complete]
        
        style P1START fill:#e1f5fe
        style P1DONE fill:#e8f5e8
        style P1TRACK fill:#f3e5f5
    end
    
    subgraph "Phase 2: Full Migration"
        P2START([Phase 2 Start]) --> P2VALIDATE{Validate Backup}
        P2VALIDATE --> P2AUTH{Authenticate}
        P2AUTH --> P2COMPARE[Compare Current vs Backup]
        P2COMPARE --> P2NEW{New Files?}
        P2NEW -->|Yes| P2COPY[Copy New Files]
        P2NEW -->|No| P2UPDATE[Update Salesforce URLs]
        P2COPY --> P2UPDATE
        P2UPDATE --> P2VERIFY[Verify Migration]
        P2VERIFY --> P2ROLLBACK[Save Rollback Data]
        P2ROLLBACK --> P2DONE[Migration Complete]
        
        style P2START fill:#fff3e0
        style P2DONE fill:#c8e6c9
        style P2UPDATE fill:#ffecb3
    end
    
    P1DONE --> P2START
```

## System State Transitions

```mermaid
stateDiagram-v2
    [*] --> NotStarted : Initial State
    
    NotStarted --> BackupInProgress : Start Phase 1
    BackupInProgress --> BackupComplete : Phase 1 Success
    BackupInProgress --> BackupFailed : Phase 1 Failure
    
    BackupFailed --> BackupInProgress : Retry Phase 1
    BackupComplete --> MigrationInProgress : Start Phase 2
    
    MigrationInProgress --> FullyMigrated : Phase 2 Success
    MigrationInProgress --> MigrationFailed : Phase 2 Failure
    
    MigrationFailed --> BackupComplete : Rollback
    FullyMigrated --> BackupComplete : Emergency Rollback
    
    state BackupComplete {
        [*] --> FilesBackedUp
        FilesBackedUp --> ReadyForMigration
    }
    
    state FullyMigrated {
        [*] --> UsersOnYourS3
        UsersOnYourS3 --> MigrationSuccess
    }
```

## User Impact During Migration

```mermaid
flowchart LR
    subgraph "Migration Phases"
        P1[Phase 1: Backup Only<br/>Users unaffected<br/>External S3 active]
        P2[Phase 2: Switchover<br/>Brief transition<br/>Move to Your S3]  
        P3[Post-Migration<br/>Users on Your S3<br/>Normal operations]
    end
    
    P1 --> P2
    P2 --> P3
    
    style P1 fill:#e8f5e8
    style P2 fill:#fff3e0  
    style P3 fill:#c8e6c9
```

## Error Handling Flow

```mermaid
flowchart TD
    ERROR([Error Occurs]) --> TYPE{Error Type?}
    
    TYPE -->|Auth Error| AUTHFIX[Fix Credentials<br/>Restart Process]
    TYPE -->|Network Error| NETFIX[Check Connectivity<br/>Retry Operation]
    TYPE -->|File Error| FILEFIX[Log & Skip File<br/>Continue Processing]
    TYPE -->|Database Error| DBFIX[Check Database<br/>Resume from Checkpoint]
    
    AUTHFIX --> RESUME[Resume Migration]
    NETFIX --> RESUME
    FILEFIX --> RESUME
    DBFIX --> RESUME
    
    RESUME --> SUCCESS{Successful?}
    SUCCESS -->|Yes| CONTINUE[Continue Migration]
    SUCCESS -->|No| ESCALATE[Manual Investigation]
    
    ESCALATE --> ROLLBACK{Need Rollback?}
    ROLLBACK -->|Yes| EMERGENCY[Emergency Rollback]
    ROLLBACK -->|No| FIX[Fix Issue & Retry]
    
    FIX --> RESUME
    EMERGENCY --> SAFE[Users Back to External S3]
    
    style ERROR fill:#ffebee
    style EMERGENCY fill:#f44336,color:#fff
    style SAFE fill:#4caf50,color:#fff
```

## Database Growth Pattern

```mermaid
xychart-beta
    title "Database Size Growth During Migration"
    x-axis ["Start", "25%", "50%", "75%", "Complete", "Post-Migration"]
    y-axis "Database Size (GB)" 0 --> 2.5
    line [0, 0.4, 0.9, 1.5, 2.0, 2.0]
```

## Performance Monitoring Dashboard

```mermaid
quadrantChart
    title Migration Performance Metrics
    x-axis "Processing Speed" --> "High Speed"
    y-axis "Success Rate" --> "High Success"
    
    "Optimal Zone": [0.8, 0.9]
    "Speed Issues": [0.3, 0.9]
    "Quality Issues": [0.8, 0.6]
    "Problem Zone": [0.3, 0.6]
    "Current Status": [0.7, 0.85]
```

## Batch Processing Flow

```mermaid
sequenceDiagram
    participant Script as Migration Script
    participant SF as Salesforce
    participant ES3 as External S3
    participant YS3 as Your S3
    participant DB as Database
    
    Script->>SF: Get batch of 100 DocListEntry records
    SF-->>Script: Return records
    
    loop For each record in batch
        Script->>ES3: Download file
        ES3-->>Script: File content
        Script->>YS3: Upload file
        YS3-->>Script: Confirm upload
        Script->>DB: Record metadata
        Note over Script: Progress: 1/100
    end
    
    Script->>DB: Update batch statistics
    Note over Script: Batch complete: 100/100
    Script->>Script: Get next batch
```

## Rollback Decision Tree

```mermaid
flowchart TD
    ISSUE([Migration Issue Detected]) --> SEVERITY{Issue Severity?}
    
    SEVERITY -->|Low| CONTINUE[Log & Continue]
    SEVERITY -->|Medium| PAUSE[Pause & Investigate]
    SEVERITY -->|High| ASSESS{Data at Risk?}
    
    ASSESS -->|No| FIX[Fix Issue & Resume]
    ASSESS -->|Yes| IMMEDIATE[Immediate Rollback]
    
    CONTINUE --> MONITOR[Monitor Progress]
    PAUSE --> DECISION{Can Fix Quickly?}
    
    DECISION -->|Yes| FIX
    DECISION -->|No| SCHEDULE[Schedule Rollback]
    
    FIX --> RESUME[Resume Migration]
    IMMEDIATE --> ROLLBACK[Execute Rollback]
    SCHEDULE --> ROLLBACK
    
    ROLLBACK --> VERIFY[Verify Rollback Success]
    VERIFY --> SAFE[Users Safe on External S3]
    
    style IMMEDIATE fill:#f44336,color:#fff
    style ROLLBACK fill:#ff9800,color:#fff
    style SAFE fill:#4caf50,color:#fff
```

## S3 File Organization Structure

```mermaid
graph TB
    subgraph "Your S3 Bucket Structure"
        ROOT[your-migration-bucket/]
        UPLOADS[uploads/]
        
        subgraph "Account Organization"
            ACC1[0013D00000AbcDef/<br/>Account ID]
            ACC1NAME[Acme_Corporation/<br/>Clean Account Name]
            FILES1[• invoice_2024.pdf<br/>• contract_v2.docx<br/>• presentation.pptx]
            
            ACC2[0013D00000XyzAbc/<br/>Account ID]  
            ACC2NAME[Beta_Solutions_Inc/<br/>Clean Account Name]
            FILES2[• proposal.pdf<br/>• analysis.xlsx<br/>• meeting_notes.docx]
        end
    end
    
    ROOT --> UPLOADS
    UPLOADS --> ACC1
    UPLOADS --> ACC2
    ACC1 --> ACC1NAME
    ACC2 --> ACC2NAME
    ACC1NAME --> FILES1
    ACC2NAME --> FILES2
    
    style ROOT fill:#fff8e1
    style UPLOADS fill:#e8f5e8
    style ACC1 fill:#e1f5fe
    style ACC2 fill:#e1f5fe
```

## Migration Phases Overview

```mermaid
flowchart TD
    subgraph "Setup Phase"
        SETUP1[Configure Credentials]
        SETUP2[Test Single Account]  
        SETUP3[Performance Tuning]
    end
    
    subgraph "Phase 1: Backup"
        P1_1[Start Full Backup]
        P1_2[Monitor Progress]
        P1_3[Address Errors]
        P1_4[Complete Backup]
    end
    
    subgraph "Phase 2: Migration" 
        P2_1[Dry Run Testing]
        P2_2[User Communication]
        P2_3[Execute Migration]
        P2_4[Validate Results]
    end
    
    SETUP1 --> SETUP2 --> SETUP3
    SETUP3 --> P1_1 --> P1_2 --> P1_3 --> P1_4
    P1_4 --> P2_1 --> P2_2 --> P2_3 --> P2_4
    
    style SETUP1 fill:#e1f5fe
    style P1_1 fill:#e8f5e8
    style P2_3 fill:#fff3e0
```

---

*These visual workflows provide quick understanding of the migration process flow, decision points, and system states throughout the migration lifecycle.*