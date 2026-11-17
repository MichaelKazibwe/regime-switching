"""Invitation-only pilot accounts, revocable sessions and durable throttling."""

from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

USERNAME = re.compile(r"[a-z0-9][a-z0-9@._+-]{2,127}\Z")


def password_hash(password, salt):
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise ValueError("Use a password of 12–256 characters")
    digest = hashlib.scrypt(password.encode(), salt=salt, n=131072, r=8, p=1,
                            maxmem=256 * 1024 * 1024).hex()
    return "scrypt-v1-n131072-r8-p1:" + digest


class AuthStore:
    def __init__(self, database, *, clock=time.time, idle_seconds=1800, absolute_seconds=28800):
        self.path, self.clock = Path(database), clock
        self.idle, self.absolute = idle_seconds, absolute_seconds
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("A regular private authentication database is required")
        self.dummy_salt = bytes.fromhex("a1" * 16)
        self.dummy_hash = password_hash("not-an-account-password-123", self.dummy_salt)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users(
                  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                  salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                  role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                  must_change INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS sessions(
                  token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                  csrf TEXT NOT NULL, created REAL NOT NULL, seen REAL NOT NULL,
                  expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS failures(
                  key TEXT PRIMARY KEY, count INTEGER NOT NULL, until REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(
                  seq INTEGER PRIMARY KEY, time REAL NOT NULL,
                  event TEXT NOT NULL, user_id TEXT);
            """)
        os.chmod(self.path, 0o600)

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            yield db

    def add_user(self, username, password, *, role="tester", must_change=True):
        username = username.strip().lower()
        if not USERNAME.fullmatch(username) or role not in {"tester", "viewer"}:
            raise ValueError("Invalid username or role")
        salt = secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        user_id = secrets.token_hex(16)
        with self.connection() as db:
            try:
                db.execute("INSERT INTO users(id,username,salt,password_hash,role,must_change) VALUES(?,?,?,?,?,?)",
                           (user_id, username, salt.hex(), hashed, role, int(must_change)))
            except sqlite3.IntegrityError:
                if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                    raise ValueError("Account already exists; use explicit reset-password to reset credentials") from None
                raise
            db.execute("INSERT INTO audit(time,event,user_id) VALUES(?,?,?)",
                       (self.clock(), "ACCOUNT_INVITED", user_id))
        return user_id

    def revoke_user(self, username):
        with self.connection() as db:
            user = db.execute("SELECT id FROM users WHERE username=?", (username.lower(),)).fetchone()
            if not user:
                raise ValueError("Unknown account")
            db.execute("UPDATE users SET active=0 WHERE id=?", (user["id"],))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("INSERT INTO audit(time,event,user_id) VALUES(?,?,?)",
                       (self.clock(), "ACCOUNT_REVOKED", user["id"]))

    def list_users(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute("SELECT username,role,active,must_change FROM users ORDER BY username")]

    def reset_password(self, username, password, *, reactivate=False):
        salt = secrets.token_bytes(16)
        hashed = password_hash(password, salt)
        with self.connection() as db:
            user = db.execute("SELECT * FROM users WHERE username=?", (username.lower(),)).fetchone()
            if not user or (not user["active"] and not reactivate):
                raise ValueError("Unknown or disabled account; reactivation must be explicit")
            db.execute("UPDATE users SET salt=?,password_hash=?,must_change=1,active=1 WHERE id=?",
                       (salt.hex(), hashed, user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("DELETE FROM failures WHERE key=?", (hashlib.sha256(("account:" + username.lower()).encode()).hexdigest(),))
            db.execute("INSERT INTO audit(time,event,user_id) VALUES(?,?,?)",
                       (self.clock(), "PASSWORD_RESET_SESSIONS_REVOKED", user["id"]))

    def login(self, username, password, peer):
        if not isinstance(username, str) or not isinstance(password, str):
            raise PermissionError("Invalid credentials")
        username = username.strip().lower()[:128]
        now = self.clock()
        keys = [hashlib.sha256((prefix + value).encode()).hexdigest()
                for prefix, value in [("account:", username), ("peer:", str(peer))]]
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM failures WHERE until < ?", (now,))
            for key in keys:
                row = db.execute("SELECT count,until FROM failures WHERE key=?", (key,)).fetchone()
                if row and row["count"] >= (10 if key == keys[0] else 60):
                    raise PermissionError("Invalid credentials or temporary login limit")
            user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            salt = bytes.fromhex(user["salt"]) if user else self.dummy_salt
            expected = user["password_hash"] if user else self.dummy_hash
            try:
                supplied = password_hash(password, salt)
            except ValueError:
                supplied = password_hash("invalid-length-password-123", salt)
                user = None
            accepted = bool(user and user["active"] and hmac.compare_digest(supplied, expected))
            if not accepted:
                for key in keys:
                    db.execute("INSERT INTO failures VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1",
                               (key, now + 900))
                db.execute("INSERT INTO audit(time,event,user_id) VALUES(?,?,?)",
                           (now, "LOGIN_FAILED", user["id"] if user else None))
                # Commit the failure before raising outside the transaction.
                db.commit()
            else:
                db.execute("DELETE FROM failures WHERE key=?", (keys[0],))
                db.execute("DELETE FROM sessions WHERE expires <= ? OR seen < ?", (now, now - self.idle))
                active = db.execute("SELECT token_hash FROM sessions WHERE user_id=? ORDER BY created DESC",
                                    (user["id"],)).fetchall()
                for row in active[4:]:
                    db.execute("DELETE FROM sessions WHERE token_hash=?", (row["token_hash"],))
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?)",
                           (hashlib.sha256(token.encode()).hexdigest(), user["id"], csrf,
                            now, now, now + self.absolute))
                db.execute("INSERT INTO audit(time,event,user_id) VALUES(?,?,?)",
                           (now, "LOGIN_SUCCEEDED", user["id"]))
                return token
        raise PermissionError("Invalid credentials or temporary login limit")

    def session(self, token):
        if not isinstance(token, str) or not 30 <= len(token) <= 128:
            return None
        key = hashlib.sha256(token.encode()).hexdigest()
        now = self.clock()
        with self.connection() as db:
            row = db.execute("""SELECT s.*,u.username,u.role,u.active,u.must_change FROM sessions s
                                JOIN users u ON u.id=s.user_id WHERE s.token_hash=?""", (key,)).fetchone()
            if not row or not row["active"] or row["expires"] <= now or row["seen"] < now - self.idle:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (key,))
                return None
            db.execute("UPDATE sessions SET seen=? WHERE token_hash=?", (now, key))
            return dict(row)

    def logout(self, token):
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, session, old_password, new_password):
        with self.connection() as db:
            user = db.execute("SELECT * FROM users WHERE id=? AND active=1", (session["user_id"],)).fetchone()
            if not user or not hmac.compare_digest(password_hash(old_password, bytes.fromhex(user["salt"])),
                                                  user["password_hash"]):
                raise PermissionError("Current password is incorrect")
            salt = secrets.token_bytes(16)
            hashed = password_hash(new_password, salt)
            db.execute("UPDATE users SET salt=?,password_hash=?,must_change=0 WHERE id=?",
                       (salt.hex(), hashed, user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            db.execute("INSERT INTO audit(time,event,user_id) VALUES(?,?,?)",
                       (self.clock(), "PASSWORD_CHANGED_SESSIONS_REVOKED", user["id"]))

    def backup(self, destination):
        destination = Path(destination)
        if destination.exists():
            raise ValueError("Use a new backup destination")
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connection() as source, sqlite3.connect(destination) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Backup integrity failed")
        os.chmod(destination, 0o600)
