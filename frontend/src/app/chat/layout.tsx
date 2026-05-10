"use client";

import AuthGuard from "../../components/AuthGuard";

export default function ChatLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      {children}
    </AuthGuard>
  );
}
