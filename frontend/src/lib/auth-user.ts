export const AUTH_USER_STORAGE_KEY = "auth_user";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

function canUseLocalStorage() {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function normalizeAuthUser(value: unknown): AuthUser | null {
  if (!value || typeof value !== "object") {
    return null;
  }

  const candidate = value as Partial<AuthUser>;
  const id = typeof candidate.id === "string" ? candidate.id.trim() : "";
  const email = typeof candidate.email === "string" ? candidate.email.trim() : "";
  const name = typeof candidate.name === "string" ? candidate.name.trim() : "";

  if (!id || !email || !name) {
    return null;
  }

  return { id, email, name };
}

export function getStoredAuthUser(): AuthUser | null {
  if (!canUseLocalStorage()) {
    return null;
  }

  try {
    const rawValue = window.localStorage.getItem(AUTH_USER_STORAGE_KEY);
    if (!rawValue) {
      return null;
    }

    return normalizeAuthUser(JSON.parse(rawValue));
  } catch {
    return null;
  }
}

export function setStoredAuthUser(user: unknown) {
  if (!canUseLocalStorage()) {
    return;
  }

  const normalizedUser = normalizeAuthUser(user);
  if (!normalizedUser) {
    window.localStorage.removeItem(AUTH_USER_STORAGE_KEY);
    return;
  }

  window.localStorage.setItem(AUTH_USER_STORAGE_KEY, JSON.stringify(normalizedUser));
}

export function clearStoredAuthUser() {
  if (!canUseLocalStorage()) {
    return;
  }

  window.localStorage.removeItem(AUTH_USER_STORAGE_KEY);
}

export function getUserDisplayName(user: AuthUser | null | undefined) {
  const name = user?.name.trim();
  if (name) {
    return name;
  }

  const email = user?.email.trim();
  if (email) {
    return email;
  }

  return "You";
}

export function getUserInitials(user: AuthUser | null | undefined) {
  const cleanedName = user?.name.trim() || "";
  if (cleanedName) {
    const words = cleanedName.split(/\s+/).filter(Boolean);
    return words
      .slice(0, 2)
      .map((word) => word.charAt(0).toUpperCase())
      .join("");
  }

  const emailLocalPart = (user?.email.split("@")[0] || "").replace(/[^a-zA-Z0-9]/g, "");
  if (emailLocalPart) {
    return emailLocalPart.slice(0, 2).toUpperCase();
  }

  return "DS";
}
