"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight, BarChart3, Sparkles } from "lucide-react";
import { BrandLogoIcon } from "@/components/BrandLogo";
import AnimatedBackground from "@/components/AnimatedBackground";
import { toAppPath } from "@/lib/routes";

export default function HomePage() {
  const pathname = usePathname();

  return (
    <main className="page-shell page-shell-animated">
      <AnimatedBackground />

      <section className="hero-layout">
        <div className="hero-panel">
          <div className="brand-row">
            <span className="brand-mark">
              <BrandLogoIcon size={20} />
            </span>
            DataSage AI
          </div>

          <div className="eyebrow">
            <Sparkles size={16} />
            Light, animated workspace for live data exploration
          </div>

          <h1 className="display-title">
            Ask data questions in a <span className="display-gradient">beautiful flow</span>.
          </h1>

          <p className="hero-copy">
            Connect databases or files, move from login straight into a polished chatbot workspace,
            and get charts, tables, and guided analysis inside a smooth light-themed interface.
          </p>

          <div className="hero-actions">
            <Link href={toAppPath("/register", pathname)} className="btn-primary">
              Create account
              <ArrowRight size={18} />
            </Link>
            <Link href={toAppPath("/login", pathname)} className="btn-secondary">
              Sign in
            </Link>
          </div>

          <div className="hero-metrics">
            <div className="metric-card">
              <strong>1 flow</strong>
              <span>Login, connect data, chat, and visualize without context switching.</span>
            </div>
            <div className="metric-card">
              <strong>Live UI</strong>
              <span>Animated cards, floating gradients, and motion that feels purposeful.</span>
            </div>
            <div className="metric-card">
              <strong>Visual-ready</strong>
              <span>Smooth chart rendering and table fallback for every analysis response.</span>
            </div>
          </div>
        </div>

        <aside className="auth-card">
          <div className="brand-row">
            <span className="brand-mark">
              <BarChart3 size={20} />
            </span>
            Welcome
          </div>
          <h1>Start with the auth flow you described</h1>
          <p>
            Enter through login or register, then continue into a sidebar-based chat workspace inspired by
            modern AI products and tuned for your visualization experience.
          </p>

          <div className="field-stack">
            <Link href={toAppPath("/register", pathname)} className="btn-primary">
              Register and enter workspace
            </Link>
            <Link href={toAppPath("/login", pathname)} className="btn-secondary">
              Login to existing account
            </Link>
          </div>

          <div className="info-banner">
            <Sparkles size={18} />
            The frontend is set up so auth routes lead directly into the chat product experience.
          </div>
        </aside>
      </section>
    </main>
  );
}
