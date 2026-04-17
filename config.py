import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Discord Bot
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
    
    # hCaptcha
    HCAPTCHA_SECRET_KEY = os.getenv("HCAPTCHA_SECRET_KEY", "")
    HCAPTCHA_SITE_KEY = os.getenv("HCAPTCHA_SITE_KEY", "")
    
    # Web Server
    WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
    WEB_PORT = int(os.getenv("WEB_PORT", "5000"))
    
    # Base URL - used for verification links (Vercel deployment URL)
    # Falls back to localhost for local development
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000")
    
    # Verification Settings
    VERIFICATION_TIMEOUT = 600  # 10 minutes in seconds
    MAX_ATTEMPTS = 3
    LOCKOUT_DURATION = 600  # 10 minutes in seconds
    DEFAULT_KICK_TIMER = 30  # 30 minutes
    
    # Colors for embeds
    COLOR_INFO = 0x3498db      # Blue
    COLOR_SUCCESS = 0x2ecc71   # Green
    COLOR_ERROR = 0xe74c3c     # Red
    COLOR_WARNING = 0xf39c12   # Orange
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        if not cls.DISCORD_TOKEN:
            print("Error: DISCORD_TOKEN is not set in .env file")
            return False
        if not cls.HCAPTCHA_SECRET_KEY:
            print("Error: HCAPTCHA_SECRET_KEY is not set in .env file")
            return False
        if not cls.HCAPTCHA_SITE_KEY:
            print("Error: HCAPTCHA_SITE_KEY is not set in .env file")
            return False
        return True