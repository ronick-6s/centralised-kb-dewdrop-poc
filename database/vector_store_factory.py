"""
Factory for creating vector store instances based on configuration.
Supports PostgreSQL (pgvector) and Zilliz Cloud (managed Milvus).
"""

import os
from typing import Optional


class VectorStoreFactory:
    """Factory to create the appropriate vector store based on configuration."""
    
    @staticmethod
    def create(provider: Optional[str] = None, user_email: Optional[str] = None):
        """
        Create a vector store instance.
        
        Args:
            provider: 'postgres' or 'zilliz'. If None, uses VECTOR_DB_PROVIDER from .env
            user_email: User's email for multi-user support (creates user-specific collection/table)
            
        Returns:
            VectorStore instance (PostgresVectorStore or VectorStore)
        """
        # Determine which provider to use
        if provider is None:
            provider = os.getenv('VECTOR_DB_PROVIDER', 'postgres').lower()
        
        provider = provider.lower()
        
        if provider == 'postgres':
            from database.postgres_vector_store import PostgresVectorStore
            user_info = f" for {user_email}" if user_email else ""
            print(f"🔵 Using PostgreSQL with pgvector{user_info}")
            return PostgresVectorStore(user_email=user_email)
            
        elif provider == 'zilliz':
            from database.vector_store import VectorStore
            user_info = f" for {user_email}" if user_email else ""
            print(f"🟢 Using Zilliz Cloud (managed Milvus){user_info}")
            return VectorStore(user_email=user_email)
            
        else:
            raise ValueError(
                f"Unknown vector database provider: {provider}. "
                f"Supported providers: 'postgres', 'zilliz'"
            )
    
    @staticmethod
    def get_available_providers():
        """Get list of available providers based on environment configuration."""
        providers = []
        
        # Check if PostgreSQL is configured
        if os.getenv('POSTGRES_HOST') or os.getenv('POSTGRES_DB'):
            providers.append('postgres')
        
        # Check if Zilliz is configured
        if os.getenv('ZILLIZ_CLOUD_URI') and os.getenv('ZILLIZ_CLOUD_TOKEN'):
            providers.append('zilliz')
        
        return providers
    
    @staticmethod
    def switch_provider(new_provider: str):
        """
        Switch the vector database provider.
        
        Args:
            new_provider: 'postgres' or 'zilliz'
            
        Note:
            This updates the environment variable for the current session.
            To persist, update your .env file.
        """
        if new_provider.lower() not in ['postgres', 'zilliz']:
            raise ValueError(f"Invalid provider: {new_provider}")
        
        os.environ['VECTOR_DB_PROVIDER'] = new_provider.lower()
        print(f"✅ Switched to {new_provider}")
        print(f"⚠️  To persist this change, update VECTOR_DB_PROVIDER in your .env file")
