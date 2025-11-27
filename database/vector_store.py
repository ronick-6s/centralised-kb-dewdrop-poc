"""
Vector database using Zilliz Cloud (managed Milvus) for storing and retrieving document chunks.
"""

import os
from typing import List, Dict, Any, Optional
from pymilvus import (
    connections,
    utility,
    FieldSchema,
    CollectionSchema,
    DataType,
    Collection,
)


class VectorStore:
    """Manage vector storage and retrieval with Zilliz Cloud."""
    
    def __init__(
        self, 
        collection_name: str = "documents",
        uri: str = None,
        token: str = None,
        user_email: str = None
    ):
        """
        Initialize the vector store with Zilliz Cloud.
        
        Args:
            collection_name: Base name of the collection
            uri: Zilliz Cloud URI (from env if not provided)
            token: Zilliz Cloud API token (from env if not provided)
            user_email: User's email for multi-user support (creates user-specific collection)
        """
        self.base_collection_name = collection_name
        self.user_email = user_email
        
        # Create user-specific collection name if email provided
        if user_email:
            safe_email = self._sanitize_collection_name(user_email)
            self.collection_name = f"{collection_name}_{safe_email}"
        else:
            self.collection_name = collection_name
        
        self.uri = uri or os.getenv("ZILLIZ_CLOUD_URI")
        self.token = token or os.getenv("ZILLIZ_CLOUD_TOKEN")
        self.vector_size = 768  # Google text-embedding-004 dimension
        self.collection = None
        
        if not self.uri or not self.token:
            raise ValueError(
                "Zilliz Cloud URI and Token are required. "
                "Set ZILLIZ_CLOUD_URI and ZILLIZ_CLOUD_TOKEN in your .env file"
            )
        
        # Connect to Zilliz Cloud
        self._connect()
    
    def _sanitize_collection_name(self, email: str) -> str:
        """
        Sanitize email address to create a valid Milvus collection name.
        
        Args:
            email: User's email address
            
        Returns:
            Sanitized string safe for collection name
        """
        # Milvus collection names: must start with letter, only alphanumeric and underscore
        safe_name = email.lower()
        safe_name = safe_name.replace('@', '_at_')
        safe_name = safe_name.replace('.', '_')
        safe_name = safe_name.replace('-', '_')
        safe_name = safe_name.replace('+', '_')
        
        # Remove any remaining invalid characters
        safe_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in safe_name)
        
        # Ensure it starts with a letter
        if safe_name[0].isdigit():
            safe_name = 'user_' + safe_name
        
        # Limit length (Milvus limit is 255)
        if len(safe_name) > 200:
            safe_name = safe_name[:200]
        
        return safe_name
        
    def _connect(self):
        """Establish connection to Zilliz Cloud."""
        try:
            connections.connect(
                alias="default",
                uri=self.uri,
                token=self.token
            )
            print("✅ Connected to Zilliz Cloud")
        except Exception as e:
            print(f"❌ Failed to connect to Zilliz Cloud: {e}")
            raise
    
    def initialize_collection(self):
        """Create the collection if it doesn't exist."""
        # Check if collection exists
        if utility.has_collection(self.collection_name):
            self.collection = Collection(self.collection_name)
            print(f"✅ Collection '{self.collection_name}' already exists")
            return
        
        # Define schema
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.vector_size),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=500),
            FieldSchema(name="chunk_id", dtype=DataType.INT64),
            FieldSchema(name="name", dtype=DataType.VARCHAR, max_length=1000),
            FieldSchema(name="mime_type", dtype=DataType.VARCHAR, max_length=200),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="allowed_users", dtype=DataType.VARCHAR, max_length=65535),  # JSON string
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="Document chunks with embeddings"
        )
        
        # Create collection
        self.collection = Collection(
            name=self.collection_name,
            schema=schema
        )
        
        # Create index for vector field
        index_params = {
            "metric_type": "COSINE",
            "index_type": "AUTOINDEX",
            "params": {}
        }
        
        self.collection.create_index(
            field_name="embedding",
            index_params=index_params
        )
        
        print(f"✅ Created collection: {self.collection_name}")
    
    def add_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Add chunks with their embeddings to the vector store.
        
        Args:
            chunks: List of chunk dictionaries with metadata
            embeddings: List of embedding vectors
        """
        if not chunks or not embeddings:
            return
        
        # Prepare data for insertion
        data = {
            "embedding": embeddings,
            "text": [],
            "file_id": [],
            "chunk_id": [],
            "name": [],
            "mime_type": [],
            "source": [],
            "allowed_users": [],
        }
        
        for chunk in chunks:
            data["text"].append(chunk.get("text", ""))
            data["file_id"].append(chunk.get("file_id", ""))
            data["chunk_id"].append(chunk.get("chunk_id", 0))
            data["name"].append(chunk.get("name", ""))
            data["mime_type"].append(chunk.get("mime_type", ""))
            data["source"].append(chunk.get("source", ""))
            
            # Convert allowed_users list to JSON string
            import json
            allowed_users = chunk.get("allowed_users", [])
            data["allowed_users"].append(json.dumps(allowed_users))
        
        # Insert data
        self.collection.insert(list(data.values()))
        
        # Flush to ensure data is persisted
        self.collection.flush()
        
        print(f"✅ Added {len(chunks)} chunks to vector store")
    
    def search(
        self, 
        query_vector: List[float], 
        limit: int = 5, 
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar chunks.
        
        Args:
            query_vector: Query embedding vector
            limit: Maximum number of results
            user_email: Filter by user permissions (if provided)
            
        Returns:
            List of matching chunks with scores
        """
        # Load collection into memory for search
        self.collection.load()
        
        # Build filter expression for permissions
        # For now, we'll skip permission filtering in the vector search
        # and filter results in Python after retrieval
        # This is simpler and more reliable for the PoC
        filter_expr = None
        
        # Search parameters
        search_params = {
            "metric_type": "COSINE",
            "params": {}
        }
        
        # Perform search without filter first
        results = self.collection.search(
            data=[query_vector],
            anns_field="embedding",
            param=search_params,
            limit=limit * 3 if user_email else limit,  # Get more results if filtering
            expr=filter_expr,
            output_fields=["text", "file_id", "chunk_id", "name", "mime_type", "source", "allowed_users"]
        )
        
        # Format and filter results
        formatted_results = []
        for hits in results:
            for hit in hits:
                import json
                allowed_users = json.loads(hit.entity.get("allowed_users", "[]"))
                
                # Apply permission filter in Python if user_email is provided
                if user_email and user_email not in allowed_users:
                    continue
                
                formatted_results.append({
                    "score": hit.score,
                    "chunk": {
                        "text": hit.entity.get("text"),
                        "file_id": hit.entity.get("file_id"),
                        "chunk_id": hit.entity.get("chunk_id"),
                        "name": hit.entity.get("name"),
                        "mime_type": hit.entity.get("mime_type"),
                        "source": hit.entity.get("source"),
                        "allowed_users": allowed_users,
                    }
                })
                
                # Stop when we have enough results
                if len(formatted_results) >= limit:
                    break
            
            if len(formatted_results) >= limit:
                break
        
        return formatted_results[:limit]
    
    def delete_by_file_id(self, file_id: str):
        """
        Delete all chunks for a specific file.
        
        Args:
            file_id: ID of the file to remove
        """
        expr = f'file_id == "{file_id}"'
        self.collection.delete(expr)
        self.collection.flush()
        print(f"✅ Deleted chunks for file: {file_id}")
    
    def close(self):
        """Close the connection to Zilliz Cloud."""
        connections.disconnect("default")
        print("✅ Disconnected from Zilliz Cloud")

