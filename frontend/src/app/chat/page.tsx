"use client";

import { startTransition, type FormEvent, type KeyboardEvent, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  Database,
  FileSpreadsheet,
  Menu,
  Send,
  Sparkles,
  UploadCloud,
  ArrowUp
} from "lucide-react";
import api from "@/lib/api";
import { getMessageBudgetState, MAX_MESSAGE_TOKENS } from "@/lib/message-budget";
import { useCurrentUser } from "@/lib/use-current-user";
import { toAppPath } from "@/lib/routes";
import { createSession } from "@/lib/sessions";
import { summarizeSessionTitle } from "@/lib/session-titles";
import AnimatedBackground from "@/components/AnimatedBackground";
import Sidebar from "@/components/Sidebar";

interface Session {
  id?: string;
  _id?: string;
  name?: string;
  title?: string;
}

export default function ChatDashboard() {
  const router = useRouter();
  const pathname = usePathname();
  const currentUser = useCurrentUser();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const messageBudget = getMessageBudgetState(input);

  useEffect(() => {
    const fetchSessions = async () => {
      try {
        const response = await api.get("/sessions");
        setSessions(response.data.data || []);
      } catch (error) {
        console.error(error);
      } finally {
        setLoading(false);
      }
    };

    fetchSessions();
  }, []);

  const createNewAndNavigate = async (prompt?: string) => {
    try {
      // Create a hidden draft session so the first sent prompt becomes the visible conversation.
      const sessionId = await createSession(
        prompt
          ? { draft: true, title: summarizeSessionTitle(prompt) }
          : { draft: true },
      );

      startTransition(() => {
        router.push(toAppPath(`/chat/${sessionId}${prompt ? `?prompt=${encodeURIComponent(prompt)}` : ""}`, pathname));
      });
    } catch (error) {
      console.error("Failed to create session", error);
    }
  };

  const createSessionAndOpenConnector = async (tab: "file" | "mongodb") => {
    try {
      // Use a hidden draft session so connectors and preview work before the first message is persisted.
      const sessionId = await createSession({ draft: true });
      startTransition(() => {
        router.push(toAppPath(`/chat/${sessionId}?connector=1&tab=${tab}`, pathname));
      });
    } catch (error) {
      console.error("Failed to create session for connector flow", error);
    }
  };

  const submitPrompt = async () => {
    if (!input.trim() || messageBudget.overLimit) {
      return;
    }

    await createNewAndNavigate(input.trim());
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await submitPrompt();
  };

  const handlePromptKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) {
      return;
    }

    event.preventDefault();
    void submitPrompt();
  };

  if (loading) {
    return (
      <main className="page-shell page-shell-animated">
        <AnimatedBackground />
        <div className="app-layout">
          <div className="content-shell" style={{ paddingLeft: 20 }}>
            <section className="chat-panel">
              <div className="chat-body">
                <div className="chat-body-inner">
                  <div className="loading-shell">
                    <div className="loading-line short" />
                    <div className="loading-line medium" />
                    <div className="loading-line" />
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </main>
    );
  }

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
                  <h2>Analysis workspace</h2>

                </div>
              </div>
              <button type="button" className="status-pill warning" onClick={() => createSessionAndOpenConnector("mongodb")}>
                <Database size={16} />
                Connect a source
              </button>
            </header>

            <div className="chat-body">
              <div className="chat-body-inner">
                <section className="dashboard-intro">
                  <div className="brand-row">
                    <span className="brand-mark">
                      <Sparkles size={18} />
                    </span>
                    DataSage workspace
                  </div>
                  <h1 className="dashboard-title">
                    What do you want to <span className="display-gradient">analyze today</span>?
                  </h1>
                  <p className="dashboard-subtitle">
                    Start with a natural-language question, connect a live database, or upload a dataset and let
                    the assistant shape the next step into tables, insights, and polished visualizations.
                  </p>
                </section>

                <section className="dashboard-card">
                  <div className="input-shell">
                    <form className="prompt-form" onSubmit={handleSubmit}>
                      <textarea
                        className="prompt-textarea"
                        placeholder="Ask about revenue trends, request a dashboard, compare segments, or describe the visualization you want..."
                        value={input}
                        onChange={(event) => setInput(event.target.value)}
                        onKeyDown={handlePromptKeyDown}
                      />

                      <div className="composer-footer">
                        <div className="composer-actions">
                          <button type="button" className="action-chip cursor-database" onClick={() => createSessionAndOpenConnector("mongodb")}>
                            <span className="action-chip-glow" />
                            <span className="action-chip-icon">
                              <Database size={14} />
                            </span>
                            <span className="action-chip-copy">Connect data</span>
                          </button>
                          <button type="button" className="action-chip cursor-upload" onClick={() => createSessionAndOpenConnector("file")}>
                            <span className="action-chip-glow" />
                            <span className="action-chip-icon">
                              <UploadCloud size={14} />
                            </span>
                            <span className="action-chip-copy">Upload file</span>
                          </button>
                          <span className={`message-budget-pill ${messageBudget.overLimit ? "over-limit" : ""}`}>
                            Message budget {messageBudget.estimatedTokens}/{MAX_MESSAGE_TOKENS} tokens
                          </span>
                        </div>

                        <button
                          type="submit"
                          className="icon-button"
                          disabled={!input.trim() || messageBudget.overLimit}
                          aria-label="Send prompt"
                        >
                          <ArrowUp strokeWidth={3} size={22} />
                        </button>
                      </div>
                    </form>
                  </div>
                </section>

              </div>
            </div>
          </section>
        </div>
      </div>

    </main>
  );
}
