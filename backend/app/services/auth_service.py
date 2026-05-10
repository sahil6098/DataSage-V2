from hashlib import sha256

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_and_update_password,
)
from app.db.mongo import get_database
from app.schemas.auth import AuthTokensOut, LoginRequest, RegisterRequest, UserOut
from app.utils.time import ist_now


class AuthService:
    def __init__(self) -> None:
        self.db = get_database()

    async def register(self, payload: RegisterRequest) -> AuthTokensOut:
        now = ist_now()
        document = {
            "name": payload.name.strip(),
            "email": payload.email.lower().strip(),
            "password_hash": hash_password(payload.password),
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = await self.db.users.insert_one(document)
        except DuplicateKeyError as exc:
            raise ValueError("An account with that email already exists.") from exc

        user_id = str(result.inserted_id)
        return await self._issue_tokens(user_id, document["email"], document["name"])

    async def login(self, payload: LoginRequest) -> AuthTokensOut:
        user = await self.db.users.find_one({"email": payload.email.lower().strip()})
        if not user:
            raise ValueError("Invalid email or password.")

        verified, upgraded_hash = verify_and_update_password(payload.password, user["password_hash"])
        if not verified:
            raise ValueError("Invalid email or password.")

        if upgraded_hash:
            await self.db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"password_hash": upgraded_hash, "updated_at": ist_now()}},
            )

        return await self._issue_tokens(str(user["_id"]), user["email"], user["name"])

    async def refresh(self, refresh_token: str) -> AuthTokensOut:
        from app.core.security import decode_token

        try:
            payload = decode_token(refresh_token, refresh=True)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        if payload.get("type") != "refresh":
            raise ValueError("Invalid refresh token.")

        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid refresh token subject.")

        refresh_hash = sha256(refresh_token.encode("utf-8")).hexdigest()
        token_document = await self.db.refresh_tokens.find_one(
            {"user_id": user_id, "token_hash": refresh_hash, "revoked_at": None}
        )
        if not token_document:
            raise ValueError("Refresh token has expired or was revoked.")

        user = await self.db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise ValueError("User not found.")

        return await self._issue_tokens(user_id, user["email"], user["name"], revoke_hash=refresh_hash)

    async def get_user(self, user: dict) -> UserOut:
        return UserOut(id=str(user["_id"]), email=user["email"], name=user["name"])

    async def _issue_tokens(
        self,
        user_id: str,
        email: str,
        name: str,
        revoke_hash: str | None = None,
    ) -> AuthTokensOut:
        now = ist_now()
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)
        refresh_hash = sha256(refresh_token.encode("utf-8")).hexdigest()

        if revoke_hash:
            await self.db.refresh_tokens.update_one(
                {"user_id": user_id, "token_hash": revoke_hash, "revoked_at": None},
                {"$set": {"revoked_at": now}},
            )

        await self.db.refresh_tokens.insert_one(
            {
                "user_id": user_id,
                "token_hash": refresh_hash,
                "created_at": now,
                "revoked_at": None,
            }
        )

        return AuthTokensOut(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserOut(id=user_id, email=email, name=name),
        )
