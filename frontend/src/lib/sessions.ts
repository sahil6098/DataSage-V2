import api from "@/lib/api";

interface SessionLike {
  id?: string;
  _id?: string;
}

interface CreateSessionOptions {
  title?: string;
  draft?: boolean;
}

export function getSessionId(session: SessionLike | null | undefined) {
  return session?.id || session?._id || null;
}

export async function createSession(options: CreateSessionOptions = {}) {
  // Allow callers to create hidden draft sessions for connector setup before the first message is persisted.
  const response = await api.post("/sessions", options);
  const sessionId = getSessionId(response.data?.data);

  if (!sessionId) {
    throw new Error("Session creation returned no id.");
  }

  return sessionId;
}
