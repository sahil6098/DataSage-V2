from dataclasses import dataclass
import ipaddress
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.core.security import mask_connection_uri


class ConnectionValidationError(ValueError):
    pass


@dataclass(slots=True)
class ParsedConnection:
    source_type: str
    normalized_uri: str
    masked_uri: str
    database_name: str
    host: str
    display_name: str


def _is_private_host(hostname: str) -> bool:
    lowered = hostname.lower().strip()
    if lowered in {"localhost", "127.0.0.1", "::1"} or lowered.endswith(".local"):
        return True

    try:
        return ipaddress.ip_address(lowered).is_private
    except ValueError:
        return False


def _require(value: str | None, message: str) -> str:
    if not value or not value.strip():
        raise ConnectionValidationError(message)
    return value.strip()


def _normalize_postgres_uri(parsed, database_name: str) -> str:
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    return urlunparse(
        (
            "postgresql",
            parsed.netloc,
            f"/{database_name}",
            "",
            urlencode(query),
            "",
        )
    )


def validate_connection_uri(source_type: str, connection_uri: str, fallback_database_name: str | None = None) -> ParsedConnection:
    parsed = urlparse(connection_uri.strip())
    scheme = parsed.scheme.lower()
    host = _require(parsed.hostname, "Connection URI must include a host.")

    if _is_private_host(host):
        raise ConnectionValidationError("Private or localhost database hosts are not allowed.")

    if source_type == "mongodb":
        if scheme not in {"mongodb+srv", "mongodb"}:
            raise ConnectionValidationError("MongoDB Atlas connections must use mongodb+srv:// or mongodb://.")
        if "mongodb.net" not in host.lower():
            raise ConnectionValidationError("Only MongoDB Atlas hosts are allowed for MongoDB connections.")
        _require(parsed.username, "MongoDB connection URI must include a username.")
        _require(parsed.password, "MongoDB connection URI must include a password.")
        database_name = (parsed.path or "").lstrip("/") or (fallback_database_name or "").strip()
        database_name = _require(database_name, "MongoDB connections require a database name.")
        normalized_uri = connection_uri.strip()
        display_name = database_name
    elif source_type == "postgresql":
        if scheme not in {"postgresql", "postgres"}:
            raise ConnectionValidationError("Supabase connections must use postgresql://.")
        if "supabase" not in host.lower():
            raise ConnectionValidationError("Only Supabase PostgreSQL hosts are allowed.")
        _require(parsed.username, "PostgreSQL connection URI must include a username.")
        _require(parsed.password, "PostgreSQL connection URI must include a password.")
        database_name = (parsed.path or "").lstrip("/")
        database_name = _require(database_name, "PostgreSQL connection URI must include a database name.")
        normalized_uri = _normalize_postgres_uri(parsed, database_name)
        display_name = database_name
    else:
        raise ConnectionValidationError("Unsupported source type.")

    return ParsedConnection(
        source_type=source_type,
        normalized_uri=normalized_uri,
        masked_uri=mask_connection_uri(normalized_uri),
        database_name=database_name,
        host=host,
        display_name=display_name,
    )
