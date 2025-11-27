"""
Sync state tracker for incremental syncs.
Tracks last sync time and file metadata per user.
"""

import os
import json
from datetime import datetime
from typing import Dict, Optional, Set
from pathlib import Path


class SyncStateManager:
    """Manage sync state for incremental updates."""
    
    def __init__(self, user_email: str):
        """
        Initialize sync state manager for a specific user.
        
        Args:
            user_email: User's email address (used as unique identifier)
        """
        self.user_email = user_email
        self.state_dir = Path(".sync_state")
        self.state_dir.mkdir(exist_ok=True)
        
        # Sanitize email for filename
        safe_email = user_email.replace("@", "_at_").replace(".", "_")
        self.state_file = self.state_dir / f"{safe_email}.json"
        
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Load sync state from file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️  Error loading sync state: {e}")
                return self._create_empty_state()
        return self._create_empty_state()
    
    def _create_empty_state(self) -> Dict:
        """Create empty sync state."""
        return {
            'user_email': self.user_email,
            'last_sync': None,
            'files': {},  # file_id -> {name, modified_time, chunk_count}
            'total_syncs': 0,
            'total_files_processed': 0,
            'total_chunks_created': 0
        }
    
    def _save_state(self):
        """Save sync state to file."""
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"⚠️  Error saving sync state: {e}")
    
    def get_last_sync_time(self) -> Optional[str]:
        """Get the last sync timestamp in ISO format."""
        return self.state.get('last_sync')
    
    def is_file_synced(self, file_id: str, modified_time: str) -> bool:
        """
        Check if a file needs to be synced.
        
        Args:
            file_id: Google Drive file ID
            modified_time: File's modified time from Drive API
            
        Returns:
            True if file is already synced and unchanged, False otherwise
        """
        if file_id not in self.state['files']:
            return False
        
        stored_modified_time = self.state['files'][file_id].get('modified_time')
        return stored_modified_time == modified_time
    
    def get_files_to_sync(self, drive_files: list) -> tuple:
        """
        Determine which files need to be synced.
        
        Args:
            drive_files: List of files from Google Drive API
            
        Returns:
            Tuple of (new_files, modified_files, unchanged_files, deleted_file_ids)
        """
        new_files = []
        modified_files = []
        unchanged_files = []
        
        current_file_ids = set()
        
        for file_item in drive_files:
            file_id = file_item['file_id']  # Changed from 'id' to 'file_id'
            modified_time = file_item.get('modified_time')  # Changed from 'modifiedTime' to 'modified_time'
            current_file_ids.add(file_id)
            
            if file_id not in self.state['files']:
                # New file
                new_files.append(file_item)
            elif not self.is_file_synced(file_id, modified_time):
                # Modified file
                modified_files.append(file_item)
            else:
                # Unchanged file
                unchanged_files.append(file_item)
        
        # Find deleted files (in DB but not in Drive)
        stored_file_ids = set(self.state['files'].keys())
        deleted_file_ids = stored_file_ids - current_file_ids
        
        return new_files, modified_files, unchanged_files, list(deleted_file_ids)
    
    def update_file_state(self, file_id: str, name: str, modified_time: str, chunk_count: int):
        """
        Update the state for a synced file.
        
        Args:
            file_id: Google Drive file ID
            name: File name
            modified_time: File's modified time
            chunk_count: Number of chunks created for this file
        """
        self.state['files'][file_id] = {
            'name': name,
            'modified_time': modified_time,
            'chunk_count': chunk_count,
            'last_synced': datetime.utcnow().isoformat()
        }
    
    def remove_file_state(self, file_id: str):
        """Remove a file from sync state (when deleted from Drive)."""
        if file_id in self.state['files']:
            del self.state['files'][file_id]
    
    def complete_sync(self, files_processed: int, chunks_created: int):
        """
        Mark sync as complete and update statistics.
        
        Args:
            files_processed: Number of files processed in this sync
            chunks_created: Number of chunks created in this sync
        """
        self.state['last_sync'] = datetime.utcnow().isoformat()
        self.state['total_syncs'] += 1
        self.state['total_files_processed'] += files_processed
        self.state['total_chunks_created'] += chunks_created
        
        self._save_state()
    
    def get_stats(self) -> Dict:
        """Get sync statistics."""
        return {
            'last_sync': self.state.get('last_sync'),
            'total_syncs': self.state.get('total_syncs', 0),
            'total_files': len(self.state.get('files', {})),
            'total_files_processed': self.state.get('total_files_processed', 0),
            'total_chunks': self.state.get('total_chunks_created', 0)
        }
    
    def reset(self):
        """Reset sync state (useful for fresh start)."""
        self.state = self._create_empty_state()
        self._save_state()
        print(f"✅ Sync state reset for {self.user_email}")
