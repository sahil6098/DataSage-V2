import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DataSage AI",
  description: "Animated AI analyst workspace for chat, connectors, and visual insights.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" data-scroll-behavior="smooth">
      <body>{children}</body>
    </html>
  );
}
