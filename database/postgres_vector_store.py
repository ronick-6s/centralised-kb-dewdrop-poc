"""
Vector database using PostgreSQL with pgvector extension.
Alternative to Zilliz Cloud with local control.
"""

import os
import json
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.extensions import register_adapter, AsIs
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# Register numpy array adapter for PostgreSQL
def adapt_numpy_array(numpy_array):
    return AsIs(str(numpy_array.tolist()))

register_adapter(np.ndarray, adapt_numpy_array)


class PostgresVectorStore:
    """Manage vector storage and retrieval with PostgreSQL + pgvector."""
    
    def __init__(
        self, 
        collection_name: str = "documents",
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
        user_email: str = None
    ):
        """
        Initialize the vector store with PostgreSQL.
        
        Args:
            collection_name: Base name of the table (default: documents)
            host: PostgreSQL host (from env if not provided)
            port: PostgreSQL port (from env if not provided)
            database: Database name (from env if not provided)
            user: Database user (from env if not provided)
            password: Database password (from env if not provided)
            user_email: User's email for multi-user support (creates user-specific table)
        """
        self.base_collection_name = collection_name
        self.user_email = user_email
        
        # Create user-specific table name if email provided
        if user_email:
            safe_email = self._sanitize_table_name(user_email)
            self.collection_name = f"{collection_name}_{safe_email}"
        else:
            self.collection_name = collection_name
        
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5432"))
        self.database = database or os.getenv("POSTGRES_DB", "enterprise_search")
        self.user = user or os.getenv("POSTGRES_USER", "postgres")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "")
        self.vector_size = 768  # Google text-embedding-004 dimension
        self.conn = None
        
        # Connect to PostgreSQL
        self._connect()
    
    def _sanitize_table_name(self, email: str) -> str:
        """
        Sanitize email address to create a valid PostgreSQL table name.
        
        Args:
            email: User's email address
            
        Returns:
            Sanitized string safe for table name
        """
        # Replace special characters with underscores
        safe_name = email.lower()
        safe_name = safe_name.replace('@', '_at_')
        safe_name = safe_name.replace('.', '_')
        safe_name = safe_name.replace('-', '_')
        safe_name = safe_name.replace('+', '_')
        
        # Ensure it starts with a letter (PostgreSQL requirement)
        if safe_name[0].isdigit():
            safe_name = 'user_' + safe_name
        
        # Limit length to 63 characters (PostgreSQL limit)
        if len(safe_name) > 63:
            safe_name = safe_name[:63]
        
        return safe_name
        
    def _connect(self):
        """Establish connection to PostgreSQL."""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            self.conn.autocommit = False
            print(f"✅ Connected to PostgreSQL at {self.host}:{self.port}/{self.database}")
        except Exception as e:
            print(f"❌ Failed to connect to PostgreSQL: {e}")
            raise
    
    def initialize_collection(self):
        """Create the table and enable pgvector extension if they don't exist."""
        cursor = self.conn.cursor()
        
        try:
            # Enable pgvector extension
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("✅ pgvector extension enabled")
            
            # Create table with vector column
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.collection_name} (
                    id BIGSERIAL PRIMARY KEY,
                    embedding vector({self.vector_size}),
                    text TEXT,
                    file_id VARCHAR(500),
                    chunk_id BIGINT,
                    name VARCHAR(1000),
                    mime_type VARCHAR(200),
                    source VARCHAR(100),
                    allowed_users JSONB
                );
            """)
            
            # Create index for vector similarity search (HNSW - fast approximate search)
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.collection_name}_embedding_idx 
                ON {self.collection_name} 
                USING hnsw (embedding vector_cosine_ops);
            """)
            
            # Create index for file_id for faster deletes
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS {self.collection_name}_file_id_idx 
                ON {self.collection_name} (file_id);
            """)
            
            self.conn.commit()
            print(f"✅ Table '{self.collection_name}' initialized with pgvector")
            
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error initializing collection: {e}")
            raise
        finally:
            cursor.close()
    
    def add_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Add chunks with their embeddings to the vector store.
        
        Args:
            chunks: List of chunk dictionaries with metadata
            embeddings: List of embedding vectors
        """
        if not chunks or not embeddings:
            return
        
        cursor = self.conn.cursor()
        
        try:
            # Prepare data for insertion
            values = []
            for chunk, embedding in zip(chunks, embeddings):
                values.append((
                    embedding,  # pgvector handles list → vector conversion
                    chunk.get("text", ""),
                    chunk.get("file_id", ""),
                    chunk.get("chunk_id", 0),
                    chunk.get("name", ""),
                    chunk.get("mime_type", ""),
                    chunk.get("source", ""),
                    json.dumps(chunk.get("allowed_users", []))  # Store as JSON
                ))
            
            # Bulk insert
            execute_values(
                cursor,
                f"""
                INSERT INTO {self.collection_name} 
                (embedding, text, file_id, chunk_id, name, mime_type, source, allowed_users)
                VALUES %s
                """,
                values
            )
            
            self.conn.commit()
            print(f"✅ Added {len(chunks)} chunks to PostgreSQL")
            
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error adding chunks: {e}")
            raise
        finally:
            cursor.close()
    
    def search(
        self, 
        query_vector: List[float], 
        limit: int = 5, 
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks using cosine similarity.
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            user_email: Filter by user permissions (if provided)
            
        Returns:
            List of matching chunks with scores
        """
        cursor = self.conn.cursor()
        
        try:
            # Get more results if we need to filter by permissions
            search_limit = limit * 3 if user_email else limit
            
            # Convert query vector to string format for PostgreSQL
            vector_str = str(query_vector)
            
            # Search using cosine similarity
            # Note: <=> operator computes cosine distance (lower is better)
            # We convert to similarity: 1 - distance
            cursor.execute(f"""
                SELECT 
                    id,
                    text,
                    file_id,
                    chunk_id,
                    name,
                    mime_type,
                    source,
                    allowed_users,
                    1 - (embedding <=> %s::vector) AS similarity
                FROM {self.collection_name}
                ORDER BY embedding <=> %s::vector
                LIMIT %s;
            """, (vector_str, vector_str, search_limit))
            
            results = cursor.fetchall()
            
            # Format and filter results
            formatted_results = []
            for row in results:
                (id, text, file_id, chunk_id, name, mime_type, 
                 source, allowed_users_json, similarity) = row
                
                # Parse allowed_users from JSON
                allowed_users = allowed_users_json if isinstance(allowed_users_json, list) else []
                
                # Apply permission filter if user_email is provided
                if user_email and user_email not in allowed_users:
                    continue
                
                formatted_results.append({
                    "score": float(similarity),
                    "chunk": {
                        "text": text,
                        "file_id": file_id,
                        "chunk_id": chunk_id,
                        "name": name,
                        "mime_type": mime_type,
                        "source": source,
                        "allowed_users": allowed_users,
                    }
                })
                
                # Stop when we have enough results
                if len(formatted_results) >= limit:
                    break
            
            return formatted_results[:limit]
            
        except Exception as e:
            print(f"❌ Error searching: {e}")
            raise
        finally:
            cursor.close()
    
    def delete_by_file_id(self, file_id: str):
        """
        Delete all chunks for a specific file.
        
        Args:
            file_id: ID of the file to remove
        """
        cursor = self.conn.cursor()
        
        try:
            cursor.execute(
                f"DELETE FROM {self.collection_name} WHERE file_id = %s;",
                (file_id,)
            )
            deleted_count = cursor.rowcount
            self.conn.commit()
            print(f"✅ Deleted {deleted_count} chunks for file: {file_id}")
            
        except Exception as e:
            self.conn.rollback()
            print(f"❌ Error deleting chunks: {e}")
            raise
        finally:
            cursor.close()
    
    def close(self):
        """Close the connection to PostgreSQL."""
        if self.conn:
            self.conn.close()
            print("✅ Disconnected from PostgreSQL")
