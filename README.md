# Enterprise Search Agent

**Fully Automatic Multi-User RAG System for Google Drive**

Search and chat with your Google Drive documents using AI. Supports multi-user isolation with automatic incremental syncing.

---

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. Setup PostgreSQL

```bash
# Install PostgreSQL (macOS)
brew install postgresql@18 pgvector

# Start PostgreSQL
brew services start postgresql@18

# Create database
createdb enterprise_search
```

### 3. Configure Environment

Create `.env` file:

```bash
# Google Drive OAuth
GDRIVE_CLIENT_ID="your-client-id"
GDRIVE_CLIENT_SECRET="your-client-secret"
GDRIVE_REDIRECT_URI="http://localhost:8080/oauth2callback"
GDRIVE_CLIENT_SECRETS_FILE="client_secrets.json"

# Google AI API (FREE)
# Get from: https://aistudio.google.com/app/apikey
GOOGLE_API_KEY="your-api-key"

# Flask Secret
FLASK_SECRET_KEY="your-random-secret"

# Vector Database
VECTOR_DB_PROVIDER=postgres

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=enterprise_search
POSTGRES_USER=your_username
POSTGRES_PASSWORD=

# Automatic Sync
AUTO_SYNC=true
AUTO_SYNC_INTERVAL_MINUTES=15
```

### 4. Run the App

```bash
# Start OAuth server (Terminal 1)
python3 app.py

# Authenticate in browser
# http://localhost:8080

# Export credentials
python3 export_credentials.py

# Start Streamlit app (Terminal 2)
streamlit run streamlit_app.py
```

### 5. That's It!

The app will:
- Auto-sync on startup
- Sync every 15 minutes automatically
- Only sync new/modified files
- Support multiple users with data isolation

---

## Key Features

### Fully Automatic Sync
- Auto-sync on startup
- Periodic background sync (every 15 minutes)
- Incremental updates (only new/modified files)
- Smart change detection (Google Drive modifiedTime)
- Deleted file handling

### Multi-User Support
- Complete data isolation per user
- User-specific database tables
- Independent sync state per user
- Concurrent multi-user usage
- No cross-user data access

### Smart Search
- Permission-aware search
- Context-aware semantic search
- Natural language Q&A
- Source citations

### File Support
- PDF, DOCX, XLSX
- Google Docs, Sheets, Slides
- TXT, CSV, JSON
- Pagination (fetches ALL files)

---

## How Automatic Sync Works

### On Startup

```
1. User opens app
2. Authenticates with Google
3. Auto-sync starts:
   Incremental Sync Analysis:
      New files: 2
      Modified files: 1
      Unchanged files: 177 (skipped)
   Auto-sync complete: 35 chunks
```

### During Usage (Every 15 Minutes)

```
Next auto-sync in 3 minute(s)
...
Background sync in progress...
Background sync: 0 chunks (all up to date)
```

---

## Multi-User Implementation

Each user gets:
- Own database table: `documents_{email}`
- Own sync state: `.sync_state/{email}.json`
- Complete data isolation

### Example

```
User 1: ronick@gmail.com
  └─ Table: documents_ronick_at_gmail_com
  └─ Files: 180, Chunks: 1,800

User 2: jane@company.com
  └─ Table: documents_jane_at_company_com
  └─ Files: 50, Chunks: 500

COMPLETELY SEPARATE!
```

---

## Performance

### First Sync
- Files: 180
- Time: ~9 minutes
- Chunks: ~1,800

### Incremental Sync
- Files: 2-5 (new/modified)
- Time: ~15 seconds
- Chunks: ~20-50

---

## Configuration

### Sync Intervals (.env)

```bash
# Recommended (every 15 min)
AUTO_SYNC_INTERVAL_MINUTES=15

# Aggressive (every 5 min)
AUTO_SYNC_INTERVAL_MINUTES=5

# Conservative (every 30 min)
AUTO_SYNC_INTERVAL_MINUTES=30

# Startup only (no periodic)
AUTO_SYNC_INTERVAL_MINUTES=0
```

---

## Troubleshooting

### Auto-sync not working

Check `.env`:
```bash
AUTO_SYNC=true
AUTO_SYNC_INTERVAL_MINUTES=15
```

### PostgreSQL connection errors

```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Verify username
echo $USER  # Use this as POSTGRES_USER
```

### API rate limits

Increase interval:
```bash
AUTO_SYNC_INTERVAL_MINUTES=30
```

---

## Tech Stack

- **Python 3.9+** - Backend
- **Streamlit** - UI
- **Flask** - OAuth server
- **PostgreSQL 18** - Database
- **pgvector 0.8.1** - Vector storage
- **Google Gemini API** - Embeddings & LLM (free tier)
  - `text-embedding-004` (768-dim)
  - `gemini-1.5-flash` (1,500 req/day free)

---

## Security

### What's Secure
OAuth 2.0 authentication  
User data isolation  
Permission filtering  
Local text processing  
No password storage  

### What to Protect
API keys in `.env`  
`client_secrets.json`  
Database credentials  

---

## File Structure

```
enterprise-search-agent/
├── app.py                    # OAuth server
├── streamlit_app.py          # Main UI
├── export_credentials.py     # Credential exporter
├── check_multi_user.py       # Multi-user verifier
├── cleanup_old_tables.sql    # Database cleanup
├── .env                      # Configuration
│
├── connectors/gdrive/        # Google Drive connector
├── database/                 # Vector stores
├── pipeline/                 # Processing pipeline
├── utils/                    # Text extraction, chunking
└── .sync_state/             # Per-user sync state
```

---

## You're All Set!

```bash
streamlit run streamlit_app.py
```

The system will:
1. Auto-sync on startup
2. Sync every 15 minutes
3. Only sync changes
4. Support multiple users
5. Work automatically

**No manual intervention needed!**

---

## Additional Documentation

For detailed information, see:
- `AUTOMATIC_SYNC_AND_MULTI_USER.md` - Complete sync & multi-user guide
- `FEATURES_SUMMARY.md` - Feature checklist
- `YOUR_QUESTIONS_ANSWERED.md` - FAQ
