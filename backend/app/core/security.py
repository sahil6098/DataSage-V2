import base64
import hashlib
from datetime import timedelta

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.utils.time import ist_now


# Use pbkdf2-sha256 for new passwords so long passphrases work reliably
# without depending on bcrypt's 72-byte input limit. Older accounts can
# still log in with legacy bcrypt hashes and will be upgraded after login.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    if _is_legacy_bcrypt_hash(hashed_password):
        return _verify_legacy_bcrypt(password, hashed_password)
    return pwd_context.verify(password, hashed_password)


def verify_and_update_password(password: str, hashed_password: str) -> tuple[bool, str | None]:
    if _is_legacy_bcrypt_hash(hashed_password):
        verified = _verify_legacy_bcrypt(password, hashed_password)
        return verified, hash_password(password) if verified else None
    return pwd_context.verify_and_update(password, hashed_password)


def _is_legacy_bcrypt_hash(hashed_password: str) -> bool:
    return hashed_password.startswith(("$2a$", "$2b$", "$2y$"))


def _verify_legacy_bcrypt(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def _derive_fernet_key(raw_key: str) -> bytes:
    if len(raw_key) == 44:
        try:
            base64.urlsafe_b64decode(raw_key.encode("utf-8"))
            return raw_key.encode("utf-8")
        except Exception:
            pass

    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_derive_fernet_key(settings.encryption_key))


def encrypt_text(value: str) -> str:
    return get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_text(value: str) -> str:
    return get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def _create_token(
    subject: str,
    secret_key: str,
    expires_delta: timedelta,
    token_type: str,
) -> str:
    now = ist_now()
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires_delta = timedelta(minutes=settings.access_token_expire_minutes)
    return _create_token(subject, settings.jwt_secret_key, expires_delta, "access")


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    expires_delta = timedelta(days=settings.refresh_token_expire_days)
    return _create_token(subject, settings.jwt_refresh_secret_key, expires_delta, "refresh")


def decode_token(token: str, refresh: bool = False) -> dict:
    settings = get_settings()
    secret_key = settings.jwt_refresh_secret_key if refresh else settings.jwt_secret_key
    try:
        return jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token.") from exc


def mask_connection_uri(connection_uri: str) -> str:
    if "://" not in connection_uri:
        return "***"

    scheme, remainder = connection_uri.split("://", 1)
    if "@" not in remainder:
        return f"{scheme}://***"

    credentials, suffix = remainder.split("@", 1)
    username = credentials.split(":", 1)[0]
    masked_user = f"{username[:2]}***" if username else "***"
    return f"{scheme}://{masked_user}:***@{suffix}"
