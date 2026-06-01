"use client";

import type React from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronRight, LogOut, MessageSquarePlus, Sparkles, Trash2, X } from "lucide-react";
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

  const normalizedSessions = sessions
    .map((session, index) => {
      const sessionId = session.id || session._id;
      if (!sessionId) return null;
      return { sessionId, title: session.name || session.title || `Analysis ${index + 1}`, index };
    })
    .filter((s): s is { sessionId: string; title: string; index: number } => Boolean(s));

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
                    </div>
                    <ChevronRight size={16} className="session-chevron" />
                  </Link>
                  <button
                    type="button"
                    className="session-delete-btn"
                    aria-label="Delete session"
                    onClick={(event) => void handleDeleteSession(session.sessionId, event)}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              );
            })
          )}
        </div>
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
