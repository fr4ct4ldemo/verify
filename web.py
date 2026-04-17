import uuid
import requests
from flask import Flask, render_template, request, jsonify, redirect
from config import Config
from database import Database

app = Flask(__name__)
app.config['SECRET_KEY'] = str(uuid.uuid4())

db = Database()


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


if __name__ == '__main__':
    app.run(host=Config.WEB_HOST, port=Config.WEB_PORT, debug=False)