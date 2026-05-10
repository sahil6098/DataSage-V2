export const SAVED_DB_CONNECTIONS_KEY = "saved_db_connections";

export interface SavedConnection {
  name: string;
  url: string;
  type?: string;
  databaseName?: string;
}

function canUseLocalStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function canUseSessionStorage() {
  return typeof window !== "undefined" && typeof window.sessionStorage !== "undefined";
}

function readSavedConnectionsFromStorage(storage: Storage | null, storageKey: string): SavedConnection[] | null {
  if (!storage) {
    return null;
  }

  const rawValue = storage.getItem(storageKey);
  if (rawValue === null) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .map(normalizeSavedConnection)
      .filter((entry): entry is SavedConnection => Boolean(entry));
  } catch {
    return [];
  }
}

function writeSavedConnectionsToStorage(storageKey: string, connections: SavedConnection[]) {
  const serializedConnections = JSON.stringify(connections);

  if (canUseLocalStorage()) {
    window.localStorage.setItem(storageKey, serializedConnections);
  }

  // Mirror into sessionStorage so the currently open tab stays in sync during the transition away from session-only storage.
  if (canUseSessionStorage()) {
    window.sessionStorage.setItem(storageKey, serializedConnections);
  }
}

function decodeBase64Url(value: string) {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), "=");
  return window.atob(padded);
}

function getAuthenticatedUserId() {
  if (!canUseLocalStorage()) {
    return null;
  }

  const token = window.localStorage.getItem("access_token") || window.localStorage.getItem("refresh_token");
  if (!token) {
    return null;
  }

  try {
    const [, payload] = token.split(".");
    if (!payload) {
      return null;
    }

    const parsed = JSON.parse(decodeBase64Url(payload)) as { sub?: unknown };
    return typeof parsed.sub === "string" && parsed.sub.trim() ? parsed.sub.trim() : null;
  } catch {
    return null;
  }
}

function getSavedConnectionsStorageKey() {
  const userId = getAuthenticatedUserId();
  return userId ? `${SAVED_DB_CONNECTIONS_KEY}:${userId}` : null;
}

function normalizeSavedConnection(entry: unknown): SavedConnection | null {
  if (!entry || typeof entry !== "object") {
    return null;
  }

  const candidate = entry as SavedConnection;
  const name = typeof candidate.name === "string" ? candidate.name.trim() : "";
  const url = typeof candidate.url === "string" ? candidate.url.trim() : "";
  const type = typeof candidate.type === "string" ? candidate.type.trim() : undefined;
  const databaseName = typeof candidate.databaseName === "string" ? candidate.databaseName.trim() : undefined;

  if (!name || !url) {
    return null;
  }

  return {
    name,
    url,
    ...(type ? { type } : {}),
    ...(databaseName ? { databaseName } : {}),
  };
}

export function getSavedConnections(): SavedConnection[] {
  // Read only the current user's saved connections so account switches in the same browser do not leak entries.
  if (!canUseLocalStorage() && !canUseSessionStorage()) {
    return [];
  }

  const storageKey = getSavedConnectionsStorageKey();
  if (!storageKey) {
    return [];
  }

  const localConnections = readSavedConnectionsFromStorage(
    canUseLocalStorage() ? window.localStorage : null,
    storageKey,
  );
  if (localConnections !== null) {
    return localConnections;
  }

  const sessionConnections = readSavedConnectionsFromStorage(
    canUseSessionStorage() ? window.sessionStorage : null,
    storageKey,
  );
  if (sessionConnections !== null) {
    // Migrate existing session-only entries so saved connections remain available after reopen/reload.
    writeSavedConnectionsToStorage(storageKey, sessionConnections);
    return sessionConnections;
  }

  return [];
}

export function setSavedConnections(connections: SavedConnection[]) {
  // Persist per-user connections in durable browser storage so they do not disappear after the session-only cache is lost.
  if (!canUseLocalStorage() && !canUseSessionStorage()) {
    return;
  }

  const storageKey = getSavedConnectionsStorageKey();
  if (!storageKey) {
    return;
  }

  writeSavedConnectionsToStorage(storageKey, connections);
}

export function saveConnection(connection: SavedConnection) {
  // Deduplicate by URL while letting the latest successful connection refresh the saved label and metadata.
  const normalizedConnection = normalizeSavedConnection(connection);
  if (!normalizedConnection) {
    return;
  }

  const existingConnections = getSavedConnections().filter((entry) => entry.url !== normalizedConnection.url);
  setSavedConnections([normalizedConnection, ...existingConnections]);
}

export function removeSavedConnection(url: string) {
  // Delete one saved entry without disturbing the rest of the quick-connect list.
  const nextConnections = getSavedConnections().filter((entry) => entry.url !== url);
  setSavedConnections(nextConnections);
}

export function buildSavedConnectionName(
  connectionUrl: string,
  sourceType: string,
  preferredName?: string | null,
  databaseName?: string | null,
) {
  // Build a generic label from the connector metadata or URL without exposing the raw credentials as the display name.
  const cleanedPreferredName = (preferredName || "").trim();
  if (cleanedPreferredName) {
    return cleanedPreferredName;
  }

  const cleanedDatabaseName = (databaseName || "").trim();
  if (cleanedDatabaseName) {
    return cleanedDatabaseName;
  }

  try {
    const parsed = new URL(connectionUrl);
    const pathName = parsed.pathname.replace(/^\/+/, "").split("/").filter(Boolean).pop();
    if (pathName) {
      return pathName;
    }
    if (parsed.hostname) {
      return parsed.hostname;
    }
  } catch {
    // Ignore parse failures and fall back to the connector type label below.
  }

  const normalizedType = sourceType.replace(/[_-]+/g, " ").trim();
  return normalizedType ? normalizedType.charAt(0).toUpperCase() + normalizedType.slice(1) : "Saved connection";
}
