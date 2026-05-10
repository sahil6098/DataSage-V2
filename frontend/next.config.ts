import type { NextConfig } from "next";

const backendOrigin = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/+$/, "");

if (process.env.NODE_ENV !== "test") {
  console.log(`[next.config] Proxying /api/* to ${backendOrigin}`);
}

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
