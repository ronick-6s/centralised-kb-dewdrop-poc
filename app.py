"""
Flask app for OAuth authentication flow.
Run this to authenticate, then use streamlit_app.py for the main UI.
"""

from flask import Flask, redirect, request, session, url_for, render_template_string
import os
import json
from dotenv import load_dotenv
from connectors.gdrive.gdrive_connector import GDriveConnector

load_dotenv()

app = Flask(__name__)

# Configure Flask
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_TYPE'] = 'filesystem'  # Use filesystem for session storage
app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour

# For development only - disable in production
app.config['DEBUG'] = True

# Simple HTML template
INDEX_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Enterprise Search Agent - Authentication</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
        }
        .container {
            background: #f5f5f5;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 { color: #333; }
        .btn {
            display: inline-block;
            padding: 12px 24px;
            background: #4285f4;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 10px 0;
        }
        .btn:hover { background: #357ae8; }
        .success { color: #0f9d58; }
        .info { background: #e8f0fe; padding: 15px; border-radius: 5px; margin: 20px 0; }
        pre { background: #fff; padding: 10px; border-radius: 5px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔍 Enterprise Search Agent</h1>
        {% if authenticated %}
            <p class="success">✅ Successfully authenticated as: <strong>{{ user_email }}</strong></p>
            <div class="info">
                <h3>Next Steps:</h3>
                <ol>
                    <li>Your credentials are saved in the session</li>
                    <li>Run the Streamlit app to start searching:</li>
                </ol>
                <pre>streamlit run streamlit_app.py</pre>
            </div>
            <a href="/export_credentials" class="btn">💾 Export Credentials for Streamlit</a>
        {% else %}
            <p>Connect your Google Drive to get started with the Enterprise Search Agent.</p>
            <a href="/connect" class="btn">🔐 Connect Google Drive</a>
        {% endif %}
    </div>
</body>
</html>
"""

SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Credentials Exported</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 30px; border-radius: 10px; }
        .success { color: #0f9d58; }
        pre { background: #fff; padding: 15px; border-radius: 5px; overflow-x: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="success">✅ Credentials Exported</h1>
        <p>Your credentials have been saved to <code>.streamlit_credentials.json</code></p>
        <p>You can now run the Streamlit app:</p>
        <pre>streamlit run streamlit_app.py</pre>
        <p><a href="/">← Back to home</a></p>
    </div>
</body>
</html>
"""

@app.route('/')
def index():
    """Home page showing authentication status."""
    try:
        authenticated = 'credentials' in session
        user_email = session.get('user_email', '')
        return render_template_string(
            INDEX_TEMPLATE, 
            authenticated=authenticated,
            user_email=user_email
        )
    except Exception as e:
        return f"Error: {str(e)}<br><a href='/clear_session'>Clear session and try again</a>", 500

@app.route('/clear_session')
def clear_session():
    """Clear the session (useful for debugging)."""
    session.clear()
    return redirect(url_for('index'))

@app.route('/connect')
def connect():
    # Clear any old session data
    session.clear()
    
    client_secrets_file = os.getenv('GDRIVE_CLIENT_SECRETS_FILE', 'client_secrets.json')
    gdrive_connector = GDriveConnector(client_secrets_file=client_secrets_file)
    auth_url = gdrive_connector.get_auth_url()
    state = gdrive_connector.get_state()
    
    # Store state in session for CSRF protection
    session['oauth_state'] = state
    session.modified = True
    
    print(f"🔑 Generated OAuth state: {state[:20]}...")
    print(f"🔗 Redirecting to: {auth_url[:80]}...")
    
    return redirect(auth_url)

@app.route('/oauth2callback')
def oauth2callback():
    # Check if state exists in session
    state = session.get('oauth_state')
    
    if not state:
        return """
        <h1>Session Error</h1>
        <p>OAuth state not found in session. This usually means:</p>
        <ul>
            <li>Cookies are blocked by your browser</li>
            <li>You're using an old authorization link</li>
            <li>Session expired</li>
        </ul>
        <p><a href="/connect">Click here to start fresh</a></p>
        """, 400
    
    print(f"🔍 Session state: {state[:20]}...")
    print(f"🔍 Callback URL: {request.url[:100]}...")
    
    client_secrets_file = os.getenv('GDRIVE_CLIENT_SECRETS_FILE', 'client_secrets.json')
    gdrive_connector = GDriveConnector(client_secrets_file=client_secrets_file, state=state)
    
    try:
        # Get credentials from OAuth callback
        credentials = gdrive_connector.get_credentials(request.url)
        
        # Store credentials in session
        session['credentials'] = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Get user email
        try:
            gdrive_connector.set_credentials(session['credentials'])
            user_email = gdrive_connector.get_user_email()
            session['user_email'] = user_email
            print(f"✅ Authenticated as: {user_email}")
        except Exception as e:
            print(f"⚠️ Error getting user email: {e}")
            session['user_email'] = "unknown@example.com"
        
        # Clear the state from session
        session.pop('oauth_state', None)
        
        return redirect(url_for('index'))
        
    except Exception as e:
        print(f"❌ OAuth callback error: {e}")
        return f"""
        <h1>Authentication Error</h1>
        <p>Error: {str(e)}</p>
        <p><a href="/clear_session">Clear session and try again</a></p>
        """, 500

@app.route('/export_credentials')
def export_credentials():
    """Export credentials to a file for use with Streamlit."""
    if 'credentials' not in session:
        return redirect(url_for('index'))
    
    credentials_data = {
        'credentials': session['credentials'],
        'user_email': session.get('user_email', '')
    }
    
    with open('.streamlit_credentials.json', 'w') as f:
        json.dump(credentials_data, f, indent=2)
    
    return render_template_string(SUCCESS_TEMPLATE)

if __name__ == '__main__':
    # Make sure to use http://localhost:8080/oauth2callback as your redirect URI
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    print("\n" + "="*60)
    print("🚀 Flask OAuth Server Starting")
    print("="*60)
    print(f"\n📍 Open in browser: http://localhost:8080")
    print(f"📍 Alternative URL: http://127.0.0.1:8080")
    print(f"\n🔐 Make sure your Google OAuth redirect URI is set to:")
    print(f"   http://localhost:8080/oauth2callback")
    print("="*60 + "\n")
    
    app.run(debug=True, host='127.0.0.1', port=8080, threaded=True)
