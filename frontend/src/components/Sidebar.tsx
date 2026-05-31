"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, Clock, LogOut, MessageSquarePlus, Sparkles, Star, Trash2, X } from "lucide-react";
import { BrandLogoIcon } from "@/components/BrandLogo";
import api from "@/lib/api";
import { clearStoredAuthUser, getUserDisplayName, getUserInitials, type AuthUser } from "@/lib/auth-user";
import { toAppPath } from "@/lib/routes";
import { createSession } from "@/lib/sessions";

interface Session {
  id?: string;
  _id?: string;
  name?: string;
  title?: string;
}

interface HistoryItem {
  id: string;
  session_id: string;
  question: string;
  is_favorite: boolean;
}

interface SidebarProps {
  sessions: Session[];
  currentUser?: AuthUser | null;
  isOpen?: boolean;
  onClose?: () => void;
  onSessionDeleted?: (sessionId: string) => void;
}

export default function Sidebar({ sessions, currentUser = null, isOpen = true, onClose, onSessionDeleted }: SidebarProps) {
  const router = useRouter();
  const pathname = usePathname();
  const userDisplayName = getUserDisplayName(currentUser);
  const userSubtitle =
    currentUser?.name?.trim() && currentUser?.email?.trim() ? currentUser.email.trim() : "Authenticated session";

  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  const normalizedSessions = sessions
    .map((session, index) => {
      const sessionId = session.id || session._id;
      if (!sessionId) return null;
      return { sessionId, title: session.name || session.title || `Analysis ${index + 1}`, index };
    })
    .filter((s): s is { sessionId: string; title: string; index: number } => Boolean(s));

  const fetchHistory = useCallback(async () => {
    try {
      const res = await api.get("/history");
      setHistory(res.data.data || []);
    } catch {
      // silently ignore if history fetch fails
    }
  }, []);

  useEffect(() => {
    if (showHistory) void fetchHistory();
  }, [showHistory, fetchHistory]);

  const logout = () => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    clearStoredAuthUser();
    router.push(toAppPath("/login", pathname));
  };

  const handleNewChat = async () => {
    try {
      const sessionId = await createSession({ draft: true });
      router.push(toAppPath(`/chat/${sessionId}`, pathname));
      onClose?.();
    } catch (error) {
      console.error("Failed to open a new analysis chat", error);
    }
  };

  const handleDeleteSession = async (sessionId: string, event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    try {
      await api.delete(`/sessions/${sessionId}`);
      onSessionDeleted?.(sessionId);
      const deletedPath = toAppPath(`/chat/${sessionId}`, pathname);
      if (pathname === deletedPath) router.push(toAppPath("/chat", pathname));
    } catch (error) {
      console.error("Failed to delete session", error);
    }
  };

  const handleToggleFavorite = async (item: HistoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.post(`/history/${item.id}/favorite`);
      setHistory((prev) => prev.map((h) => (h.id === item.id ? { ...h, is_favorite: !h.is_favorite } : h)));
    } catch { /* ignore */ }
  };

  const handleDeleteHistory = async (item: HistoryItem, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.delete(`/history/${item.id}`);
      setHistory((prev) => prev.filter((h) => h.id !== item.id));
    } catch { /* ignore */ }
  };

  const handleReuseQuery = async (item: HistoryItem) => {
    try {
      const sessionId = item.session_id || (await createSession({ draft: true }));
      router.push(toAppPath(`/chat/${sessionId}`, pathname));
      onClose?.();
    } catch { /* ignore */ }
  };

  const favorites = history.filter((h) => h.is_favorite);
  const recent = history.filter((h) => !h.is_favorite).slice(0, 10);

  return (
    <aside className={`sidebar-panel ${isOpen ? "open" : ""}`}>
      <div className="sidebar-top">
        <Link href={toAppPath("/chat", pathname)} className="brand-row">
          <span className="brand-mark"><BrandLogoIcon size={18} /></span>
          DataSage
        </Link>
        <button type="button" className="btn-ghost mobile-sidebar-toggle" onClick={onClose} aria-label="Close sidebar">
          <X size={18} />
        </button>
      </div>

      <button type="button" className="btn-primary" onClick={() => void handleNewChat()}>
        <MessageSquarePlus size={18} />
        New analysis
      </button>

      <div className="info-banner" style={{ marginTop: 0 }}>
        <Sparkles size={18} />
        Smooth workspace for questions, uploads, connectors, and visual answers.
      </div>

      <div className="sidebar-scroll">
        <div className="sidebar-section-title">Recent chats</div>
        <div className="session-list">
          {normalizedSessions.length === 0 ? (
            <div className="empty-copy" style={{ padding: "14px 8px" }}>Your new sessions will appear here.</div>
          ) : (
            normalizedSessions.map((session) => {
              const sessionPath = toAppPath(`/chat/${session.sessionId}`, pathname);
              const active = pathname === sessionPath;
              return (
                <div key={session.sessionId} className="session-item-wrap">
                  <Link href={sessionPath} className={`session-link ${active ? "active" : ""}`} onClick={() => onClose?.()}>
                    <span className="avatar" style={{ width: 38, height: 38, borderRadius: "50%" }}>
                      {String(session.index + 1).padStart(2, "0")}
                    </span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <strong>{session.title}</strong>
                      <span>{session.sessionId.slice(0, 8)}</span>
                    </div>
                    <ChevronRight size={16} className="session-chevron" />
                  </Link>
                  <button type="button" className="session-delete-btn" aria-label="Delete session"
                    onClick={(e) => void handleDeleteSession(session.sessionId, e)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              );
            })
          )}
        </div>

        {/* ── Query History ── */}
        <button type="button" className="sidebar-section-title sidebar-history-toggle"
          onClick={() => setShowHistory((v) => !v)}
          style={{ width: "100%", textAlign: "left", cursor: "pointer", background: "none", border: "none", padding: 0 }}>
          <Clock size={13} style={{ marginRight: 6, verticalAlign: "middle" }} />
          Query history {showHistory ? "▲" : "▼"}
        </button>

        {showHistory && (
          <div className="query-history-section">
            {favorites.length > 0 && (
              <>
                <div className="query-history-group-label">⭐ Favorites</div>
                {favorites.map((item) => (
                  <div key={item.id} className="query-history-item" onClick={() => void handleReuseQuery(item)}>
                    <span className="query-history-text" title={item.question}>
                      {item.question.length > 60 ? item.question.slice(0, 60) + "…" : item.question}
                    </span>
                    <span className="query-history-actions">
                      <button type="button" className="query-history-fav active"
                        onClick={(e) => void handleToggleFavorite(item, e)} title="Unfavorite">
                        <Star size={12} fill="currentColor" />
                      </button>
                      <button type="button" className="query-history-del"
                        onClick={(e) => void handleDeleteHistory(item, e)} title="Delete">
                        <Trash2 size={12} />
                      </button>
                    </span>
                  </div>
                ))}
              </>
            )}
            {recent.length > 0 && (
              <>
                <div className="query-history-group-label">Recent</div>
                {recent.map((item) => (
                  <div key={item.id} className="query-history-item" onClick={() => void handleReuseQuery(item)}>
                    <span className="query-history-text" title={item.question}>
                      {item.question.length > 60 ? item.question.slice(0, 60) + "…" : item.question}
                    </span>
                    <span className="query-history-actions">
                      <button type="button" className="query-history-fav"
                        onClick={(e) => void handleToggleFavorite(item, e)} title="Favorite">
                        <Star size={12} />
                      </button>
                      <button type="button" className="query-history-del"
                        onClick={(e) => void handleDeleteHistory(item, e)} title="Delete">
                        <Trash2 size={12} />
                      </button>
                    </span>
                  </div>
                ))}
              </>
            )}
            {favorites.length === 0 && recent.length === 0 && (
              <div className="empty-copy" style={{ padding: "10px 8px", fontSize: 13 }}>
                Your analyzed questions will appear here.
              </div>
            )}
          </div>
        )}
      </div>

      <div className="sidebar-footer">
        <div className="sidebar-user">
          <span className="avatar">{getUserInitials(currentUser)}</span>
          <div>
            <strong style={{ display: "block" }}>{currentUser ? userDisplayName : "Workspace ready"}</strong>
            <span className="message-time">{currentUser ? userSubtitle : "Authenticated session"}</span>
          </div>
        </div>
        <button type="button" className="btn-secondary btn-logout" onClick={logout}>
          <LogOut size={18} />
          Logout
        </button>
      </div>
    </aside>
  );
}
