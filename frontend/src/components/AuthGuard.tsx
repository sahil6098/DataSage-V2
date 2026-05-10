"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { toAppPath } from "@/lib/routes";

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
    if (!token) {
      router.replace(toAppPath("/login", pathname));
    }
  }, [pathname, router]);

  return <>{children}</>;
}
