"use client";

import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, BarChart3, Check, ChevronDown, Database, FileSpreadsheet, FileText, Menu, PlugZap, Sparkles, Unplug, Zap, UploadCloud, ArrowUp } from "lucide-react";
import api, { refreshAccessToken } from "@/lib/api";
import { API_BASE_PATH } from "@/lib/api-base";
import { getUserDisplayName } from "@/lib/auth-user";
import { toAppPath } from "@/lib/routes";
import { useCurrentUser } from "@/lib/use-current-user";
import { getMessageBudgetState, MAX_MESSAGE_TOKENS } from "@/lib/message-budget";
import AnimatedBackground from "@/components/AnimatedBackground";
import Sidebar from "@/components/Sidebar";
import ChatMessage from "@/components/ChatMessage";
import ConnectorModal from "@/components/ConnectorModal";
import DataSourcePreview, { type ConnectedSourceConfig } from "@/components/DataSourcePreview";

const API = API_BASE_PATH;
const MODEL_STORAGE_KEY = "llm_provider";
const PENDING_PROMPT_STORAGE_PREFIX = "datasage_pending_prompt:";
const STREAM_FRAME_MS = 16;
const MIN_REPORT_USER_MESSAGES = 4;

type LlmProvider = "groq" | "deepseek";

interface Message {
  role: string;
  content: string;
  viz_data?: string;
  status?: "streaming" | "complete";
  stage_label?: string;
}

interface StreamFinalPayload {
  message?: string;
  viz_data?: string;
}

interface SessionResponse {
  messages?: Message[];
  data_source?: ConnectedSourceConfig | null;
}

interface Session {
  id?: string;
  _id?: string;
  name?: string;
  title?: string;
}

async function fetchSessionsList() {
  // Reuse one sidebar loader so first-message draft sessions appear as soon as the backend promotes them.
  const response = await api.get("/sessions");
  return response.data.data || [];
}

function isConnectorErrorPayload(payload: unknown) {
  if (!payload || typeof payload !== "object") {
    return false;
  }

  const candidate = payload as { error_code?: unknown; message?: unknown };
  const errorCode = typeof candidate.error_code === "string" ? candidate.error_code.toUpperCase() : "";
  if (errorCode === "CONNECTOR_ERROR" || errorCode === "NO_CONNECTION") {
    return true;
  }

  const message = typeof candidate.message === "string" ? candidate.message.toLowerCase() : "";
  return message.includes("no data source connected") || message.includes("no active connection");
}

function isConnectorErrorMessage(message: string | null | undefined) {
  const normalized = (message || "").toLowerCase();
  return normalized.includes("no data source connected") || normalized.includes("no active connection");
}

function formatProviderLabel(provider: LlmProvider) {
  if (provider === "deepseek") return "DeepSeek";
  return "Groq";
}

function formatSourceTitle(sourceConfig: ConnectedSourceConfig | null) {
  return sourceConfig?.file_name || sourceConfig?.database_name || "Connected source";
}

function formatSourceSubtitle(sourceConfig: ConnectedSourceConfig | null) {
  const sourceType = (sourceConfig?.type || "").toLowerCase();
  if (sourceConfig?.file_name) {
    return sourceType === "excel" ? "Spreadsheet attached" : "File attached";
  }

  if (sourceConfig?.database_name) {
    switch (sourceType) {
      case "mongodb":
        return "MongoDB database";
      case "postgresql":
        return "PostgreSQL database";
      case "mysql":
        return "MySQL database";
      default:
        return "Database connected";
    }
  }

  return "Source connected";
}

