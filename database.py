import sqlite3
import json
import time
from typing import Optional, Dict, Any
from contextlib import contextmanager


class Database:
    def __init__(self, db_path: str = "verification.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Server settings table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    guild_id INTEGER PRIMARY KEY,
                    verified_role_id INTEGER,
                    log_channel_id INTEGER,
                    kick_unverified INTEGER DEFAULT 0,
                    kick_timer INTEGER DEFAULT 30
                )
            """)
            
            # Pending verifications table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pending_verifications (
                    user_id INTEGER PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    attempts INTEGER DEFAULT 0,
                    locked_until REAL DEFAULT 0,
                    verified INTEGER DEFAULT 0
                )
            """)
            
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # Server Settings Methods
    def get_server_settings(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get server settings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM server_settings WHERE guild_id = ?",
                (guild_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def set_server_settings(
        self,
        guild_id: int,
        verified_role_id: int = None,
        log_channel_id: int = None,
        kick_unverified: bool = False,
        kick_timer: int = 30
    ):
        """Set or update server settings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO server_settings (guild_id, verified_role_id, log_channel_id, kick_unverified, kick_timer)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    verified_role_id = COALESCE(excluded.verified_role_id, server_settings.verified_role_id),
                    log_channel_id = COALESCE(excluded.log_channel_id, server_settings.log_channel_id),
                    kick_unverified = COALESCE(excluded.kick_unverified, server_settings.kick_unverified),
                    kick_timer = COALESCE(excluded.kick_timer, server_settings.kick_timer)
            """, (guild_id, verified_role_id, log_channel_id, int(kick_unverified), kick_timer))
            conn.commit()

    # Verification Methods
    def create_verification(
        self,
        user_id: int,
        token: str,
        timeout: int = 600
    ) -> Dict[str, Any]:
        """Create a new verification session."""
        current_time = time.time()
        expires_at = current_time + timeout
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO pending_verifications
                (user_id, token, created_at, expires_at, attempts, locked_until, verified)
                VALUES (?, ?, ?, ?, 0, 0, 0)
            """, (user_id, token, current_time, expires_at))
            conn.commit()
        
        return {
            "user_id": user_id,
            "token": token,
            "created_at": current_time,
            "expires_at": expires_at,
            "attempts": 0,
            "locked_until": 0
        }

    def get_verification(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get pending verification for a user."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def get_verification_by_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Get pending verification by token."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM pending_verifications WHERE token = ?",
                (token,)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def increment_attempts(self, user_id: int) -> int:
        """Increment failed attempts and return new count."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT attempts FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row:
                new_attempts = row[0] + 1
                cursor.execute(
                    "UPDATE pending_verifications SET attempts = ? WHERE user_id = ?",
                    (new_attempts, user_id)
                )
                conn.commit()
                return new_attempts
            return 0

    def set_lockout(self, user_id: int, duration: int = 600):
        """Set lockout for a user (default 10 minutes)."""
        lockout_until = time.time() + duration
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_verifications SET locked_until = ? WHERE user_id = ?",
                (lockout_until, user_id)
            )
            conn.commit()
        return lockout_until

    def is_locked_out(self, user_id: int) -> bool:
        """Check if user is locked out."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT locked_until FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and row[0] > time.time():
                return True
            return False

    def get_lockout_remaining(self, user_id: int) -> float:
        """Get remaining lockout time in seconds."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT locked_until FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and row[0] > time.time():
                return row[0] - time.time()
            return 0

    def is_expired(self, user_id: int) -> bool:
        """Check if verification session is expired."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT expires_at FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            if row and time.time() > row[0]:
                return True
            return False

    def delete_verification(self, user_id: int):
        """Delete verification session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()

    def mark_verified(self, user_id: int):
        """Mark a verification as completed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE pending_verifications SET verified = 1 WHERE user_id = ?",
                (user_id,)
            )
            conn.commit()

    def is_verified(self, user_id: int) -> bool:
        """Check if user has completed verification."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT verified FROM pending_verifications WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return row and row[0] == 1

    def get_newly_verified(self) -> list:
        """Get list of newly verified user IDs."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT user_id FROM pending_verifications WHERE verified = 1",
                ()
            )
            return [row[0] for row in cursor.fetchall()]

    def cleanup_expired(self):
        """Clean up all expired verification sessions."""
        current_time = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM pending_verifications WHERE expires_at < ? AND locked_until < ?",
                (current_time, current_time)
            )
            conn.commit()
            return cursor.rowcount