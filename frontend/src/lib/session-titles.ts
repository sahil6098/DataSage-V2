const SESSION_TITLE_MAX_LENGTH = 96;

export function summarizeSessionTitle(message: string) {
  // Mirror the backend title logic so draft conversations show the first user sentence immediately.
  const normalized = message.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "New conversation";
  }

  const firstSentence = normalized.split(/(?<=[.!?])\s+/, 1)[0]?.replace(/[.!?]+$/, "").trim() || normalized;
  if (firstSentence.length <= SESSION_TITLE_MAX_LENGTH) {
    return firstSentence;
  }

  const truncated = firstSentence.slice(0, SESSION_TITLE_MAX_LENGTH - 3).trimEnd();
  const lastSpace = truncated.lastIndexOf(" ");
  const safeCut = lastSpace >= 48 ? truncated.slice(0, lastSpace) : truncated;
  return `${safeCut}...`;
}
