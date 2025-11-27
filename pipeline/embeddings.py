"""
Generate embeddings using Google's Gemini API.
"""

import os
from typing import List
import google.generativeai as genai


class EmbeddingGenerator:
    """Generate embeddings for text chunks using Google Gemini."""
    
    def __init__(self, api_key: str = None, model: str = "models/text-embedding-004"):
        """
        Initialize the embedding generator.
        
        Args:
            api_key: Google API key (defaults to env var)
            model: Embedding model to use (text-embedding-004 is the latest)
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        self.model = model
        
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        
        genai.configure(api_key=self.api_key)
    
    def generate(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        embeddings = []
        for text in texts:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_document"
            )
            embeddings.append(result['embedding'])
        
        return embeddings
    
    def generate_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        result = genai.embed_content(
            model=self.model,
            content=text,
            task_type="retrieval_query"
        )
        return result['embedding']
