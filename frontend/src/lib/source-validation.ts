export interface SourceValidationResult {
  ok: boolean;
  message?: string;
}

function isPrivateHost(hostname: string) {
  const normalized = hostname.trim().toLowerCase();
  if (!normalized) {
    return true;
  }

  if (normalized === "localhost" || normalized === "127.0.0.1" || normalized === "::1" || normalized.endsWith(".local")) {
    return true;
  }

  return /^(10\.|127\.|172\.(1[6-9]|2\d|3[0-1])\.|192\.168\.)/.test(normalized);
}

export function validateSourceConnectionUri(
  sourceType: "mongodb" | "postgresql",
  connectionUri: string,
  databaseName?: string,
): SourceValidationResult {
  const trimmed = connectionUri.trim();
  if (!trimmed) {
    return { ok: false, message: "Enter a connection URI before connecting." };
  }

  try {
    const parsed = new URL(trimmed);
    const hostname = parsed.hostname || "";
    if (isPrivateHost(hostname)) {
      return { ok: false, message: "Private or localhost database hosts are not allowed." };
    }

    if (sourceType === "mongodb") {
      if (!["mongodb:", "mongodb+srv:"].includes(parsed.protocol)) {
        return { ok: false, message: "MongoDB Atlas URLs must start with mongodb+srv:// or mongodb://." };
      }
      if (!hostname.includes("mongodb.net")) {
        return { ok: false, message: "Only MongoDB Atlas hosts are supported for MongoDB connections." };
      }
      if (!parsed.username || !parsed.password) {
        return { ok: false, message: "MongoDB Atlas URLs must include both username and password." };
      }
      if (!parsed.pathname.replace(/^\/+/, "") && !databaseName?.trim()) {
        return { ok: false, message: "Enter the MongoDB database name for Atlas quick connect." };
      }
      return { ok: true };
    }

    if (!["postgresql:", "postgres:"].includes(parsed.protocol)) {
      return { ok: false, message: "Supabase URLs must start with postgresql://." };
    }
    if (!hostname.includes("supabase")) {
      return { ok: false, message: "Only Supabase PostgreSQL hosts are supported for PostgreSQL connections." };
    }
    if (!parsed.username || !parsed.password) {
      return { ok: false, message: "Supabase URLs must include both username and password." };
    }
    if (!parsed.pathname.replace(/^\/+/, "")) {
      return { ok: false, message: "Supabase URLs must include the database name in the path." };
    }
    return { ok: true };
  } catch {
    return { ok: false, message: "The connection URI format looks invalid." };
  }
}
