"""
Authentication module for EyeShield EMR application.
Handles user database, login verification, and user management.
"""

import sqlite3
import hashlib
import os
from typing import Optional

DB_FILE = "users.db"


# ============================================================
# DATABASE CONNECTION
# ============================================================

class DatabaseConnection:
    """Manages database connections"""
    
    @staticmethod
    def get_connection() -> sqlite3.Connection:
        """Get a database connection"""
        return sqlite3.connect(DB_FILE)


def get_connection() -> sqlite3.Connection:
    """Get a database connection (legacy function)"""
    return DatabaseConnection.get_connection()


# ============================================================
# PASSWORD HASHING
# ============================================================

class PasswordManager:
    """Manages password hashing and verification"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using SHA256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify a password against its hash"""
        return PasswordManager.hash_password(password) == password_hash


def hash_password(password: str) -> str:
    """Hash a password (legacy function)"""
    return PasswordManager.hash_password(password)


# ============================================================
# USER DATABASE MANAGEMENT
# ============================================================

class UserManager:
    """Manages user database operations"""
    
    def __init__(self):
        self.conn = self._init_db()
    
    @staticmethod
    def _init_db() -> sqlite3.Connection:
        """Initialize the database"""
        first_run = not os.path.exists(DB_FILE)

        conn = get_connection()
        cur = conn.cursor()
        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
            )
        """)

        # Patient records table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS patient_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT,
                name TEXT,
                birthdate TEXT,
                age TEXT,
                sex TEXT,
                contact TEXT,
                eyes TEXT,
                diabetes_type TEXT,
                duration TEXT,
                hba1c TEXT,
                prev_treatment TEXT,
                notes TEXT,
                result TEXT,
                confidence TEXT
            )
        """)

        conn.commit()

        # Create default admin on first run
        if first_run:
            UserManager.create_user("admin", "admin123", "admin")

        return conn
    
    @staticmethod
    def create_user(username: str, password: str, role: str = "clinician") -> bool:
        """Create a new user"""
        if not username or not password:
            return False
        
        conn = get_connection()
        cur = conn.cursor()
        
        pw_hash = PasswordManager.hash_password(password)
        
        try:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role)
            )
            conn.commit()
            success = True
        except sqlite3.IntegrityError:
            success = False
        
        conn.close()
        return success
    
    @staticmethod
    def verify_user(username: str, password: str) -> Optional[str]:
        """Verify user credentials and return role"""
        if not username or not password:
            return None
        
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute(
            "SELECT password_hash, role FROM users WHERE username = ?",
            (username,)
        )
        
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
        
        pw_hash, role = row
        
        if PasswordManager.verify_password(password, pw_hash):
            return role
        
        return None
    
    @staticmethod
    def get_all_users() -> list[tuple]:
        """Get all users"""
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT username, role FROM users")
        users = cur.fetchall()
        
        conn.close()
        return users
    
    @staticmethod
    def update_user_role(username: str, new_role: str) -> bool:
        """Update a user's role"""
        valid_roles = ["clinician", "admin", "viewer"]
        if new_role not in valid_roles:
            return False
        
        conn = get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                (new_role, username)
            )
            conn.commit()
            success = True
        except sqlite3.Error:
            success = False
        
        conn.close()
        return success
    
    @staticmethod
    def delete_user(username: str) -> bool:
        """Delete a user"""
        conn = get_connection()
        cur = conn.cursor()
        
        try:
            cur.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
            success = True
        except sqlite3.Error:
            success = False
        
        conn.close()
        return success


# ============================================================
# LEGACY FUNCTIONS (for backward compatibility)
# ============================================================

def init_db():
    """Initialize database (legacy function)"""
    UserManager._init_db()


def create_user(username: str, password: str, role: str = "clinician") -> bool:
    """Create a user (legacy function)"""
    return UserManager.create_user(username, password, role)


def verify_user(username: str, password: str) -> Optional[str]:
    """Verify user (legacy function)"""
    return UserManager.verify_user(username, password)

# ============================================================
# INITIALIZE DATABASE ON MODULE LOAD   