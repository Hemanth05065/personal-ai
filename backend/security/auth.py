import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import AuthSession, Device, User, now_utc
from backend.security.audit import append_security_event

SESSION_COOKIE = "assistant_session"
DEVICE_COOKIE = "assistant_device"


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    role: str
    session_id: str | None = None
    service: bool = False


@dataclass(frozen=True)
class LoginTokens:
    session_token: str
    device_token: str
    csrf_token: str
    expires_at: datetime
    user: User


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    categories = [
        any(char.islower() for char in password),
        any(char.isupper() for char in password),
        any(char.isdigit() for char in password),
        any(not char.isalnum() for char in password),
    ]
    if sum(categories) < 3:
        raise ValueError("Password must use at least three character categories.")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    derived = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=32)
    return "$".join(
        [
            "scrypt",
            str(n),
            str(r),
            str(p),
            base64.urlsafe_b64encode(salt).decode(),
            base64.urlsafe_b64encode(derived).decode(),
        ]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(
            password.encode(),
            salt=base64.urlsafe_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(derived, base64.urlsafe_b64decode(expected))
    except (ValueError, TypeError):
        return False


def create_user(db: Session, username: str, password: str, role: str = "admin") -> User:
    if db.scalar(select(User).where(User.username == username.lower())):
        raise ValueError("Username already exists.")
    user = User(username=username.lower(), password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    append_security_event(db, "auth.user_created", "success", f"username={user.username}", user.id)
    return user


def verify_login(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username.lower()))
    if user is None or user.disabled or not verify_password(password, user.password_hash):
        append_security_event(db, "auth.login", "denied", f"username={username.lower()}")
        db.commit()
        return None
    return user


def create_login(
    db: Session,
    user: User,
    device_name: str,
    existing_device_token: str | None = None,
) -> LoginTokens:
    device = None
    if existing_device_token:
        device = db.scalar(
            select(Device).where(
                Device.user_id == user.id,
                Device.token_hash == hash_token(existing_device_token),
                Device.trusted.is_(True),
            )
        )
    device_token = existing_device_token or secrets.token_urlsafe(32)
    if device is None:
        device_token = secrets.token_urlsafe(32)
        device = Device(user_id=user.id, name=device_name, token_hash=hash_token(device_token))
        db.add(device)
        db.flush()
    device.last_seen = now_utc()
    session_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    expires = now_utc() + timedelta(hours=get_settings().session_hours)
    session = AuthSession(
        user_id=user.id,
        device_id=device.id,
        token_hash=hash_token(session_token),
        csrf_hash=hash_token(csrf_token),
        expires_at=expires,
    )
    db.add(session)
    db.flush()
    append_security_event(db, "auth.login", "success", f"device={device.id}", user.id)
    db.commit()
    return LoginTokens(session_token, device_token, csrf_token, expires, user)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def authenticate_session(
    db: Session, session_token: str | None, device_token: str | None
) -> tuple[Principal, AuthSession] | None:
    if not session_token or not device_token:
        return None
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(session_token)))
    if session is None or session.revoked_at or _aware(session.expires_at) <= datetime.now(UTC):
        return None
    device = db.get(Device, session.device_id)
    user = db.get(User, session.user_id)
    if not device or not user or user.disabled or not device.trusted:
        return None
    if not hmac.compare_digest(device.token_hash, hash_token(device_token)):
        return None
    session.last_seen = now_utc()
    device.last_seen = now_utc()
    db.commit()
    return Principal(user.id, user.username, user.role, session.id), session


def revoke_session(db: Session, session_id: str, actor_id: str) -> None:
    session = db.get(AuthSession, session_id)
    if session and session.revoked_at is None:
        session.revoked_at = now_utc()
        append_security_event(db, "auth.logout", "success", f"session={session_id}", actor_id)
        db.commit()
