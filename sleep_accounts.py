"""Local account authentication shared by Streamlit and the mobile API."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import re
import secrets
from uuid import uuid4

from health_records import connect, digest, erase_session_rows


class AuthenticationError(ValueError):
    pass


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()


def validate_username(username):
    username = username.strip().casefold()
    if not re.fullmatch(r"[\w.-]{3,40}", username):
        raise ValueError("아이디는 문자·숫자·밑줄·점·하이픈으로 3~40자 입력하세요.")
    return username


def validate_password(password):
    if not 10 <= len(password) <= 128:
        raise ValueError("비밀번호는 10~128자로 입력하세요.")


def register(username, password, db_path=None):
    username = validate_username(username)
    validate_password(password)
    with closing(connect(db_path)) as db, db:
        if db.execute("SELECT 1 FROM accounts WHERE username=?", (username,)).fetchone():
            raise ValueError("이미 사용 중인 아이디입니다.")
        account_id = str(uuid4())
        salt = secrets.token_hex(16)
        db.execute("INSERT INTO accounts VALUES(?,?,?,?,?)", (account_id, username, password_hash(password, salt), salt, datetime.now(timezone.utc).isoformat()))
    return {"id": account_id, "username": username}


def login(username, password, db_path=None):
    username = username.strip().casefold()
    now = datetime.now(timezone.utc)
    with closing(connect(db_path)) as db:
        with db:
            db.execute("DELETE FROM login_attempts WHERE attempted_at<?", ((now - timedelta(minutes=10)).isoformat(),))
            count = db.execute("SELECT count(*) FROM login_attempts WHERE username=?", (username,)).fetchone()[0]
            if count >= 5:
                raise AuthenticationError("로그인 시도가 많습니다. 10분 후 다시 시도하세요.")
            row = db.execute("SELECT * FROM accounts WHERE username=?", (username,)).fetchone()
            # Also spend the password hashing time for nonexistent accounts.
            valid = hmac.compare_digest(password_hash(password[:129], row["salt"] if row else "00" * 16), row["password_hash"] if row else "0" * 64)
            if not row or not valid:
                db.execute("INSERT INTO login_attempts VALUES(?,?)", (username, now.isoformat()))
            else:
                db.execute("DELETE FROM login_attempts WHERE username=?", (username,))
                db.execute("DELETE FROM auth_tokens WHERE expires_at<?", (now.isoformat(),))
                token = secrets.token_urlsafe(32)
                db.execute("INSERT INTO auth_tokens VALUES(?,?,?)", (digest(token), row["id"], (now + timedelta(hours=24)).isoformat()))
                return {"token": token, "user": {"id": row["id"], "username": row["username"]}}
    raise AuthenticationError("아이디 또는 비밀번호를 확인하세요.")


def current_user(token, db_path=None):
    if not token:
        raise AuthenticationError("로그인이 필요합니다.")
    with closing(connect(db_path)) as db:
        row = db.execute("SELECT accounts.id, accounts.username FROM auth_tokens JOIN accounts ON accounts.id=auth_tokens.account_id WHERE token_hash=? AND expires_at>?", (digest(token), datetime.now(timezone.utc).isoformat())).fetchone()
        if row:
            return dict(row)
    raise AuthenticationError("로그인이 만료됐습니다. 다시 로그인하세요.")


def logout(token, db_path=None):
    with closing(connect(db_path)) as db, db:
        db.execute("DELETE FROM auth_tokens WHERE token_hash=?", (digest(token),))


def _verify_account_action(db, account_id, password):
    """Caller holds a write transaction; failed checks must commit their counter."""
    now = datetime.now(timezone.utc)
    db.execute("DELETE FROM login_attempts WHERE attempted_at<?", ((now - timedelta(minutes=10)).isoformat(),))
    row = db.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not row:
        return None, AuthenticationError("계정을 찾을 수 없습니다. 다시 로그인하세요.")
    count = db.execute("SELECT count(*) FROM login_attempts WHERE username=?", (row["username"],)).fetchone()[0]
    if count >= 5:
        return None, AuthenticationError("비밀번호 확인 시도가 많습니다. 10분 후 다시 시도하세요.")
    valid = hmac.compare_digest(password_hash(password[:129], row["salt"]), row["password_hash"])
    if not valid:
        db.execute("INSERT INTO login_attempts VALUES(?,?)", (row["username"], now.isoformat()))
        return None, AuthenticationError("현재 비밀번호를 확인하세요.")
    db.execute("DELETE FROM login_attempts WHERE username=?", (row["username"],))
    return row, None


def update_account(account_id, current_password, new_username=None, new_password=None, db_path=None):
    username = validate_username(new_username) if new_username is not None else None
    if new_password is not None:
        validate_password(new_password)
    if username is None and new_password is None:
        raise ValueError("변경할 아이디나 비밀번호를 입력하세요.")
    with closing(connect(db_path)) as db:
        with db:
            db.execute("BEGIN IMMEDIATE")
            row, error = _verify_account_action(db, account_id, current_password)
            if error is None:
                username = username if username is not None else row["username"]
                if db.execute("SELECT 1 FROM accounts WHERE username=? AND id<>?", (username, account_id)).fetchone():
                    error = ValueError("이미 사용 중인 아이디입니다.")
                elif username == row["username"] and new_password is None:
                    error = ValueError("아이디가 현재와 같습니다. 변경할 내용을 입력하세요.")
                else:
                    salt = secrets.token_hex(16) if new_password is not None else row["salt"]
                    hashed = password_hash(new_password, salt) if new_password is not None else row["password_hash"]
                    db.execute("UPDATE accounts SET username=?, password_hash=?, salt=? WHERE id=?", (username, hashed, salt, account_id))
                    db.execute("DELETE FROM auth_tokens WHERE account_id=?", (account_id,))
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='health_connections'").fetchone():
                        db.execute("DELETE FROM health_connections WHERE account_id=?", (account_id,))
        if error is not None:
            raise error
    return {"id": account_id, "username": username, "reauthentication_required": True}


def erase_account_rows(db, account_id):
    """Erase only this account, including trash and observations outside sessions."""
    from history_service import erase_coaching_rows
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ('sleep_alarm_fires', 'sleep_alarm_settings'):
        if table in tables:
            db.execute('DELETE FROM '+table+' WHERE account_id=?',(account_id,))
    for row in list(db.execute("SELECT id FROM sessions WHERE subject=?", (account_id,))):
        erase_session_rows(db, row["id"], account_id)
    if "coaching" in tables:
        for row in list(db.execute("SELECT id FROM coaching WHERE account_id=?", (account_id,))):
            erase_coaching_rows(db, row["id"], account_id)
    db.execute("DELETE FROM samples WHERE subject=?", (account_id,))
    db.execute("DELETE FROM imports WHERE subject=?", (account_id,))
    if "accounts" in tables:
        db.execute("DELETE FROM login_attempts WHERE username IN (SELECT username FROM accounts WHERE id=?)", (account_id,))
        db.execute("DELETE FROM auth_tokens WHERE account_id=?", (account_id,))
        db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
    if "permanent_deletions" in tables:
        db.execute("DELETE FROM permanent_deletions WHERE subject=?", (account_id,))
    if "coaching_requests" in tables:
        # Keep anonymous request times for the global cap after account deletion.
        db.execute("UPDATE coaching_requests SET account_id=NULL WHERE account_id=?", (account_id,))


def delete_account(account_id, current_password, confirmation, db_path=None):
    if confirmation != "계정 삭제":
        raise ValueError("확인 문구 ‘계정 삭제’를 정확히 입력하세요.")
    with closing(connect(db_path)) as db:
        db.execute("PRAGMA secure_delete=ON")
        with db:
            db.execute("BEGIN IMMEDIATE")
            row, error = _verify_account_action(db, account_id, current_password)
            if error is None:
                erase_account_rows(db, account_id)
                db.execute("INSERT INTO permanent_deletions VALUES(?,?,?,?)", ("account", account_id, account_id, datetime.now(timezone.utc).isoformat()))
        if error is not None:
            raise error
    from backup_policy import maintain_backups
    return {"status": "account_deleted", "backups": maintain_backups(db_path)}
