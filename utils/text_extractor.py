"""
In-memory text extraction from various file formats.
No temporary files are created.
"""

import io
from typing import Optional
from pypdf import PdfReader
from docx import Document as DocxDocument


class TextExtractor:
    """Extract text from files in-memory without saving to disk."""
    
    @staticmethod
    def extract_from_bytes(file_bytes: bytes, mime_type: str) -> str:
        """
        Extract text from file bytes based on mime type.
        
        Args:
            file_bytes: Raw file content as bytes
            mime_type: MIME type of the file
            
        Returns:
            Extracted text content (NUL characters removed)
        """
        try:
            text = ""
            
            if mime_type == 'application/pdf':
                text = TextExtractor._extract_pdf(file_bytes)
            elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
                              'application/msword']:
                text = TextExtractor._extract_docx(file_bytes)
            elif mime_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                              'application/vnd.ms-excel',
                              'text/csv']:
                # For Excel/CSV files, decode as text (may have NUL bytes)
                text = file_bytes.decode('utf-8', errors='ignore')
            elif mime_type.startswith('text/'):
                text = file_bytes.decode('utf-8', errors='ignore')
            else:
                # For unsupported types, try to decode as text
                text = file_bytes.decode('utf-8', errors='ignore')
            
            # Remove NUL characters (0x00) that cause PostgreSQL errors
            text = text.replace('\x00', '')
            
            return text
            
        except Exception as e:
            print(f"Error extracting text from {mime_type}: {e}")
            return ""
    
    @staticmethod
    def _extract_pdf(file_bytes: bytes) -> str:
        """Extract text from PDF bytes."""
        pdf_file = io.BytesIO(file_bytes)
        reader = PdfReader(pdf_file)
        
        text = []
        for page in reader.pages:
            text.append(page.extract_text())
        
        return '\n'.join(text)
    
    @staticmethod
    def _extract_docx(file_bytes: bytes) -> str:
        """Extract text from DOCX bytes."""
        docx_file = io.BytesIO(file_bytes)
        doc = DocxDocument(docx_file)
        
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        
        return '\n'.join(text)
