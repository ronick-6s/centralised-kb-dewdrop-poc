"""
Text chunking with token-based splitting and overlap.
"""

import tiktoken
from typing import List


class TextChunker:
    """Chunk text into overlapping segments based on token count."""
    
    def __init__(self, chunk_size: int = 500, overlap: int = 100):
        """
        Initialize the chunker.
        
        Args:
            chunk_size: Maximum tokens per chunk
            overlap: Number of overlapping tokens between chunks
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
    
    def chunk_text(self, text: str, metadata: dict = None) -> List[dict]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Text to chunk
            metadata: Metadata to attach to each chunk
            
        Returns:
            List of chunks with metadata
        """
        if not text.strip():
            return []
        
        tokens = self.encoding.encode(text)
        chunks = []
        
        start = 0
        chunk_id = 0
        
        while start < len(tokens):
            # Get chunk tokens
            end = min(start + self.chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            
            # Decode back to text
            chunk_text = self.encoding.decode(chunk_tokens)
            
            # Create chunk with metadata
            chunk = {
                'chunk_id': chunk_id,
                'text': chunk_text,
                'start_token': start,
                'end_token': end,
                'token_count': len(chunk_tokens)
            }
            
            # Add additional metadata if provided
            if metadata:
                chunk.update(metadata)
            
            chunks.append(chunk)
            
            # Move to next chunk with overlap
            start += self.chunk_size - self.overlap
            chunk_id += 1
        
        return chunks
