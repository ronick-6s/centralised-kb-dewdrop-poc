"""
RAG (Retrieval Augmented Generation) Pipeline
Combines vector search with LLM to answer questions.
"""

from typing import List, Dict, Any
import google.generativeai as genai
import os


class RAGPipeline:
    """Answer questions using retrieved context from vector store."""
    
    def __init__(self, vector_store, embedding_generator, model: str = "gemini-flash-latest"):
        """
        Initialize the RAG pipeline.
        
        Args:
            vector_store: VectorStore instance
            embedding_generator: EmbeddingGenerator instance
            model: Google Gemini model to use for generation
        """
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.model_name = model
        
        # Configure Gemini
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY not found in environment variables")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name=model)
    
    def answer_question(
        self, 
        question: str, 
        user_email: str = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """
        Answer a question using RAG.
        
        Args:
            question: User's question
            user_email: User's email for permission filtering
            top_k: Number of chunks to retrieve
            
        Returns:
            Dictionary with answer, sources, and reasoning
        """
        # Generate embedding for the question
        question_vector = self.embedding_generator.generate_single(question)
        
        # Search vector store
        results = self.vector_store.search(
            query_vector=question_vector,
            limit=top_k,
            user_email=user_email
        )
        
        if not results:
            return {
                'answer': "I couldn't find any relevant information in your documents.",
                'sources': [],
                'reasoning': "No matching documents found."
            }
        
        # Build context from retrieved chunks
        context_parts = []
        sources = []
        
        for idx, result in enumerate(results):
            chunk = result['chunk']
            score = result['score']
            
            context_parts.append(
                f"[Document {idx + 1}: {chunk.get('name', 'Unknown')}]\n{chunk.get('text', '')}"
            )
            
            sources.append({
                'name': chunk.get('name', 'Unknown'),
                'file_id': chunk.get('file_id', ''),
                'score': score,
                'chunk_id': chunk.get('chunk_id', 0)
            })
        
        context = "\n\n".join(context_parts)
        
        # Build prompt
        system_instruction = """You are an AI assistant that answers questions based on the provided document context.

Instructions:
- Answer the question using ONLY the information from the provided documents
- Include specific references to document names when citing information
- If the documents don't contain enough information, say so clearly
- Provide a brief reasoning for your answer
- Be concise but complete"""

        user_prompt = f"""Context from documents:

{context}

Question: {question}

Please provide:
1. A direct answer to the question
2. Citations to the specific documents used
3. A brief explanation of your reasoning"""

        # Generate answer using Gemini
        response = self.model.generate_content(
            f"{system_instruction}\n\n{user_prompt}"
        )
        
        answer = response.text
        
        return {
            'answer': answer,
            'sources': sources,
            'context': context,
            'question': question
        }
