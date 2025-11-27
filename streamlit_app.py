"""
Streamlit UI for Enterprise Search Agent
Simple, clean interface for the PoC.
"""

import streamlit as st
import os
import json
from datetime import datetime, timedelta
import time
from dotenv import load_dotenv
from connectors.gdrive.gdrive_connector import GDriveConnector
from pipeline.embeddings import EmbeddingGenerator
from pipeline.orchestrator import Pipeline
from pipeline.rag import RAGPipeline

# Load environment variables
load_dotenv()

# Page config
st.set_page_config(
    page_title="Enterprise Search Agent",
    page_icon="🔍",
    layout="wide"
)

# Load credentials from file if they exist
def load_credentials():
    """Load credentials from the exported file."""
    if os.path.exists('.streamlit_credentials.json'):
        with open('.streamlit_credentials.json', 'r') as f:
            data = json.load(f)
            return data.get('credentials'), data.get('user_email')
    return None, None

# Initialize session state
if 'authenticated' not in st.session_state:
    creds, email = load_credentials()
    if creds:
        st.session_state.authenticated = True
        st.session_state.credentials = creds
        st.session_state.user_email = email
    else:
        st.session_state.authenticated = False
        st.session_state.credentials = None
        st.session_state.user_email = None

if 'indexed' not in st.session_state:
    st.session_state.indexed = False
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []

# Initialize components per user
@st.cache_resource
def init_components(user_email=None):
    """Initialize vector store and embedding generator for a specific user."""
    from database.vector_store_factory import VectorStoreFactory
    
    # Create user-specific vector store (provider from .env, defaults to postgres)
    vector_store = VectorStoreFactory.create(provider=None, user_email=user_email)
    vector_store.initialize_collection()
    
    embedding_generator = EmbeddingGenerator()
    
    return vector_store, embedding_generator

# Get user-specific components
if st.session_state.authenticated and st.session_state.user_email:
    vector_store, embedding_generator = init_components(st.session_state.user_email)
else:
    vector_store, embedding_generator = init_components()

# Header
st.title("🔍 Enterprise Search Agent")
st.markdown("Connect your Google Drive and ask questions about your documents.")

