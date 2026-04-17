import os
import uuid
import requests
from flask import Flask, render_template, request, jsonify, redirect
from dotenv import load_dotenv

load_dotenv()

# Import config
class Config:
    HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY", "")
    HCAPTCHA_SITE_KEY = os.getenv("HCAPTCHA_SITE_KEY", "")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")
    VERIFICATION_TIMEOUT = 600
    MAX_ATTEMPTS = 3
    LOCKOUT_DURATION = 600


# Simple in-memory storage for Vercel (serverless)
# Note: This resets on each function invocation in serverless
# For production, use a database or external storage
class SimpleDB:
    def __init__(self):
        self.verifications = {}
    
    def create_verification(self, user_id: int, token: str, timeout: int = 600):
        import time
        current_time = time.time()
        self.verifications[token] = {
            "user_id": user_id,
            "token": token,
            "created_at": current_time,
            "expires_at": current_time + timeout,
            "attempts": 0,
            "locked_until": 0,
            "verified": 0
        }
        return self.verifications[token]
    
    def get_verification_by_token(self, token: str):
        return self.verifications.get(token)
    
    def get_verification(self, user_id: int):
        for v in self.verifications.values():
            if v["user_id"] == user_id:
                return v
        return None
    
    def is_expired(self, user_id: int):
        import time
        v = self.get_verification(user_id)
        if v and time.time() > v["expires_at"]:
            return True
        return False
    
    def is_locked_out(self, user_id: int):
        import time
        v = self.get_verification(user_id)
        if v and v["locked_until"] > time.time():
            return True
        return False
    
    def get_lockout_remaining(self, user_id: int):
        import time
        v = self.get_verification(user_id)
        if v and v["locked_until"] > time.time():
            return v["locked_until"] - time.time()
        return 0
    
    def increment_attempts(self, user_id: int):
        v = self.get_verification(user_id)
        if v:
            v["attempts"] += 1
            return v["attempts"]
        return 0
    
    def set_lockout(self, user_id: int, duration: int = 600):
        import time
        v = self.get_verification(user_id)
        if v:
            v["locked_until"] = time.time() + duration
            return v["locked_until"]
        return 0
    
    def mark_verified(self, user_id: int):
        v = self.get_verification(user_id)
        if v:
            v["verified"] = 1
    
    def is_verified(self, user_id: int):
        v = self.get_verification(user_id)
        return v and v["verified"] == 1
    
    def get_newly_verified(self):
        return [v["user_id"] for v in self.verifications.values() if v["verified"] == 1]
    
    def delete_verification(self, user_id: int):
        token_to_delete = None
        for token, v in self.verifications.items():
            if v["user_id"] == user_id:
                token_to_delete = token
                break
        if token_to_delete:
            del self.verifications[token_to_delete]


# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = str(uuid.uuid4())

# Initialize DB
db = SimpleDB()


@app.route('/')
def index():
    """Redirect to verification page."""
    return redirect('/verify')


@app.route('/verify')
def verify_page():
    """Render the verification page with hCaptcha."""
    token = request.args.get('token', '')
    
    if not token:
        return render_template(
            'verification.html',
            site_key=Config.HCAPTCHA_SITE_KEY,
            error="Invalid verification link."
        ), 400
    
    # Check if verification exists and is valid
    verification = db.get_verification_by_token(token)
    if not verification:
        return render_template(
            'verification.html',
            site_key=Config.HCAPTCHA_SITE_KEY,
            error="Verification session not found. Please request a new verification link."
        )
    
    if db.is_expired(verification['user_id']):
        return render_template(
            'verification.html',
            site_key=Config.HCAPTCHA_SITE_KEY,
            error="Verification link has expired. Please use /verify in Discord to get a new link."
        )
    
    if db.is_locked_out(verification['user_id']):
        remaining = db.get_lockout_remaining(verification['user_id'])
        minutes = int(remaining / 60)
        return render_template(
            'verification.html',
            site_key=Config.HCAPTCHA_SITE_KEY,
            error=f"You are temporarily locked out. Please try again in {minutes} minute(s)."
        )
    
    return render_template(
        'verification.html',
        site_key=Config.HCAPTCHA_SITE_KEY,
        token=token
    )