export default function ChatSessionPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentUser = useCurrentUser();
  const endOfMessagesRef = useRef<HTMLDivElement>(null);
  const pendingInitialPromptSentRef = useRef(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [sourceConfig, setSourceConfig] = useState<ConnectedSourceConfig | null>(null);
  const [previewRefreshToken, setPreviewRefreshToken] = useState(0);
  const [connectorModalMode, setConnectorModalMode] = useState<"all" | "database" | "file">("all");
  const [llmProvider, setLlmProvider] = useState<LlmProvider>("groq");
  const [disconnecting, setDisconnecting] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [modelMenuOpen, setModelMenuOpen] = useState(false);
  const modelMenuRef = useRef<HTMLDivElement>(null);
  const messageBudget = getMessageBudgetState(input);
  const userMessageCount = messages.filter((message) => message.role === "user").length;
  // serverMessageCount = null means session hasn't loaded yet.
  // serverMessageCount = 0 means it's a brand-new session → enforce 4-message minimum.
  // serverMessageCount > 0 means existing session → always allow report if ≥4 total messages.
  const [serverMessageCount, setServerMessageCount] = useState<number | null>(null);
  const effectiveCount = serverMessageCount !== null && serverMessageCount > 0
    ? Math.max(serverMessageCount, userMessageCount)   // old session: credit existing messages
    : userMessageCount;                                 // new session: count only current messages
  const canGenerateReport = effectiveCount >= MIN_REPORT_USER_MESSAGES;
  const reportDisabled = reportLoading || loading || !canGenerateReport;
  const reportTitle = canGenerateReport
    ? "Generate report PDF"
    : `Send ${MIN_REPORT_USER_MESSAGES - effectiveCount} more message${
        MIN_REPORT_USER_MESSAGES - effectiveCount === 1 ? "" : "s"
      } to generate a report`;

  const markConnectionInactive = () => {
    setIsConnected(false);
    setPreviewOpen(false);
    setSourceConfig(null);
    setPreviewRefreshToken((currentToken) => currentToken + 1);
  };

  useEffect(() => {
    const savedProvider = typeof window !== "undefined" ? window.localStorage.getItem(MODEL_STORAGE_KEY) : null;
    if (savedProvider === "groq") {
      setLlmProvider(savedProvider);
    } else if (typeof window !== "undefined") {
      window.localStorage.setItem(MODEL_STORAGE_KEY, "groq");
      setLlmProvider("groq");
    }
  }, []);

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        setSessions(await fetchSessionsList());
      } catch (error) {
        console.error(error);
      }
    };

    fetchSessions();
  }, []);

  useEffect(() => {
    pendingInitialPromptSentRef.current = false;
    setServerMessageCount(null);

    const fetchSession = async () => {
      try {
        const response = await api.get(`/sessions/${sessionId}`);
        const session: SessionResponse = response.data.data;
        const loadedMessages: Message[] = (session.messages || []).map((message) => ({ ...message, status: "complete" as const, stage_label: undefined }));
        setMessages(loadedMessages);
        setServerMessageCount(loadedMessages.filter((m) => m.role === "user").length);
        const nextSource = session.data_source || null;
        setSourceConfig(nextSource);
        setIsConnected(false);

        if (nextSource) {
          try {
            await api.get(`/connectors/${sessionId}/schema`);
            setIsConnected(true);
          } catch {
            markConnectionInactive();
          }
        }
      } catch (error) {
        console.error(error);
      }
    };

    if (sessionId) {
      fetchSession();
    }
  }, [sessionId]);

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }

    event.preventDefault();
    if (!loading && input.trim()) {
      void sendMessage();
    }
  };

  const sendMessage = async (messageText?: string) => {
    const content = (messageText ?? input).trim();
    if (!content) {
      return;
    }

    if (getMessageBudgetState(content).overLimit) {
      return;
    }

    const optimisticMessages = [...messages, { role: "user", content }];
    setMessages(optimisticMessages);
    if (!messageText) {
      setInput("");
    }
    setLoading(true);
    let stopActiveStreamTimer: (() => void) | null = null;

    try {
      const requestStream = (accessToken: string | null) =>
        fetch(`${API}/chat/${sessionId}/stream`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-LLM-Provider": llmProvider,
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify({ message: content, llm_provider: llmProvider }),
        });

      const readErrorResponse = async (response: Response) => {
        const rawBody = await response.text();
        if (!rawBody) {
          return { payload: null as unknown, message: null as string | null };
        }

        try {
          const payload = JSON.parse(rawBody) as unknown;
          const message =
            payload && typeof payload === "object" && "message" in payload
              ? (payload as { message?: string }).message || null
              : payload && typeof payload === "object" && "detail" in payload
                ? (payload as { detail?: string }).detail || null
                : null;
          return { payload, message };
        } catch {
          return { payload: rawBody, message: rawBody.trim() || null };
        }
      };

      let token = localStorage.getItem("access_token");
      let response = await requestStream(token);
      if (response.status === 401) {
        token = await refreshAccessToken();
        response = await requestStream(token);
      }

      if (!response.ok || !response.body) {
        const { payload: serverPayload, message: errorBody } = await readErrorResponse(response);

        if (isConnectorErrorPayload(serverPayload)) {
          markConnectionInactive();
        }

        throw new Error(errorBody || "Streaming request failed.");
      }

      setMessages([
        ...optimisticMessages,
        { role: "assistant", content: "", status: "streaming", stage_label: "Thinking" },
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let receivedFinal = false;
      let queuedStreamText = "";
      let streamedAssistantText = "";
      let streamRafId: number | null = null;
      let lastFrameAt = 0;
      let streamFlushResolver: (() => void) | null = null;
      let finalPayload: StreamFinalPayload | null = null;

      const applyAssistantUpdate = (updater: (current: Message) => Message) => {
        setMessages((currentMessages) => {
          if (!currentMessages.length) {
            return currentMessages;
          }
          const nextMessages = [...currentMessages];
          const lastIndex = nextMessages.length - 1;
          const lastMessage = nextMessages[lastIndex];
          if (lastMessage.role !== "assistant") {
            return currentMessages;
          }
          nextMessages[lastIndex] = updater(lastMessage);
          return nextMessages;
        });
      };

      const stopStreamTimer = () => {
        if (streamRafId) {
          window.cancelAnimationFrame(streamRafId);
          streamRafId = null;
        }
      };
      stopActiveStreamTimer = stopStreamTimer;

      const resolveStreamFlush = () => {
        if (!queuedStreamText && !streamRafId && streamFlushResolver) {
          streamFlushResolver();
          streamFlushResolver = null;
        }
      };

      const flushQueuedStreamText = (force = false) => {
        if (!queuedStreamText) {
          stopStreamTimer();
          resolveStreamFlush();
          return;
        }

        const chunkToApply = queuedStreamText;
        queuedStreamText = "";
        streamedAssistantText += chunkToApply;
        applyAssistantUpdate((current) => ({
          ...current,
          status: "streaming",
          content: `${current.content}${chunkToApply}`,
        }));

        if (force) {
          stopStreamTimer();
          resolveStreamFlush();
        }
      };

      const runFrameFlush = (timestamp: number) => {
        if (!queuedStreamText) {
          streamRafId = null;
          resolveStreamFlush();
          return;
        }

        if (timestamp - lastFrameAt < STREAM_FRAME_MS) {
          streamRafId = window.requestAnimationFrame(runFrameFlush);
          return;
        }

        lastFrameAt = timestamp;
        flushQueuedStreamText();
        streamRafId = queuedStreamText ? window.requestAnimationFrame(runFrameFlush) : null;
      };

      const startStreamTimer = () => {
        if (!streamRafId) {
          streamRafId = window.requestAnimationFrame(runFrameFlush);
        }
      };

      const queueAssistantText = (nextText: string) => {
        if (!nextText) {
          return;
        }
        queuedStreamText += nextText;
        startStreamTimer();
      };

      const waitForQueuedStreamText = () => {
        if (!queuedStreamText && !streamRafId) {
          return Promise.resolve();
        }
        return new Promise<void>((resolve) => {
          streamFlushResolver = resolve;
        });
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const event of events) {
          const dataLine = event
            .split("\n")
            .find((line) => line.startsWith("data: "));

          if (!dataLine) {
            continue;
          }

          const payload = JSON.parse(dataLine.slice(6));

          if (payload.type === "chunk") {
            const chunkContent = typeof payload.content === "string" ? payload.content : "";
            if (chunkContent) {
              queueAssistantText(chunkContent);
            }
          }

          if (payload.type === "stage") {
            const stageLabel = typeof payload.label === "string" && payload.label.trim()
              ? payload.label.trim()
              : "Generating insight";
            applyAssistantUpdate((current) => ({
              ...current,
              status: "streaming",
              stage_label: stageLabel,
            }));
          }

          if (payload.type === "final") {
            receivedFinal = true;
            finalPayload = (payload.payload || {}) as StreamFinalPayload;
          }

          if (payload.type === "error") {
            queuedStreamText = "";
            stopStreamTimer();
            if (isConnectorErrorMessage(payload.message)) {
              markConnectionInactive();
            }
            applyAssistantUpdate(() => ({
              role: "assistant",
              content: payload.message || "An error occurred while generating the response.",
              status: "complete",
              stage_label: undefined,
            }));
          }
        }
      }

      if (finalPayload) {
        const finalMessage = finalPayload.message || "";
        const renderedAssistantText = `${streamedAssistantText}${queuedStreamText}`;
        const missingFinalText = finalMessage.startsWith(renderedAssistantText)
          ? finalMessage.slice(renderedAssistantText.length)
          : "";

        if (missingFinalText) {
          queueAssistantText(missingFinalText);
        }

        flushQueuedStreamText(true);
        await waitForQueuedStreamText();
        applyAssistantUpdate((current) => ({
          role: "assistant",
          content: finalMessage || current.content,
          viz_data: finalPayload?.viz_data,
          status: "complete",
          stage_label: undefined,
        }));
      } else if (streamedAssistantText || queuedStreamText) {
        flushQueuedStreamText(true);
        await waitForQueuedStreamText();
        applyAssistantUpdate((current) => ({
          ...current,
          status: "complete",
          stage_label: undefined,
        }));
      }

      // Refresh the sidebar after a completed turn so newly promoted draft sessions become visible and active.
      if (receivedFinal) {
        try {
          setSessions(await fetchSessionsList());
        } catch (refreshError) {
          console.error("Failed to refresh sessions after sending a message", refreshError);
        }
      }
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : "An error occurred while generating the response.";
      setMessages([
        ...optimisticMessages,
        { role: "assistant", content: message || "An error occurred.", status: "complete", stage_label: undefined },
      ]);
    } finally {
      stopActiveStreamTimer?.();
      setLoading(false);
    }
  };

  useEffect(() => {
    if (pendingInitialPromptSentRef.current || serverMessageCount === null || messages.length !== 0 || loading) {
      return;
    }

    const legacyPrompt = searchParams.get("prompt");
    const storageKey = `${PENDING_PROMPT_STORAGE_PREFIX}${sessionId}`;
    const storedPrompt = typeof window !== "undefined" ? window.sessionStorage.getItem(storageKey) : null;
    const initialPrompt = storedPrompt || legacyPrompt;

    if (!initialPrompt) {
      return;
    }

    pendingInitialPromptSentRef.current = true;
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem(storageKey);
    }
    if (legacyPrompt) {
      router.replace(toAppPath(`/chat/${sessionId}`, pathname));
    }
    void sendMessage(initialPrompt);
  }, [serverMessageCount, messages.length, loading, searchParams, sessionId, router, pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (searchParams.get("connector") === "1") {
      const modeFromUrl = searchParams.get("tab") === "file" ? "file" : "database";
      setConnectorModalMode(modeFromUrl);
      setIsModalOpen(true);
    }
  }, [searchParams]);

  useEffect(() => {
    if (!sourceConfig) {
      setPreviewOpen(false);
    }
  }, [sourceConfig]);

  useEffect(() => {
    if (!modelMenuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (!modelMenuRef.current?.contains(event.target as Node)) {
        setModelMenuOpen(false);
      }
    };

    const handleEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        setModelMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [modelMenuOpen]);

  const handleProviderChange = (provider: LlmProvider) => {
    setLlmProvider(provider);
    setModelMenuOpen(false);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(MODEL_STORAGE_KEY, provider);
    }
  };

  const handleDisconnectSource = async () => {
    if (!sessionId || disconnecting) {
      return;
    }

    try {
      setDisconnecting(true);
      await api.delete(`/connectors/${sessionId}/disconnect`);
      setIsConnected(false);
      setPreviewOpen(false);
      setSourceConfig(null);
      setPreviewRefreshToken((currentToken) => currentToken + 1);
    } catch (error) {
      console.error("Failed to disconnect source", error);
    } finally {
      setDisconnecting(false);
    }
  };

  const handleDownloadReport = async () => {
    if (!sessionId) return;

    // Bypass Next.js rewrite proxy — it times out on long-running requests (report takes 20-45s).
    const BACKEND = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

    try {
      setReportLoading(true);

      let token = localStorage.getItem("access_token");

      const doFetch = (t: string | null) =>
        fetch(`${BACKEND}/chat/${sessionId}/report`, {
          headers: t ? { Authorization: `Bearer ${t}` } : {},
        });

      let response = await doFetch(token);

      if (response.status === 401) {
        token = await refreshAccessToken();
        response = await doFetch(token);
      }

      if (!response.ok) {
        let errText = "Report generation failed.";
        try { errText = (await response.text()) || errText; } catch { /* ignore */ }
        throw new Error(errText);
      }

      const blob = await response.blob();
      const cd = response.headers.get("content-disposition") ?? "";
      const filename = cd.match(/filename="([^"]+)"/)?.[1] ?? "datasage-report.pdf";

      const href = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Delay revoke so browser has time to read the blob before it's freed
      setTimeout(() => window.URL.revokeObjectURL(href), 3000);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "Report generation failed.";
      setMessages((cur) => [
        ...cur,
        { role: "assistant", content: `⚠️ ${msg}`, status: "complete" as const, stage_label: undefined },
      ]);
    } finally {
      setReportLoading(false);
    }
  };

  const activeConnectorTab = searchParams.get("tab") === "file" ? "file" : "mongodb";
  const sourceConfigured = Boolean(sourceConfig);

  return (
    <main className="page-shell page-shell-animated">
      <AnimatedBackground />

      <div className="app-layout">
        <Sidebar
          sessions={sessions}
          currentUser={currentUser}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onSessionDeleted={(id) => setSessions((prev) => prev.filter((s) => (s.id ?? s._id) !== id))}
        />
        {sidebarOpen ? (
          <button
            type="button"
            className="sidebar-backdrop"
            onClick={() => setSidebarOpen(false)}
            aria-label="Close sidebar"
          />
        ) : null}

        <div className="content-shell">
          <div className="chat-workspace">
            <section className="chat-panel">
              <header className="chat-topbar">
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <button
                    type="button"
                    className="btn-secondary mobile-sidebar-toggle"
                    onClick={() => setSidebarOpen(true)}
                  >
                    <Menu size={18} />
                  </button>
                  <div>
                    <h2>Chat analysis</h2>

                  </div>
                </div>

                <div className="chat-topbar-actions">
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => void handleDownloadReport()}
                    disabled={reportDisabled}
                    title={reportTitle}
                  >
                    <FileText size={16} />
                    {reportLoading ? "Creating PDF" : "Generate report"}
                  </button>
                  {!sourceConfigured ? (
                    <button type="button" className="status-pill warning" onClick={() => { setConnectorModalMode("all"); setIsModalOpen(true); }}>
                      <AlertCircle size={16} />
                      Connect data first
                    </button>
                  ) : null}
                </div>
              </header>

              <div className="chat-body">
                <div className="chat-body-inner">
                  {messages.length === 0 ? (
                    <section className="empty-state">
                      <span className="empty-state-icon">
                        <Sparkles size={28} />
                      </span>
                      <div>
                        <h2 style={{ margin: 0, fontFamily: "var(--font-display)" }}>Ready for your first analysis</h2>
                        <p className="empty-copy" style={{ margin: "10px 0 0" }}>
                          Connect a source and ask for trends, anomalies, or a chart-driven summary.
                        </p>
                      </div>
                    </section>
                  ) : (
                    <div className="message-stack">
                      {messages.map((message, index) => (
                        <ChatMessage
                          key={`${message.role}-${index}`}
                          message={message}
                          userDisplayName={getUserDisplayName(currentUser)}
                        />
                      ))}
                    </div>
                  )}

                  <div ref={endOfMessagesRef} />
                </div>
              </div>

              <div className="chat-composer-wrap">
                <div className="chat-body-inner">
                  <div className="input-shell">
                    <form
                      className="prompt-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void sendMessage();
                      }}
                    >
                      <textarea
                        className="prompt-textarea"
                        placeholder="Ask about the connected data, request a chart, or describe the dashboard you want..."
                        value={input}
                        onChange={(event) => setInput(event.target.value)}
                        onKeyDown={handleComposerKeyDown}
                        disabled={loading}
                      />

                      <div className="composer-footer">
                        <div className="composer-actions">
                          {!sourceConfigured && (
                            <>
                              <button
                                type="button"
                                className="action-chip cursor-database"
                                onClick={() => { setConnectorModalMode("database"); setIsModalOpen(true); }}
                              >
                                <span className="action-chip-glow" />
                                <span className="action-chip-icon">
                                  <Database size={14} />
                                </span>
                                <span className="action-chip-copy">Connect data</span>
                              </button>
                              <button
                                type="button"
                                className="action-chip cursor-upload"
                                onClick={() => { setConnectorModalMode("file"); setIsModalOpen(true); }}
                              >
                                <span className="action-chip-glow" />
                                <span className="action-chip-icon">
                                  <UploadCloud size={14} />
                                </span>
                                <span className="action-chip-copy">Upload file</span>
                              </button>
                              <button
                                type="button"
                                className="action-chip cursor-report"
                                onClick={() => void handleDownloadReport()}
                                disabled={reportDisabled}
                                title={reportTitle}
                              >
                                <span className="action-chip-glow" />
                                <span className="action-chip-icon">
                                  <FileText size={14} />
                                </span>
                                <span className="action-chip-copy">Generate report</span>
                              </button>
                            </>
                          )}
                          {sourceConfigured ? (
                            <button
                              type="button"
                              className="composer-source-chip"
                              onClick={() => setPreviewOpen(true)}
                            >
                              <span className="composer-source-dot" />
                              <span className="composer-source-icon">
                                {sourceConfig?.file_name ? <FileSpreadsheet size={14} /> : <Database size={14} />}
                              </span>
                              <span className="composer-source-copy">
                                <span className="composer-source-label">{formatSourceSubtitle(sourceConfig)}</span>
                                <span className="composer-source-value">{formatSourceTitle(sourceConfig)}</span>
                              </span>
                            </button>
                          ) : null}
                          <div
                            ref={modelMenuRef}
                            className={`provider-menu-shell ${modelMenuOpen ? "open" : ""}`}
                          >
                            <button
                              type="button"
                              className="provider-chip"
                              onClick={() => setModelMenuOpen((current) => !current)}
                              aria-haspopup="menu"
                              aria-expanded={modelMenuOpen}
                              disabled={loading}
                            >
                              <span className="provider-chip-glow" />
                              <span className="provider-chip-icon">
                                <Zap size={14} />
                              </span>
                              <span className="provider-chip-copy">
                                <span className="provider-chip-label">Model</span>
                                <span className="provider-chip-value">{formatProviderLabel(llmProvider)}</span>
                              </span>
                              <span className={`provider-chip-caret ${modelMenuOpen ? "open" : ""}`}>
                                <ChevronDown size={16} />
                              </span>
                            </button>

                            <div className={`provider-menu ${modelMenuOpen ? "open" : ""}`} role="menu" aria-label="Select model">
                              {(["groq", "deepseek"] as LlmProvider[]).map((provider) => {
                                const active = provider === llmProvider;
                                const subtitle = provider === "deepseek"
                                  ? "DeepSeek via HuggingFace"
                                  : "Groq key-pool fallback";
                                return (
                                  <button
                                    key={provider}
                                    type="button"
                                    role="menuitemradio"
                                    aria-checked={active}
                                    className={`provider-option ${active ? "active" : ""}`}
                                    onClick={() => handleProviderChange(provider)}
                                  >
                                    <span className="provider-option-main">
                                      <span className={`provider-option-icon ${provider}`}>
                                        <Zap size={13} />
                                      </span>
                                      <span className="provider-option-copy">
                                        <span className="provider-option-title">{formatProviderLabel(provider)}</span>
                                        <span className="provider-option-subtitle">
                                          {subtitle}
                                        </span>
                                      </span>
                                    </span>
                                    {active ? <Check size={16} className="provider-option-check" /> : null}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        </div>

                        <button
                          type="submit"
                          className="icon-button send-btn"
                          disabled={loading || !input.trim()}
                          aria-label="Send message"
                        >
                          <ArrowUp strokeWidth={3} size={22} />
                        </button>
                      </div>
                    </form>
                  </div>
                </div>
              </div>
            </section>

            {sourceConfigured ? (
              <DataSourcePreview
                sessionId={sessionId}
                sourceConfig={sourceConfig}
                refreshToken={previewRefreshToken}
                isOpen={previewOpen}
                onClose={() => setPreviewOpen(false)}
                onConnectionStateChange={(active) => setIsConnected(active)}
              />
            ) : null}
          </div>
        </div>
      </div>

      {sourceConfigured && isConnected ? (
        <button
          type="button"
          className="floating-disconnect-button"
          onClick={() => {
            void handleDisconnectSource();
          }}
          disabled={disconnecting}
        >
          <span className="floating-disconnect-dot" aria-hidden="true" />
          <span className="floating-disconnect-copy">
            {formatSourceTitle(sourceConfig)} · {disconnecting ? "Disconnecting..." : "Disconnect"}
          </span>
          <Unplug size={14} />
        </button>
      ) : null}

      {isModalOpen ? (
        <ConnectorModal
          sessionId={sessionId}
          initialTab={connectorModalMode === "file" ? "file" : activeConnectorTab}
          mode={connectorModalMode}
          onClose={() => {
            setIsModalOpen(false);
            if (searchParams.get("connector") === "1") {
              router.replace(toAppPath(`/chat/${sessionId}`, pathname));
            }
          }}
          onConnect={(nextSource) => {
            setIsConnected(true);
            if (nextSource) {
              setSourceConfig(nextSource);
            }
            setPreviewRefreshToken((currentToken) => currentToken + 1);
            setPreviewOpen(true);
            setIsModalOpen(false);
            if (searchParams.get("connector") === "1") {
              router.replace(toAppPath(`/chat/${sessionId}`, pathname));
            }
          }}
        />
      ) : null}
    </main>
  );
}
