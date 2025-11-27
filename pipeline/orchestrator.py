"""
Main pipeline orchestrator - ties everything together.
"""

import os
from typing import List, Dict, Any, Optional
from connectors.gdrive.gdrive_connector import GDriveConnector
from utils.text_extractor import TextExtractor
from utils.chunker import TextChunker
from utils.sync_state import SyncStateManager
from pipeline.embeddings import EmbeddingGenerator
from database.vector_store import VectorStore


class Pipeline:
    """Orchestrate the complete document processing pipeline."""
    
    def __init__(
        self, 
        vector_store: VectorStore, 
        embedding_generator: EmbeddingGenerator,
        user_email: Optional[str] = None
    ):
        """
        Initialize the pipeline.
        
        Args:
            vector_store: VectorStore instance
            embedding_generator: EmbeddingGenerator instance
            user_email: User's email for sync state tracking
        """
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.text_extractor = TextExtractor()
        self.chunker = TextChunker(chunk_size=500, overlap=100)
        self.user_email = user_email
        self.sync_manager = SyncStateManager(user_email) if user_email else None
    
    def process_gdrive_documents(
        self, 
        gdrive_connector: GDriveConnector,
        incremental: bool = True
    ) -> int:
        """
        Fetch, process, and index documents from Google Drive.
        
        Args:
            gdrive_connector: Authenticated GDrive connector
            incremental: If True, only process new/modified files (default)
            
        Returns:
            Number of chunks indexed
        """
        print("📥 Fetching documents from Google Drive...")
        documents = gdrive_connector.fetch_documents_with_metadata()
        
        if not documents:
            print("⚠️  No documents found.")
            return 0
        
        # Determine which files need processing
        if incremental and self.sync_manager:
            files_to_process, files_stats = self._get_incremental_sync_files(documents)
            
            print(f"\n📊 Incremental Sync Analysis:")
            print(f"   ✨ New files: {files_stats['new']}")
            print(f"   🔄 Modified files: {files_stats['modified']}")
            print(f"   ✓  Unchanged files: {files_stats['unchanged']} (skipped)")
            print(f"   🗑️  Deleted files: {files_stats['deleted']} (will remove)")
            
            # Remove deleted files from vector store
            for file_id in files_stats['deleted_file_ids']:
                try:
                    file_name = self.sync_manager.state['files'][file_id]['name']
                    self.vector_store.delete_by_file_id(file_id)
                    self.sync_manager.remove_file_state(file_id)
                    print(f"   🗑️  Removed deleted file: {file_name}")
                except Exception as e:
                    print(f"   ⚠️  Error removing file {file_id}: {e}")
            
            if not files_to_process:
                print(f"\n✅ No files to sync - everything is up to date!")
                return 0
            
            print(f"\n📄 Processing {len(files_to_process)} file(s)...")
        else:
            files_to_process = documents
            print(f"\n📄 Full sync: Processing all {len(documents)} file(s)...")
        
        total_chunks = 0
        files_processed = 0
        
        for doc in files_to_process:
            try:
                # Extract text from file bytes
                text = self.text_extractor.extract_from_bytes(
                    doc['file_bytes'], 
                    doc['mime_type']
                )
                
                if not text.strip():
                    print(f"   ⊘ Skipping {doc['name']} - no text content")
                    continue
                
                # If this file was modified, delete old chunks first
                if incremental and self.sync_manager and \
                   self.sync_manager.state['files'].get(doc['file_id']):
                    self.vector_store.delete_by_file_id(doc['file_id'])
                
                # Prepare metadata for chunks
                chunk_metadata = {
                    'file_id': doc['file_id'],
                    'name': doc['name'],
                    'mime_type': doc['mime_type'],
                    'source': doc['source'],
                    'created_time': doc['created_time'],
                    'modified_time': doc['modified_time'],
                    'allowed_users': doc['allowed_users']
                }
                
                # Chunk the text
                chunks = self.chunker.chunk_text(text, chunk_metadata)
                
                if not chunks:
                    continue
                
                # Generate embeddings for all chunks
                chunk_texts = [chunk['text'] for chunk in chunks]
                embeddings = self.embedding_generator.generate(chunk_texts)
                
                # Add to vector store
                self.vector_store.add_chunks(chunks, embeddings)
                
                total_chunks += len(chunks)
                files_processed += 1
                
                # Update sync state
                if self.sync_manager:
                    self.sync_manager.update_file_state(
                        doc['file_id'],
                        doc['name'],
                        doc['modified_time'],
                        len(chunks)
                    )
                
                print(f"   ✓ {doc['name']}: {len(chunks)} chunks")
                
            except Exception as e:
                print(f"   ✗ Error processing {doc.get('name', 'unknown')}: {e}")
                continue
        
        # Complete sync
        if self.sync_manager:
            self.sync_manager.complete_sync(files_processed, total_chunks)
        
        print(f"\n{'='*60}")
        print(f"✅ Sync complete!")
        print(f"   Files processed: {files_processed}")
        print(f"   Total chunks indexed: {total_chunks}")
        print(f"{'='*60}\n")
        
        return total_chunks
    
    def _get_incremental_sync_files(self, all_documents: List[Dict]) -> tuple:
        """
        Determine which files need to be processed for incremental sync.
        
        Args:
            all_documents: All documents from Google Drive
            
        Returns:
            Tuple of (files_to_process, stats_dict)
        """
        new_files, modified_files, unchanged_files, deleted_file_ids = \
            self.sync_manager.get_files_to_sync(all_documents)
        
        # Combine new and modified files
        files_to_process = new_files + modified_files
        
        stats = {
            'new': len(new_files),
            'modified': len(modified_files),
            'unchanged': len(unchanged_files),
            'deleted': len(deleted_file_ids),
            'deleted_file_ids': deleted_file_ids
        }
        
        return files_to_process, stats