@app.route('/submit', methods=['POST'])
def submit_verification():
    """Handle hCaptcha verification submission."""
    data = request.get_json()
    hcaptcha_token = data.get('hcaptcha_token', '')
    user_token = data.get('token', '')
    
    if not hcaptcha_token or not user_token:
        return jsonify({
            'success': False,
            'message': 'Missing required fields.'
        }), 400
    
    # Get verification session
    verification = db.get_verification_by_token(user_token)
    if not verification:
        return jsonify({
            'success': False,
            'message': 'Verification session not found.'
        }), 400
    
    # Check if expired
    if db.is_expired(verification['user_id']):
        return jsonify({
            'success': False,
            'message': 'Verification link has expired.'
        }), 400
    
    # Check if locked out
    if db.is_locked_out(verification['user_id']):
        remaining = db.get_lockout_remaining(verification['user_id'])
        minutes = int(remaining / 60)
        return jsonify({
            'success': False,
            'message': f'Temporarily locked out. Try again in {minutes} minute(s).'
        }), 429
    
    # Verify hCaptcha
    verify_url = "https://hcaptcha.com/siteverify"
    verify_data = {
        'secret': Config.HCAPTCHA_SECRET_KEY,
        'response': hcaptcha_token,
        'sitekey': Config.HCAPTCHA_SITE_KEY
    }
    
    try:
        response = requests.post(verify_url, data=verify_data, timeout=10)
        result = response.json()
    except Exception as e:
        return jsonify({
            'success': False,
            'message': 'Failed to verify captcha. Please try again.'
        }), 500
    
    if not result.get('success'):
        # Increment failed attempts
        attempts = db.increment_attempts(verification['user_id'])
        
        if attempts >= Config.MAX_ATTEMPTS:
            # Set lockout
            lockout_until = db.set_lockout(verification['user_id'], Config.LOCKOUT_DURATION)
            return jsonify({
                'success': False,
                'message': 'Too many failed attempts. You are locked out for 10 minutes.',
                'locked': True,
                'locked_until': lockout_until
            })
        
        remaining = Config.MAX_ATTEMPTS - attempts
        return jsonify({
            'success': False,
            'message': f'Captcha verification failed. {remaining} attempt(s) remaining.',
            'attempts_remaining': remaining
        })
    
    # Success! Mark as verified in database
    db.mark_verified(verification['user_id'])
    
    return jsonify({
        'success': True,
        'user_id': verification['user_id']
    })


# API endpoints for bot communication
@app.route('/api/verification/<int:user_id>', methods=['POST'])
def create_verification(user_id: int):
    """Create a new verification session (called by bot)."""
    import uuid
    token = str(uuid.uuid4())
    db.create_verification(user_id, token, Config.VERIFICATION_TIMEOUT)
    return jsonify({
        'success': True,
        'token': token,
        'url': f"{Config.BASE_URL}/verify?token={token}"
    })


@app.route('/api/verified', methods=['GET'])
def get_verified():
    """Get list of newly verified users (called by bot)."""
    verified = db.get_newly_verified()
    return jsonify({'verified_users': verified})


@app.route('/api/check/<int:user_id>', methods=['GET'])
def check_verification(user_id: int):
    """Check if a user is verified."""
    is_verified = db.is_verified(user_id)
    return jsonify({'verified': is_verified})


@app.route('/api/delete/<int:user_id>', methods=['DELETE'])
def delete_verification(user_id: int):
    """Delete a verification session."""
    db.delete_verification(user_id)
    return jsonify({'success': True})


# Export app for Vercel
app = app