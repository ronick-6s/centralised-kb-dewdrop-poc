import os
import io
from typing import List, Optional, Dict, Any
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from core.base_connector import BaseConnector
from core.document import Document

SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/userinfo.email'
]
REDIRECT_URI = 'http://localhost:8080/oauth2callback'

class GDriveConnector(BaseConnector):
    def __init__(self, client_secrets_file: str, state: Optional[str] = None):
        self.client_secrets_file = client_secrets_file
        self.flow = Flow.from_client_secrets_file(
            client_secrets_file,
            scopes=SCOPES,
            state=state
        )
        self.flow.redirect_uri = REDIRECT_URI
        self.creds: Optional[Credentials] = None

    def get_auth_url(self):
        authorization_url, state = self.flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'  # Force consent screen to get refresh token
        )
        self.state = state
        return authorization_url

    def get_state(self):
        return self.state

    def get_credentials(self, authorization_response: str) -> Credentials:
        """Get credentials from the OAuth callback."""
        try:
            # Suppress the scope warning - Google adds 'openid' automatically
            import warnings
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*Scope has changed.*")
                self.flow.fetch_token(authorization_response=authorization_response)
            
            self.creds = self.flow.credentials
            return self.creds
        except Exception as e:
            print(f"Error getting credentials: {e}")
            raise

    def set_credentials(self, creds_dict: dict):
        """Set credentials from a dictionary."""
        # Ensure all required fields are present
        required_fields = ['token', 'refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [f for f in required_fields if f not in creds_dict or creds_dict[f] is None]
        
        if missing_fields:
            raise ValueError(f"Missing required credential fields: {missing_fields}")
        
        # Create Credentials object with explicit parameters
        self.creds = Credentials(
            token=creds_dict['token'],
            refresh_token=creds_dict['refresh_token'],
            token_uri=creds_dict['token_uri'],
            client_id=creds_dict['client_id'],
            client_secret=creds_dict['client_secret'],
            scopes=creds_dict.get('scopes', SCOPES)
        )

    def connect(self) -> None:
        # The connect logic is now handled by the web flow
        if not self.creds:
            raise Exception("Not connected. Please go through the web authentication flow.")
        print("Connected to Google Drive.")
    
    def get_user_email(self) -> str:
        """Get the authenticated user's email address."""
        if not self.creds:
            raise Exception("Not connected. Please authenticate first.")
        
        # Use OAuth2 API to get user info
        from googleapiclient.discovery import build
        oauth2_service = build('oauth2', 'v2', credentials=self.creds)
        user_info = oauth2_service.userinfo().get().execute()
        return user_info.get('email', '')

    def fetch_documents_with_metadata(self) -> List[Dict[str, Any]]:
        """
        Fetch ALL files from Google Drive with full metadata and content.
        Returns raw bytes and metadata without saving to disk.
        Uses pagination to fetch all files regardless of count.
        """
        if not self.creds:
            raise Exception("Not connected. Please go through the web authentication flow.")

        service = build('drive', 'v3', credentials=self.creds)
        
        # Fetch all files using pagination
        all_items = []
        page_token = None
        page_count = 0
        
        print("📥 Fetching files from Google Drive...")
        
        while True:
            results = service.files().list(
                pageSize=100,
                pageToken=page_token,
                fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, owners, permissions)"
            ).execute()
            
            items = results.get('files', [])
            all_items.extend(items)
            page_count += 1
            
            print(f"   Page {page_count}: Found {len(items)} files (Total so far: {len(all_items)})")
            
            page_token = results.get('nextPageToken')
            if not page_token:
                break  # No more pages
        
        print(f"✅ Found {len(all_items)} total files across {page_count} page(s)")
        
        if not all_items:
            print("⚠️  No files found in your Drive.")
            return []

        documents = []
        print(f"\n📄 Processing {len(all_items)} files...")
        
        processed = 0
        skipped = 0
        errors = 0
        
        for idx, item in enumerate(all_items, 1):
            # Get file content as bytes
            file_bytes = b""
            mime_type = item.get('mimeType', '')
            file_name = item.get('name', 'Unknown')
            
            # Progress indicator
            if idx % 10 == 0 or idx == len(all_items):
                print(f"   Progress: {idx}/{len(all_items)} files ({processed} processed, {skipped} skipped, {errors} errors)")
            
            try:
                # Handle Google Docs export
                if mime_type == 'application/vnd.google-apps.document':
                    request = service.files().export_media(fileId=item['id'], mimeType='text/plain')
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    file_bytes = fh.getvalue()
                    mime_type = 'text/plain'  # Override for processing
                
                # Handle Google Sheets (export as CSV)
                elif mime_type == 'application/vnd.google-apps.spreadsheet':
                    request = service.files().export_media(fileId=item['id'], mimeType='text/csv')
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    file_bytes = fh.getvalue()
                    mime_type = 'text/csv'
                
                # Handle Google Slides (export as text)
                elif mime_type == 'application/vnd.google-apps.presentation':
                    request = service.files().export_media(fileId=item['id'], mimeType='text/plain')
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    file_bytes = fh.getvalue()
                    mime_type = 'text/plain'
                
                # Handle regular files (PDF, DOCX, TXT, etc.)
                elif mime_type.startswith('text/') or \
                     mime_type == 'application/json' or \
                     mime_type == 'application/pdf' or \
                     mime_type == 'text/csv' or \
                     mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                                   'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                    request = service.files().get_media(fileId=item['id'])
                    fh = io.BytesIO()
                    downloader = MediaIoBaseDownload(fh, request)
                    done = False
                    while not done:
                        status, done = downloader.next_chunk()
                    file_bytes = fh.getvalue()
                
                else:
                    # Skip unsupported file types
                    skipped += 1
                    continue
                
                # Skip empty files
                if not file_bytes:
                    skipped += 1
                    continue
                
                # Extract allowed users from permissions
                allowed_users = []
                if 'permissions' in item:
                    for perm in item['permissions']:
                        if perm.get('emailAddress'):
                            allowed_users.append(perm['emailAddress'])
                
                # Add owner email
                if item.get('owners'):
                    for owner in item['owners']:
                        if owner.get('emailAddress') and owner['emailAddress'] not in allowed_users:
                            allowed_users.append(owner['emailAddress'])
                
                documents.append({
                    'file_id': item['id'],
                    'name': file_name,
                    'mime_type': mime_type,
                    'created_time': item.get('createdTime'),
                    'modified_time': item.get('modifiedTime'),
                    'allowed_users': allowed_users,
                    'source': 'gdrive',
                    'file_bytes': file_bytes
                })
                
                processed += 1
            
            except Exception as e:
                print(f"   ⚠️  Error fetching '{file_name}': {str(e)[:80]}")
                errors += 1
                continue
        
        print(f"\n✅ Processing complete:")
        print(f"   ✓ Processed: {processed} files")
        print(f"   ⊘ Skipped: {skipped} files (unsupported types or empty)")
        print(f"   ✗ Errors: {errors} files")
        
        return documents
    
    def fetch_documents(self) -> List[Document]:
        """Legacy method for backwards compatibility."""
        docs_with_metadata = self.fetch_documents_with_metadata()
        
        documents = []
        for doc_meta in docs_with_metadata:
            # Try to decode as text
            try:
                content = doc_meta['file_bytes'].decode('utf-8', errors='ignore')
            except:
                content = ""
            
            documents.append(Document(
                content=content,
                metadata={
                    'source': doc_meta['source'],
                    'id': doc_meta['file_id'],
                    'name': doc_meta['name'],
                    'mimeType': doc_meta['mime_type'],
                    'createdTime': doc_meta['created_time'],
                    'modifiedTime': doc_meta['modified_time'],
                }
            ))
        
        return documents

        
        results = service.files().list(
            pageSize=100, # Adjust as needed
            fields="nextPageToken, files(id, name, mimeType, createdTime, modifiedTime, owners)"
        ).execute()
        
        items = results.get('files', [])
        if not items:
            print("No files found.")
            return []

        documents: List[Document] = []
        for item in items:
            content = ""
            if item.get('mimeType') == 'application/vnd.google-apps.document':
                request = service.files().export_media(fileId=item['id'], mimeType='text/plain')
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                content = fh.getvalue().decode('utf-8')
            elif item.get('mimeType', '').startswith('text/') or item.get('mimeType') == 'application/json':
                request = service.files().get_media(fileId=item['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                content = fh.getvalue().decode('utf-8')

            documents.append(Document(
                content=content,
                metadata={
                    'source': 'gdrive',
                    'id': item['id'],
                    'name': item['name'],
                    'mimeType': item.get('mimeType'),
                    'createdTime': item.get('createdTime'),
                    'modifiedTime': item.get('modifiedTime'),
                    'owners': item.get('owners'),
                }
            ))
        return documents
