export const MAX_MESSAGE_TOKENS = 1200;

export function estimateMessageTokens(value: string) {
  const trimmed = value.trim();
  if (!trimmed) {
    return 0;
  }

  return Math.max(1, Math.ceil(trimmed.length / 4));
}

export function getMessageBudgetState(value: string) {
  const estimatedTokens = estimateMessageTokens(value);
  const remainingTokens = MAX_MESSAGE_TOKENS - estimatedTokens;
  return {
    estimatedTokens,
    remainingTokens,
    overLimit: estimatedTokens > MAX_MESSAGE_TOKENS,
  };
}
