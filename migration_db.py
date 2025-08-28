#!/usr/bin/env python3
"""
Migration Database Manager
=========================

SQLite database manager for tracking file migrations across phases.
Handles 1M+ records efficiently with indexing and chunked operations.
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import logging

class MigrationDB:
    """Database manager for migration tracking."""
    
    def __init__(self, db_path: str = "migration_tracking.db"):
        """Initialize database connection and create tables if needed."""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        self.logger = logging.getLogger(__name__)
        self._create_tables()
        self._create_indexes()
    
    def _create_tables(self):
        """Create database tables for migration tracking."""
        self.conn.executescript('''
            -- Main file tracking table
            CREATE TABLE IF NOT EXISTS file_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doclist_entry_id TEXT NOT NULL UNIQUE,
                account_id TEXT NOT NULL,
                account_name TEXT NOT NULL,
                original_url TEXT NOT NULL,
                your_s3_key TEXT NOT NULL,
                your_s3_url TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size_bytes INTEGER,
                file_hash TEXT,
                backup_timestamp TEXT NOT NULL,
                last_modified_sf TEXT,
                migration_phase INTEGER NOT NULL DEFAULT 1,
                salesforce_updated INTEGER NOT NULL DEFAULT 0,
                created_date TEXT NOT NULL,
                updated_date TEXT NOT NULL
            );
            
            -- Migration run log table
            CREATE TABLE IF NOT EXISTS migration_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_type TEXT NOT NULL,  -- 'backup', 'full_migration', 'incremental'
                start_time TEXT NOT NULL,
                end_time TEXT,
                total_files_processed INTEGER DEFAULT 0,
                successful_files INTEGER DEFAULT 0,
                failed_files INTEGER DEFAULT 0,
                new_files INTEGER DEFAULT 0,
                updated_files INTEGER DEFAULT 0,
                skipped_files INTEGER DEFAULT 0,
                status TEXT DEFAULT 'running',  -- 'running', 'completed', 'failed'
                error_message TEXT,
                config_snapshot TEXT  -- JSON of config used
            );
            
            -- Failed operations log
            CREATE TABLE IF NOT EXISTS migration_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER,
                doclist_entry_id TEXT,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                original_url TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES migration_runs(id)
            );
        ''')
        self.conn.commit()
    
    def _create_indexes(self):
        """Create indexes for better query performance."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_doclist_entry_id ON file_migrations(doclist_entry_id)",
            "CREATE INDEX IF NOT EXISTS idx_account_id ON file_migrations(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_backup_timestamp ON file_migrations(backup_timestamp)",
            "CREATE INDEX IF NOT EXISTS idx_migration_phase ON file_migrations(migration_phase)",
            "CREATE INDEX IF NOT EXISTS idx_salesforce_updated ON file_migrations(salesforce_updated)",
            "CREATE INDEX IF NOT EXISTS idx_run_type ON migration_runs(run_type)",
            "CREATE INDEX IF NOT EXISTS idx_run_start_time ON migration_runs(start_time)"
        ]
        
        for index_sql in indexes:
            self.conn.execute(index_sql)
        self.conn.commit()
    
    def start_migration_run(self, run_type: str, config: Dict) -> int:
        """Start a new migration run and return run ID."""
        cursor = self.conn.execute('''
            INSERT INTO migration_runs (run_type, start_time, config_snapshot)
            VALUES (?, ?, ?)
        ''', (run_type, datetime.now().isoformat(), json.dumps(config)))
        self.conn.commit()
        return cursor.lastrowid
    
    def end_migration_run(self, run_id: int, status: str = 'completed', error_message: str = None):
        """Complete a migration run with final statistics."""
        self.conn.execute('''
            UPDATE migration_runs 
            SET end_time = ?, status = ?, error_message = ?
            WHERE id = ?
        ''', (datetime.now().isoformat(), status, error_message, run_id))
        self.conn.commit()
    
    def update_run_stats(self, run_id: int, **kwargs):
        """Update migration run statistics."""
        valid_fields = [
            'total_files_processed', 'successful_files', 'failed_files',
            'new_files', 'updated_files', 'skipped_files'
        ]
        
        updates = []
        values = []
        for field, value in kwargs.items():
            if field in valid_fields:
                updates.append(f"{field} = ?")
                values.append(value)
        
        if updates:
            values.append(run_id)
            self.conn.execute(f'''
                UPDATE migration_runs 
                SET {", ".join(updates)}
                WHERE id = ?
            ''', values)
            self.conn.commit()
    
    def record_file_migration(self, file_data: Dict) -> bool:
        """Record or update a file migration entry."""
        try:
            now = datetime.now().isoformat()
            
            # Check if record exists
            existing = self.conn.execute(
                'SELECT id FROM file_migrations WHERE doclist_entry_id = ?',
                (file_data['doclist_entry_id'],)
            ).fetchone()
            
            if existing:
                # Update existing record
                self.conn.execute('''
                    UPDATE file_migrations 
                    SET account_id = ?, account_name = ?, original_url = ?,
                        your_s3_key = ?, your_s3_url = ?, file_name = ?,
                        file_size_bytes = ?, file_hash = ?, backup_timestamp = ?,
                        last_modified_sf = ?, updated_date = ?
                    WHERE doclist_entry_id = ?
                ''', (
                    file_data['account_id'], file_data['account_name'], 
                    file_data['original_url'], file_data['your_s3_key'],
                    file_data['your_s3_url'], file_data['file_name'],
                    file_data.get('file_size_bytes'), file_data.get('file_hash'),
                    file_data['backup_timestamp'], file_data.get('last_modified_sf'),
                    now, file_data['doclist_entry_id']
                ))
                return False  # Updated existing
            else:
                # Insert new record
                self.conn.execute('''
                    INSERT INTO file_migrations (
                        doclist_entry_id, account_id, account_name, original_url,
                        your_s3_key, your_s3_url, file_name, file_size_bytes,
                        file_hash, backup_timestamp, last_modified_sf,
                        created_date, updated_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file_data['doclist_entry_id'], file_data['account_id'],
                    file_data['account_name'], file_data['original_url'],
                    file_data['your_s3_key'], file_data['your_s3_url'],
                    file_data['file_name'], file_data.get('file_size_bytes'),
                    file_data.get('file_hash'), file_data['backup_timestamp'],
                    file_data.get('last_modified_sf'), now, now
                ))
                return True  # New record
        except Exception as e:
            self.logger.error(f"Error recording file migration: {e}")
            raise
        finally:
            self.conn.commit()
    
    def record_migration_error(self, run_id: int, doclist_entry_id: str, 
                              error_type: str, error_message: str, original_url: str = None):
        """Record a migration error."""
        self.conn.execute('''
            INSERT INTO migration_errors (run_id, doclist_entry_id, error_type, error_message, original_url, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (run_id, doclist_entry_id, error_type, error_message, original_url, datetime.now().isoformat()))
        self.conn.commit()
    
    def get_backed_up_files(self) -> List[sqlite3.Row]:
        """Get all backed up files."""
        return self.conn.execute('''
            SELECT * FROM file_migrations 
            ORDER BY backup_timestamp DESC
        ''').fetchall()
    
    def get_files_for_account(self, account_id: str) -> List[sqlite3.Row]:
        """Get all files for a specific account."""
        return self.conn.execute('''
            SELECT * FROM file_migrations 
            WHERE account_id = ?
            ORDER BY backup_timestamp DESC
        ''', (account_id,)).fetchall()
    
    def get_files_needing_salesforce_update(self) -> List[sqlite3.Row]:
        """Get files that need Salesforce URL updates (Phase 2)."""
        return self.conn.execute('''
            SELECT * FROM file_migrations 
            WHERE salesforce_updated = 0
            ORDER BY account_id, backup_timestamp
        ''').fetchall()
    
    def mark_salesforce_updated(self, doclist_entry_ids: List[str]):
        """Mark files as having Salesforce URLs updated."""
        if not doclist_entry_ids:
            return
            
        placeholders = ','.join('?' * len(doclist_entry_ids))
        self.conn.execute(f'''
            UPDATE file_migrations 
            SET salesforce_updated = 1, migration_phase = 2, updated_date = ?
            WHERE doclist_entry_id IN ({placeholders})
        ''', [datetime.now().isoformat()] + doclist_entry_ids)
        self.conn.commit()
    
    def get_migration_stats(self) -> Dict:
        """Get comprehensive migration statistics."""
        stats = {}
        
        # Overall file stats
        cursor = self.conn.execute('''
            SELECT 
                COUNT(*) as total_files,
                SUM(CASE WHEN salesforce_updated = 0 THEN 1 ELSE 0 END) as backup_only,
                SUM(CASE WHEN salesforce_updated = 1 THEN 1 ELSE 0 END) as fully_migrated,
                SUM(file_size_bytes) as total_size_bytes,
                COUNT(DISTINCT account_id) as unique_accounts
            FROM file_migrations
        ''')
        stats['files'] = dict(cursor.fetchone())
        
        # Recent run stats
        cursor = self.conn.execute('''
            SELECT run_type, COUNT(*) as count, MAX(start_time) as last_run
            FROM migration_runs
            GROUP BY run_type
            ORDER BY last_run DESC
        ''')
        stats['runs'] = [dict(row) for row in cursor.fetchall()]
        
        # Error summary
        cursor = self.conn.execute('''
            SELECT error_type, COUNT(*) as count
            FROM migration_errors
            GROUP BY error_type
            ORDER BY count DESC
        ''')
        stats['errors'] = [dict(row) for row in cursor.fetchall()]
        
        return stats
    
    def find_incremental_files(self, last_backup_time: str = None) -> List[str]:
        """Find DocListEntry IDs that need incremental backup."""
        if not last_backup_time:
            # Get timestamp of last successful backup run
            cursor = self.conn.execute('''
                SELECT MAX(start_time) 
                FROM migration_runs 
                WHERE run_type IN ('backup', 'incremental') AND status = 'completed'
            ''')
            result = cursor.fetchone()
            last_backup_time = result[0] if result[0] else '1970-01-01T00:00:00'
        
        # Return all DocListEntry IDs backed up after the specified time
        # This will be compared against current Salesforce data to find new/changed files
        cursor = self.conn.execute('''
            SELECT doclist_entry_id 
            FROM file_migrations 
            WHERE backup_timestamp > ?
        ''', (last_backup_time,))
        
        return [row[0] for row in cursor.fetchall()]
    
    def cleanup_old_runs(self, keep_days: int = 30):
        """Clean up old migration runs and errors."""
        cutoff_date = datetime.now().replace(day=datetime.now().day - keep_days).isoformat()
        
        # Delete old errors first (foreign key constraint)
        self.conn.execute('''
            DELETE FROM migration_errors 
            WHERE run_id IN (
                SELECT id FROM migration_runs WHERE start_time < ?
            )
        ''', (cutoff_date,))
        
        # Delete old runs
        self.conn.execute('DELETE FROM migration_runs WHERE start_time < ?', (cutoff_date,))
        self.conn.commit()
    
    def export_metadata(self, output_file: str = None) -> str:
        """Export migration metadata to JSON for backup/inspection."""
        if not output_file:
            output_file = f"migration_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Export file migrations
        files = self.conn.execute('SELECT * FROM file_migrations ORDER BY backup_timestamp').fetchall()
        runs = self.conn.execute('SELECT * FROM migration_runs ORDER BY start_time').fetchall()
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'total_files': len(files),
            'files': [dict(row) for row in files],
            'runs': [dict(row) for row in runs],
            'stats': self.get_migration_stats()
        }
        
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        self.logger.info(f"Exported metadata to {output_file}")
        return output_file
    
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


def calculate_file_hash(file_content: bytes) -> str:
    """Calculate SHA-256 hash of file content."""
    return hashlib.sha256(file_content).hexdigest()


if __name__ == "__main__":
    # Test the database functionality
    with MigrationDB() as db:
        print("Database initialized successfully")
        stats = db.get_migration_stats()
        print(f"Current stats: {json.dumps(stats, indent=2)}")