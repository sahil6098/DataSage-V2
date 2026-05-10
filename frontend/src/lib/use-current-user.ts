"use client";

import { useEffect, useState } from "react";
import api from "@/lib/api";
import { clearStoredAuthUser, getStoredAuthUser, setStoredAuthUser, type AuthUser } from "@/lib/auth-user";

export function useCurrentUser() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const accessToken = typeof window !== "undefined" ? window.localStorage.getItem("access_token") : null;
    if (!accessToken) {
      clearStoredAuthUser();
      setCurrentUser(null);
      return;
    }

    const storedUser = getStoredAuthUser();
    if (storedUser) {
      setCurrentUser(storedUser);
    }

    let cancelled = false;

    const syncCurrentUser = async () => {
      try {
        const response = await api.get("/auth/me");
        const nextUser = response.data?.data ?? null;
        setStoredAuthUser(nextUser);
        if (!cancelled) {
          setCurrentUser(getStoredAuthUser());
        }
      } catch {
        if (!cancelled && !storedUser) {
          setCurrentUser(null);
        }
      }
    };

    void syncCurrentUser();

    return () => {
      cancelled = true;
    };
  }, []);

  return currentUser;
}