# Sidebar for authentication and sync
with st.sidebar:
    st.header("Configuration")
    
    # Check if Google API key is set
    if not os.getenv("GOOGLE_API_KEY"):
        st.error("⚠️ Google API key not found. Please set it in your .env file.")
        st.info("Get your key from: https://aistudio.google.com/app/apikey")
        st.stop()
    
    # Authentication status
    if st.session_state.authenticated:
        st.success(f"✅ Authenticated as: {st.session_state.user_email}")
        
        # Initialize auto-sync tracking
        if 'auto_synced' not in st.session_state:
            st.session_state.auto_synced = False
        if 'last_auto_sync_time' not in st.session_state:
            st.session_state.last_auto_sync_time = None
        if 'next_auto_sync_time' not in st.session_state:
            st.session_state.next_auto_sync_time = None
        if 'sync_in_progress' not in st.session_state:
            st.session_state.sync_in_progress = False
        
        # Get auto-sync settings
        auto_sync_enabled = os.getenv('AUTO_SYNC', 'true').lower() == 'true'
        auto_sync_interval = int(os.getenv('AUTO_SYNC_INTERVAL_MINUTES', '5'))
        
        # Function to perform sync (runs in main thread but doesn't block UI)
        def perform_auto_sync():
            """Perform automatic incremental sync."""
            try:
                st.session_state.sync_in_progress = True
                
                gdrive_connector = GDriveConnector(
                    client_secrets_file=os.getenv("GDRIVE_CLIENT_SECRETS_FILE", "client_secrets.json")
                )
                gdrive_connector.set_credentials(st.session_state.credentials)
                
                pipeline = Pipeline(
                    vector_store, 
                    embedding_generator,
                    user_email=st.session_state.user_email
                )
                
                # Run sync (output goes to console)
                print("\n" + "="*60)
                print("🔄 Background sync started...")
                print("="*60)
                
                num_chunks = pipeline.process_gdrive_documents(gdrive_connector, incremental=True)
                
                st.session_state.indexed = True
                st.session_state.last_auto_sync_time = datetime.now()
                st.session_state.next_auto_sync_time = datetime.now() + timedelta(minutes=auto_sync_interval)
                st.session_state.sync_in_progress = False
                
                print("="*60)
                print(f"✅ Background sync complete: {num_chunks} chunks")
                print("="*60 + "\n")
                
                return num_chunks
            except Exception as e:
                st.session_state.sync_in_progress = False
                print(f"❌ Auto-sync error: {str(e)}")
                return None
        
        # Auto-sync on startup (only once) - non-blocking
        if not st.session_state.auto_synced and auto_sync_enabled:
            st.info("🔄 Initializing sync... (check console for progress)")
            num_chunks = perform_auto_sync()
            st.session_state.auto_synced = True
            
            if num_chunks is not None:
                if num_chunks > 0:
                    st.success(f"✅ Initial sync complete: {num_chunks} chunks indexed")
                else:
                    st.info("✓ All files up to date")
            st.rerun()  # Refresh to show chat interface
        
        # Show sync status (non-blocking)
        if st.session_state.sync_in_progress:
            st.info("🔄 Sync in progress... (check console for details)")
        
        # Automatic background sync (periodic) - non-blocking
        if auto_sync_enabled and auto_sync_interval > 0 and not st.session_state.sync_in_progress:
            current_time = datetime.now()
            
            # Check if it's time for next sync
            if st.session_state.next_auto_sync_time and current_time >= st.session_state.next_auto_sync_time:
                st.info("🔄 Background sync triggered... (check console)")
                num_chunks = perform_auto_sync()
                
                if num_chunks is not None and num_chunks > 0:
                    st.toast(f"✅ Synced {num_chunks} new chunks", icon="🔄")
                
                st.rerun()  # Refresh UI after sync
            
            # Show next sync countdown
            if st.session_state.next_auto_sync_time:
                time_until_next = st.session_state.next_auto_sync_time - current_time
                minutes_left = int(time_until_next.total_seconds() / 60)
                if minutes_left >= 0:
                    st.caption(f"🔄 Next auto-sync in {minutes_left} minute(s)")
        
        # Manual sync button
        if st.button("🔄 Sync Now", use_container_width=True, type="primary", disabled=st.session_state.sync_in_progress):
            st.info("🔄 Manual sync started... (check console)")
            num_chunks = perform_auto_sync()
            
            if num_chunks is not None:
                if num_chunks > 0:
                    st.success(f"✅ Synced {num_chunks} chunks")
                else:
                    st.info("✓ Everything up to date!")
            
            st.rerun()  # Refresh UI
        
        # Show sync statistics
        if st.session_state.user_email:
            from utils.sync_state import SyncStateManager
            sync_manager = SyncStateManager(st.session_state.user_email)
            stats = sync_manager.get_stats()
            
            if stats['last_sync']:
                from datetime import datetime
                last_sync = datetime.fromisoformat(stats['last_sync'])
                st.caption(f"📊 Last sync: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
                st.caption(f"📁 Files: {stats['total_files']} | 📦 Chunks: {stats['total_chunks']}")
        
        # Show indexing status
        if st.session_state.indexed:
            st.info("📚 Documents indexed and ready for search")
        else:
            st.info("🔄 Sync in progress... Chat will be available after first sync")
    
    else:
        st.warning("🔐 Not authenticated")
        st.markdown("""
        To get started:
        1. Run `app.py` to authenticate via OAuth
        2. Come back here to sync and search
        
        Or use the authentication flow in the web app at:
        http://localhost:8080
        """)

# Main content area - Always show chat if authenticated (even during sync)
if st.session_state.authenticated:
    st.header("💬 Ask Questions")
    
    # Chat interface
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if "sources" in message:
                with st.expander("📄 Sources"):
                    for source in message["sources"]:
                        st.markdown(f"- **{source['name']}** (relevance: {source['score']:.2f})")
    
    # Question input
    if question := st.chat_input("Ask a question about your documents..."):
        # Add user message to chat
        st.session_state.chat_history.append({"role": "user", "content": question})
        
        with st.chat_message("user"):
            st.markdown(question)
        
        # Generate answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    rag = RAGPipeline(vector_store, embedding_generator)
                    result = rag.answer_question(
                        question=question,
                        user_email=st.session_state.user_email
                    )
                    
                    st.markdown(result['answer'])
                    
                    # Show sources
                    if result['sources']:
                        with st.expander("📄 Sources"):
                            for source in result['sources']:
                                st.markdown(f"- **{source['name']}** (relevance: {source['score']:.2f})")
                    
                    # Add to chat history
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": result['answer'],
                        "sources": result['sources']
                    })
                
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    # Clear chat button
    if st.button("🗑️ Clear Chat History"):
        st.session_state.chat_history = []
        st.rerun()

elif st.session_state.authenticated:
    st.info("👆 Click 'Sync Google Drive' in the sidebar to index your documents first.")
else:
    st.info("👈 Please authenticate using the sidebar instructions.")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using Streamlit, Gemini, and Zilliz Cloud.")
