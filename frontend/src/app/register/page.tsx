'use client';

import { startTransition, useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import axios from 'axios';
import { Eye, EyeOff } from 'lucide-react';
import { useRive } from '@rive-app/react-canvas';

import { API_BASE_PATH } from '@/lib/api-base';
import { setStoredAuthUser } from '@/lib/auth-user';
import { toAppPath } from '@/lib/routes';

const API = API_BASE_PATH;

// ─── Helpers ───────────────────────────────────────────────────────────────────

type Strength = 0 | 1 | 2 | 3;

function getStrength(pw: string): Strength {
  if (!pw.length) return 0;
  if (pw.length < 6) return 1;
  if (pw.length < 10 || !/[A-Z]/.test(pw) || !/[0-9]/.test(pw)) return 2;
  return 3;
}

const STRENGTH_LABEL = ['', 'Weak', 'Medium', 'Strong'] as const;
const STRENGTH_COLOR = ['', '#ef4444', '#f97316', '#22c55e'] as const;
const MAX_PASSWORD_LENGTH = 128;

function normalizeRegistrationError(message: string): string {
  if (message.toLowerCase().includes('72 bytes')) {
    return 'Password could not be processed by the server. Try again after restarting the backend with the latest code.';
  }
  return message;
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function Particles() {
  const configs = [
    { s: 32, l: '7%', d: '-1s', dur: '12s' },
    { s: 20, l: '22%', d: '-4s', dur: '14s' },
    { s: 46, l: '36%', d: '-7s', dur: '10s' },
    { s: 17, l: '50%', d: '-2s', dur: '15s' },
    { s: 36, l: '64%', d: '-5s', dur: '11s' },
    { s: 24, l: '77%', d: '-8s', dur: '13s' },
    { s: 40, l: '88%', d: '-3s', dur: '9s' },
    { s: 15, l: '55%', d: '-6.5s', dur: '16s' },
  ];
  return (
    <>
      {configs.map((c, i) => (
        <div
          key={i}
          className="rg-particle"
          style={{ width: c.s, height: c.s, left: c.l, animationDelay: c.d, animationDuration: c.dur }}
        />
      ))}
    </>
  );
}

import { BrandLogoIcon } from "@/components/BrandLogo";

function BrandIcon() {
  return <BrandLogoIcon size={18} />;
}

// ─── Data floating icons ──────────────────────────────────────────────────────

function DataIcons() {
  return (
    <>
      <svg style={{ position: 'absolute', width: 0, height: 0 }} aria-hidden="true">
        <defs>
          <linearGradient id="grad-db" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#4F46E5" />
            <stop offset="100%" stopColor="#E02FEF" />
          </linearGradient>
          <linearGradient id="grad-bar" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10B981" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id="grad-line" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F59E0B" />
            <stop offset="100%" stopColor="#EF4444" />
          </linearGradient>
          <linearGradient id="grad-pie" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#8B5CF6" />
            <stop offset="100%" stopColor="#14B8A6" />
          </linearGradient>
          <linearGradient id="grad-table" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F43F5E" />
            <stop offset="100%" stopColor="#9333EA" />
          </linearGradient>
          <linearGradient id="grad-scatter" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#14B8A6" />
            <stop offset="100%" stopColor="#EAB308" />
          </linearGradient>
          <linearGradient id="grad-nodes" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06B6D4" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id="grad-sql" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#EC4899" />
            <stop offset="100%" stopColor="#F59E0B" />
          </linearGradient>
          <linearGradient id="grad-cloud" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0EA5E9" />
            <stop offset="100%" stopColor="#6366F1" />
          </linearGradient>
          <linearGradient id="grad-gear" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F97316" />
            <stop offset="100%" stopColor="#EAB308" />
          </linearGradient>
          <linearGradient id="grad-brain" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#D946EF" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id="grad-search" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10B981" />
            <stop offset="100%" stopColor="#14B8A6" />
          </linearGradient>
        </defs>
      </svg>

      <div className="di di-db" style={{ filter: "drop-shadow(0 8px 16px rgba(224, 47, 239, 0.4)) drop-shadow(0 0 12px rgba(79, 70, 229, 0.5))" }}>
        <svg viewBox="0 0 40 44" fill="none" xmlns="http://www.w3.org/2000/svg">
          <ellipse cx="20" cy="9" rx="14" ry="5" stroke="url(#grad-db)" strokeWidth="2.5" />
          <path d="M6 9v9c0 2.76 6.27 5 14 5s14-2.24 14-5V9" stroke="url(#grad-db)" strokeWidth="2.5" />
          <path d="M6 18v9c0 2.76 6.27 5 14 5s14-2.24 14-5v-9" stroke="url(#grad-db)" strokeWidth="2.5" />
          <path d="M6 27v8c0 2.76 6.27 5 14 5s14-2.24 14-5v-8" stroke="url(#grad-db)" strokeWidth="2.5" />
        </svg>
      </div>
      <div className="di di-bar" style={{ filter: "drop-shadow(0 8px 16px rgba(16, 185, 129, 0.4)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))" }}>
        <svg viewBox="0 0 40 36" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="2" y="22" width="9" height="12" rx="2" fill="url(#grad-bar)" opacity="0.9" />
          <rect x="15" y="14" width="9" height="20" rx="2" fill="url(#grad-bar)" />
          <rect x="28" y="4" width="9" height="30" rx="2" fill="url(#grad-bar)" opacity="0.95" />
          <line x1="1" y1="35" x2="39" y2="35" stroke="url(#grad-bar)" strokeWidth="2" opacity="0.6" />
        </svg>
      </div>
      <div className="di di-line" style={{ filter: "drop-shadow(0 8px 16px rgba(245, 158, 11, 0.4)) drop-shadow(0 0 12px rgba(239, 68, 68, 0.5))" }}>
        <svg viewBox="0 0 52 34" fill="none" xmlns="http://www.w3.org/2000/svg">
          <polyline points="2,28 13,18 23,22 34,8 46,13" stroke="url(#grad-line)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="2" cy="28" r="3.5" fill="url(#grad-line)" />
          <circle cx="13" cy="18" r="3.5" fill="url(#grad-line)" />
          <circle cx="23" cy="22" r="3.5" fill="url(#grad-line)" />
          <circle cx="34" cy="8" r="3.5" fill="url(#grad-line)" />
          <circle cx="46" cy="13" r="3.5" fill="url(#grad-line)" />
        </svg>
      </div>
      <div className="di di-pie" style={{ filter: "drop-shadow(0 8px 16px rgba(139, 92, 246, 0.4)) drop-shadow(0 0 12px rgba(20, 184, 166, 0.5))" }}>
        <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="20" cy="20" r="16" stroke="url(#grad-pie)" strokeWidth="8" strokeDasharray="40 60" strokeDashoffset="25" opacity="1" />
          <circle cx="20" cy="20" r="16" stroke="url(#grad-pie)" strokeWidth="8" strokeDasharray="25 75" strokeDashoffset="-15" opacity="0.7" />
          <circle cx="20" cy="20" r="16" stroke="url(#grad-pie)" strokeWidth="8" strokeDasharray="15 85" strokeDashoffset="-40" opacity="0.5" />
        </svg>
      </div>
      <div className="di di-table" style={{ filter: "drop-shadow(0 8px 16px rgba(244, 63, 94, 0.4)) drop-shadow(0 0 12px rgba(147, 51, 234, 0.5))" }}>
        <svg viewBox="0 0 48 38" fill="none" xmlns="http://www.w3.org/2000/svg">
          <rect x="1" y="1" width="46" height="36" rx="3.5" stroke="url(#grad-table)" strokeWidth="2.5" />
          <line x1="1" y1="13" x2="47" y2="13" stroke="url(#grad-table)" strokeWidth="2" />
          <line x1="1" y1="25" x2="47" y2="25" stroke="url(#grad-table)" strokeWidth="2" />
          <line x1="17" y1="1" x2="17" y2="37" stroke="url(#grad-table)" strokeWidth="2" />
          <line x1="33" y1="1" x2="33" y2="37" stroke="url(#grad-table)" strokeWidth="2" />
        </svg>
      </div>
      <div className="di di-scatter" style={{ filter: "drop-shadow(0 8px 16px rgba(20, 184, 166, 0.4)) drop-shadow(0 0 12px rgba(234, 179, 8, 0.5))" }}>
        <svg viewBox="0 0 48 36" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="8" cy="30" r="4.5" fill="url(#grad-scatter)" />
          <circle cx="20" cy="20" r="4" fill="url(#grad-scatter)" />
          <circle cx="30" cy="14" r="5" fill="url(#grad-scatter)" />
          <circle cx="14" cy="10" r="3.5" fill="url(#grad-scatter)" />
          <circle cx="40" cy="24" r="4" fill="url(#grad-scatter)" />
          <circle cx="42" cy="8" r="3" fill="url(#grad-scatter)" />
        </svg>
      </div>
      <div className="di di-nodes" style={{ filter: "drop-shadow(0 8px 16px rgba(6, 182, 212, 0.4)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))" }}>
        <svg viewBox="0 0 48 38" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="8" cy="19" r="5.5" stroke="url(#grad-nodes)" strokeWidth="2.5" />
          <circle cx="40" cy="8" r="5" stroke="url(#grad-nodes)" strokeWidth="2.5" />
          <circle cx="40" cy="30" r="5" stroke="url(#grad-nodes)" strokeWidth="2.5" />
          <circle cx="24" cy="19" r="4.5" stroke="url(#grad-nodes)" strokeWidth="2.5" />
          <line x1="13.5" y1="19" x2="19.5" y2="19" stroke="url(#grad-nodes)" strokeWidth="2.5" />
          <line x1="28.5" y1="16" x2="35" y2="10" stroke="url(#grad-nodes)" strokeWidth="2.5" />
          <line x1="28.5" y1="22" x2="35" y2="28" stroke="url(#grad-nodes)" strokeWidth="2.5" />
        </svg>
      </div>
      <div className="di di-sql" style={{ filter: "drop-shadow(0 8px 16px rgba(236, 72, 153, 0.4)) drop-shadow(0 0 12px rgba(245, 158, 11, 0.5))" }}>
        <svg viewBox="0 0 44 28" fill="none" xmlns="http://www.w3.org/2000/svg">
          <text x="2" y="22" fontFamily="monospace" fontSize="24" fontWeight="bold" fill="url(#grad-sql)">{`{ }`}</text>
        </svg>
      </div>

      {/* Cloud */}
      <div className="di di-cloud" style={{ filter: "drop-shadow(0 8px 16px rgba(14, 165, 233, 0.4)) drop-shadow(0 0 12px rgba(99, 102, 241, 0.5))" }}>
        <svg viewBox="0 0 48 36" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M14 18c-4.4 0-8 3.6-8 8s3.6 8 8 8h22c5.5 0 10-4.5 10-10s-4.5-10-10-10c-1.1 0-2.2.2-3.2.6C31.5 8.2 26.2 4 20 4c-6.1 0-11.2 4.4-12.6 10.2-.4-.1-.9-.2-1.4-.2z" stroke="url(#grad-cloud)" strokeWidth="2.5" strokeLinejoin="round"/>
          <path d="M24 16v10M20 22l4-4 4 4" stroke="url(#grad-cloud)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>

      {/* Brain / AI */}
      <div className="di di-brain" style={{ filter: "drop-shadow(0 8px 16px rgba(217, 70, 239, 0.4)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))" }}>
        <svg viewBox="0 0 48 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M24 8a6 6 0 0 0-11-2.5A8 8 0 0 0 12 18s-4 1-4 6 5 8 7 8" stroke="url(#grad-brain)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M24 8a6 6 0 0 1 11-2.5A8 8 0 0 1 36 18s4 1 4 6-5 8-7 8" stroke="url(#grad-brain)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M24 8v24M15 28s3-2 9-2 9 2 9 2M16 20s3-2 8-2 8 2 8 2M18 12s2-2 6-2 6 2 6 2" stroke="url(#grad-brain)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>

      {/* Magnifying Glass */}
      <div className="di di-search" style={{ filter: "drop-shadow(0 8px 16px rgba(16, 185, 129, 0.4)) drop-shadow(0 0 12px rgba(20, 184, 166, 0.5))" }}>
        <svg viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="18" cy="18" r="12" stroke="url(#grad-search)" strokeWidth="3"/>
          <line x1="27" y1="27" x2="38" y2="38" stroke="url(#grad-search)" strokeWidth="4" strokeLinecap="round"/>
          <path d="M12 18h6M18 12v6" stroke="url(#grad-search)" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      </div>

      {/* Gear */}
      <div className="di di-gear" style={{ filter: "drop-shadow(0 8px 16px rgba(249, 115, 22, 0.4)) drop-shadow(0 0 12px rgba(234, 179, 8, 0.5))" }}>
        <svg viewBox="0 0 44 44" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="22" cy="22" r="7" stroke="url(#grad-gear)" strokeWidth="3"/>
          <path d="M22 6V2M22 42v-4M6 22H2M42 22h-4M10.7 10.7L7.9 7.9M36.1 36.1l-2.8-2.8M10.7 33.3l-2.8 2.8M36.1 7.9l-2.8 2.8" stroke="url(#grad-gear)" strokeWidth="3" strokeLinecap="round"/>
          <path d="M25.5 13.5a10 10 0 1 0 5 5" stroke="url(#grad-gear)" strokeWidth="2" strokeLinecap="round"/>
        </svg>
      </div>

</>
  );
}

// ─── Page ──────────────────────────────────────────────────────────────────────

export default function RegisterPage() {
  const router = useRouter();
  const pathname = usePathname();

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');

  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);
  const [isAngry, setIsAngry] = useState(false);
  const [isFlying, setIsFlying] = useState(false);

  // focused states
  const [nameFocused, setNameFocused] = useState(false);
  const [emailFocused, setEmailFocused] = useState(false);
  const [pwFocused, setPwFocused] = useState(false);
  const [confirmFocused, setConfirmFocused] = useState(false);

  const robotWrapRef = useRef<HTMLDivElement>(null);

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!robotWrapRef.current) return;
    const { clientX, clientY } = e;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = clientX - rect.left - rect.width / 2;
    const y = clientY - rect.top - rect.height / 2;
    
    const tx = x * 0.05;
    const ty = y * 0.05;
    const rotX = -(y * 0.02);
    const rotY = x * 0.02;

    robotWrapRef.current.style.transform = `translate(${tx}px, ${ty}px) perspective(1000px) rotateX(${rotX}deg) rotateY(${rotY}deg)`;
  };

  const handlePointerLeave = () => {
    if (!robotWrapRef.current) return;
    robotWrapRef.current.style.transform = `translate(0px, 0px) perspective(1000px) rotateX(0deg) rotateY(0deg)`;
  };

  // ── Rive ──
  const { rive, RiveComponent } = useRive({
    src: '/11277-21565-test.riv',
    autoplay: true,
  });

  useEffect(() => {
    if (!rive) return;
    const canvas = document.querySelector('canvas');
    if (canvas) {
      canvas.style.background = 'transparent';
      const ctx = canvas.getContext('2d');
      ctx?.clearRect(0, 0, canvas.width, canvas.height);
    }
  }, [rive]);

  // Drive Skin from any text-typing field
  const setSkin = (val: string) => {
    // Left empty since new riv file has no Skin input
  };

  const startFlying = () => {};
  const stopFlying = () => {};

  const doShake = () => { 
    setShake(true); 
    setIsAngry(true);
    setTimeout(() => setShake(false), 600); 
    setTimeout(() => setIsAngry(false), 2500); 
  };

  const handleRobotClick = () => {
    if (isFlying) return;
    setIsFlying(true);
    setTimeout(() => setIsFlying(false), 2000);
  };

  // ── Submit ──
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError('Passwords do not match.');
      doShake(); return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      doShake(); return;
    }
    if (password.length > MAX_PASSWORD_LENGTH) {
      setError(`Password cannot be longer than ${MAX_PASSWORD_LENGTH} characters.`);
      doShake(); return;
    }

    setLoading(true);
    try {
      const res = await axios.post(`${API}/auth/register`, { name, email, password });
      const tokens = res.data?.data;

      if (!tokens?.access_token) {
        setError('Unexpected response from server.');
        stopFlying(); doShake(); return;
      }

      localStorage.setItem('access_token', tokens.access_token);
      localStorage.setItem('refresh_token', tokens.refresh_token);
      setStoredAuthUser(tokens.user);

      // Success: robot flies away!
      startFlying();

      // Send newly registered users to the draft chat workspace and let the first message create the conversation.
      startTransition(() => router.push(toAppPath('/chat', pathname)));
    } catch (err: unknown) {
      const d = (
        err as {
          response?: {
            data?: { errors?: Array<{ message?: string }>; message?: string; detail?: string };
          };
        }
      )?.response?.data;

      const msg = d?.errors?.length
        ? d.errors.map((i) => i.message).filter(Boolean).join('; ')
        : d?.message || d?.detail || 'Registration failed. Please try again.';

      setError(normalizeRegistrationError(msg));
      doShake();
    } finally {
      setLoading(false);
    }
  };

  const strength = getStrength(password);

  // ── Render ──
  return (
    <>
      <style>{CSS}</style>

      <main className="rg-shell" onPointerMove={handlePointerMove} onPointerLeave={handlePointerLeave}>
        {/* ── LEFT: Form panel ── */}
        <div className="rg-left">
          <div className={`rg-card${shake ? ' rg-shake' : ''}`}>

            {/* Header */}
            <div className="rg-header">
              <h1 className="rg-heading">Create your account</h1>
              <p className="rg-sub">Join DataSage AI and start analyzing smarter</p>
            </div>

            <form onSubmit={handleSubmit}>
              {error && <div className="rg-error">{error}</div>}

              {/* Full name */}
              <div className={`rg-field${(nameFocused || name) ? ' rg-field--up' : ''}`}>
                <input
                  id="rg-name"
                  type="text"
                  placeholder=" "
                  value={name}
                  onChange={(e) => { setName(e.target.value); setSkin(e.target.value); }}
                  onFocus={() => setNameFocused(true)}
                  onBlur={() => setNameFocused(false)}
                  required
                />
                <label htmlFor="rg-name">Full name</label>
              </div>

              {/* Email */}
              <div className={`rg-field${(emailFocused || email) ? ' rg-field--up' : ''}`}>
                <input
                  id="rg-email"
                  type="email"
                  placeholder=" "
                  value={email}
                  onChange={(e) => { setEmail(e.target.value); setSkin(e.target.value); }}
                  onFocus={() => setEmailFocused(true)}
                  onBlur={() => setEmailFocused(false)}
                  required
                />
                <label htmlFor="rg-email">Email address</label>
              </div>

              {/* Password */}
              <div className={`rg-field rg-field--pw${(pwFocused || password) ? ' rg-field--up' : ''}`}>
                <input
                  id="rg-password"
                  type={showPw ? 'text' : 'password'}
                  placeholder=" "
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => { setPwFocused(true); startFlying(); }}
                  onBlur={() => { setPwFocused(false); stopFlying(); }}
                  maxLength={MAX_PASSWORD_LENGTH}
                  required
                />
                <label htmlFor="rg-password">Password</label>
                <button type="button" className="rg-eye" onClick={() => setShowPw((s) => !s)}>
                  {showPw ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>

              {/* Password strength */}
              {password.length > 0 && (
                <div className="rg-strength">
                  <div className="rg-strength-bars">
                    {([1, 2, 3] as const).map((i) => (
                      <div
                        key={i}
                        className="rg-strength-seg"
                        style={{ background: i <= strength ? STRENGTH_COLOR[strength] : '#e2e8f0' }}
                      />
                    ))}
                  </div>
                  <span className="rg-strength-label" style={{ color: STRENGTH_COLOR[strength] }}>
                    {STRENGTH_LABEL[strength]}
                  </span>
                </div>
              )}

              {/* Confirm password */}
              <div className={`rg-field rg-field--pw${(confirmFocused || confirm) ? ' rg-field--up' : ''}`}>
                <input
                  id="rg-confirm"
                  type={showConfirm ? 'text' : 'password'}
                  placeholder=" "
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  onFocus={() => { setConfirmFocused(true); startFlying(); }}
                  onBlur={() => { setConfirmFocused(false); stopFlying(); }}
                  maxLength={MAX_PASSWORD_LENGTH}
                  required
                />
                <label htmlFor="rg-confirm">Confirm password</label>
                <button type="button" className="rg-eye" onClick={() => setShowConfirm((s) => !s)}>
                  {showConfirm ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>

              <button type="submit" className="rg-btn-primary" disabled={loading}>
                {loading ? 'Creating account…' : 'Create account →'}
              </button>
            </form>

            {/* Switch */}
            <p className="rg-switch">
              Already have an account?{' '}
              <Link href={toAppPath('/login', pathname)} className="rg-switch-link">
                Sign in →
              </Link>
            </p>
          </div>
        </div>

        {/* ── RIGHT: Animated panel ── */}
        <div className="rg-right">
          <Particles />
          <DataIcons />

          <div className="rg-brand">
            <span className="rg-brand-icon"><BrandIcon /></span>
            DataSage AI
          </div>

          <div
            className={`rg-robot-wrap ${isAngry ? 'rg-angry' : ''} ${isFlying ? 'rg-flying' : ''}`}
            onClick={handleRobotClick}
          >
            {isFlying && (
              <div className="nitro-burst">
                <div className="nitro-flame nitro-main"></div>
                <div className="nitro-flame nitro-core"></div>
                <div className="nitro-sparks"></div>
              </div>
            )}
            <div ref={robotWrapRef} style={{ width: '100%', height: '100%', transition: 'transform 0.1s ease-out' }}>
              <div className={`rg-angry-inner ${isAngry ? 'angry-shake' : ''}`} style={{ width: '100%', height: '100%', position: 'relative' }}>
                <RiveComponent />
              </div>
            </div>
          </div>
          <div className={`rg-robot-shadow ${isFlying ? 'rg-shadow-shrink' : ''}`} />
        </div>
      </main>
    </>
  );
}

// ─── Styles ────────────────────────────────────────────────────────────────────
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

.rg-shell * { box-sizing: border-box; }

.rg-shell {
  display: flex;
  height: 100vh;
  font-family: 'Inter', sans-serif;
  overflow: hidden;
}

/* ════════════ LEFT PANEL (form) ════════════ */
.rg-left {
  flex: 1;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 44px;
  box-shadow: 8px 0 48px rgba(0, 0, 0, 0.06);
  overflow-y: auto;
}

.rg-card {
  width: 100%;
  max-width: 390px;
  animation: rgFadeUp 0.55s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes rgFadeUp {
  from { opacity: 0; transform: translateY(22px); }
  to   { opacity: 1; transform: translateY(0); }
}

@keyframes rgShake {
  0%, 100% { transform: translateX(0); }
  15%       { transform: translateX(-10px); }
  30%       { transform: translateX(10px); }
  45%       { transform: translateX(-7px); }
  60%       { transform: translateX(7px); }
  75%       { transform: translateX(-4px); }
  90%       { transform: translateX(4px); }
}

.rg-shake { animation: rgShake 0.55s ease; }

/* Header */
.rg-header { margin-bottom: 28px; }

.rg-heading {
  font-size: 26px !important;
  font-weight: 800 !important;
  color: #0f172a !important;
  margin: 0 0 6px !important;
  letter-spacing: -0.025em !important;
  line-height: 1.2 !important;
  background: none !important;
  -webkit-background-clip: unset !important;
  -webkit-text-fill-color: unset !important;
}

.rg-sub {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

/* Error banner */
.rg-error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
  padding: 11px 14px;
  border-radius: 10px;
  font-size: 13.5px;
  margin-bottom: 18px;
  font-weight: 500;
}

/* ── Floating label field ── */
.rg-field {
  position: relative;
  margin-bottom: 18px;
}

.rg-field input {
  width: 100%;
  padding: 25px 16px 9px;
  border: 1.5px solid #e2e8f0;
  border-radius: 12px;
  font-size: 15px;
  font-family: 'Inter', sans-serif;
  background: #f8fafc;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
  outline: none;
  color: #0f172a;
  -webkit-appearance: none;
}

.rg-field input:focus {
  border-color: #2563eb;
  background: #ffffff;
  box-shadow: 0 0 0 3.5px rgba(37, 99, 235, 0.13);
}

.rg-field label {
  position: absolute;
  left: 16px;
  top: 18px;
  font-size: 15px;
  color: #94a3b8;
  pointer-events: none;
  transition: all 0.2s cubic-bezier(0.22, 1, 0.36, 1);
  font-family: 'Inter', sans-serif;
}

.rg-field--up label {
  top: 7px;
  font-size: 10.5px;
  color: #2563eb;
  font-weight: 700;
  letter-spacing: 0.07em;
  text-transform: uppercase;
}

.rg-field--pw input { padding-right: 48px; }

.rg-eye {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  padding: 5px;
  cursor: pointer;
  color: #94a3b8;
  display: flex;
  align-items: center;
  transition: color 0.2s;
}
.rg-eye:hover { color: #2563eb; }

/* Password strength */
.rg-strength {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: -8px 0 16px;
}

.rg-strength-bars {
  display: flex;
  gap: 5px;
  flex: 1;
}

.rg-strength-seg {
  flex: 1;
  height: 4px;
  border-radius: 99px;
  transition: background 0.3s;
}

.rg-strength-label {
  font-size: 12px;
  font-weight: 700;
  min-width: 44px;
  text-align: right;
  transition: color 0.3s;
}

/* Submit button */
.rg-btn-primary {
  width: 100%;
  padding: 15.5px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #ffffff;
  border: none;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  font-family: 'Inter', sans-serif;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  letter-spacing: 0.01em;
}

.rg-btn-primary:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 10px 30px rgba(37, 99, 235, 0.38);
}

.rg-btn-primary:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
}

.rg-btn-primary:disabled {
  background: #93c5fd;
  cursor: not-allowed;
}

/* Divider */
.rg-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0;
  color: #94a3b8;
  font-size: 13px;
  font-weight: 500;
}

.rg-divider::before,
.rg-divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #e2e8f0;
}

/* Google button */
.rg-btn-google {
  width: 100%;
  padding: 13.5px;
  background: #ffffff;
  border: 1.5px solid #e2e8f0;
  border-radius: 14px;
  font-size: 14px;
  font-weight: 600;
  font-family: 'Inter', sans-serif;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #0f172a;
}
.rg-btn-google:hover {
  border-color: #93c5fd;
  background: #eff6ff;
  transform: translateY(-1px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.07);
}

/* Switch */
.rg-switch {
  text-align: center;
  margin-top: 22px;
  font-size: 14px;
  color: #64748b;
}

.rg-switch-link {
  color: #2563eb;
  font-weight: 700;
  text-decoration: none;
}
.rg-switch-link:hover { text-decoration: underline; }

/* ════════════ RIGHT PANEL (animated) ════════════ */
.rg-right {
  width: 500px;
  flex-shrink: 0;
  background: #111326;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.rg-brand {
  position: absolute;
  top: 28px;
  right: 28px;
  display: flex;
  align-items: center;
  gap: 9px;
  font-weight: 800;
  font-size: 15px;
  color: #c7d2fe;
  letter-spacing: -0.01em;
}

.rg-brand-icon {
  width: 32px;
  height: 32px;
  background: #2563eb;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.rg-particle {
  position: absolute;
  border-radius: 50%;
  background: rgba(165, 180, 252, 0.06);
  animation: rgFloat linear infinite;
  filter: blur(10px);
  bottom: -80px;
}

@keyframes rgFloat {
  0%   { transform: translateY(0) scale(0.7);  opacity: 0; }
  12%  { opacity: 0.9; }
  85%  { opacity: 0.35; }
  100% { transform: translateY(-115vh) scale(1.4); opacity: 0; }
}

.rg-robot-wrap {
  width: 620px;
  height: 620px;
  flex-shrink: 0;
  flex-grow: 0;
  position: relative;
  z-index: 10;
  transform: scale(1.1);
  background: transparent;
  cursor: pointer;
}

.rg-robot-wrap.rg-flying {
  animation: robot-fly-rg 2s cubic-bezier(0.3, 0, 0.2, 1) forwards;
}

@keyframes robot-fly-rg {
  0% { transform: scale(1.1) translateY(0); }
  40% { transform: scale(1.2) translateY(-150px); }
  60% { transform: scale(1.2) translateY(-150px); }
  100% { transform: scale(1.1) translateY(0); }
}

.rg-robot-shadow {
  width: 72px;
  height: 14px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.4);
  filter: blur(4px);
  margin-top: -80px;
  transition: transform 0.3s ease, opacity 0.3s ease;
}

.rg-robot-shadow.rg-shadow-shrink {
  animation: shadow-shrink-rg 2s cubic-bezier(0.3, 0, 0.2, 1) forwards;
}

@keyframes shadow-shrink-rg {
  0% { transform: scale(1); opacity: 1; }
  40% { transform: scale(0.3); opacity: 0.1; }
  60% { transform: scale(0.3); opacity: 0.1; }
  100% { transform: scale(1); opacity: 1; }
}

.rg-robot-wrap.rg-angry {
  /* Powerful angry reaction */
  filter: hue-rotate(330deg) saturate(220%) contrast(110%) drop-shadow(0 0 60px rgba(255, 30, 30, 0.4));
  transition: filter 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.rg-angry-inner {
  transform-origin: center center;
}

.rg-angry-inner.angry-shake {
  animation: robot-angry-shake-rg 0.3s cubic-bezier(.36, .07, .19, .97) both infinite;
}

.rg-angry-inner.angry-shake::after {
  content: "";
  position: absolute;
  top: 25%;  
  left: 38%;
  width: 24%;
  height: 8%;
  background: 
    linear-gradient(15deg, transparent 40%, rgba(200,0,0,0.8) 43%, rgba(200,0,0,0.8) 57%, transparent 60%) 0 0% / 50% 100% no-repeat,
    linear-gradient(-15deg, transparent 40%, rgba(200,0,0,0.8) 43%, rgba(200,0,0,0.8) 57%, transparent 60%) 100% 0% / 50% 100% no-repeat;
  filter: drop-shadow(0 0 10px rgba(255,10,10,0.6));
  pointer-events: none;
  animation: eyebrow-slam-rg 0.2s forwards cubic-bezier(0.6, -0.4, 0.2, 1.5);
  transform-origin: top center;
  z-index: 10;
}

@keyframes eyebrow-slam-rg {
  0% { transform: translateY(-40px) scale(1.2); opacity: 0; }
  100% { transform: translateY(0px) scale(1); opacity: 1; }
}

@keyframes robot-angry-shake-rg {
  10%, 90% { transform: translate3d(-3px, 1px, 0) rotate(1deg); }
  20%, 80% { transform: translate3d(4px, -1px, 0) rotate(-1deg); }
  30%, 50%, 70% { transform: translate3d(-6px, -2px, 0) rotate(1.5deg); }
  40%, 60% { transform: translate3d(6px, 2px, 0) rotate(-1.5deg); }
}

@keyframes rgShadow {
  0%, 100% { transform: scaleX(1);    opacity: 0.6; }
  50%       { transform: scaleX(0.6); opacity: 0.22; }
}

.rg-tagline {
  margin-top: 14px;
  font-size: 13.5px;
  font-weight: 500;
  color: #a5b4fc;
  text-align: center;
  line-height: 1.75;
  padding: 0 32px;
  letter-spacing: 0.01em;
  z-index: 2;
  position: relative;
}

/* ── Floating data icons ── */
.di {
  position: absolute;
  color: rgba(165, 180, 252, 0.28);
  z-index: 1;
  animation: diFloat 35s ease-in-out infinite alternate;
}

@keyframes diFloat {
  0% { transform: translate(0, 0) rotate(0deg); }
  25% { transform: translate(12vw, 8vh) rotate(15deg); }
  50% { transform: translate(-5vw, 15vh) rotate(-10deg); }
  75% { transform: translate(-12vw, -12vh) rotate(10deg); }
  100% { transform: translate(0, 0) rotate(0deg); }
}

.di-db      { width: 52px; height: 52px; top: 10%; left: 5%;   animation-duration: 32s;   animation-delay: 0s;     }
.di-bar     { width: 48px; height: 48px; top: 6%;  right: 6%;  animation-duration: 45s;   animation-delay: -5s;    animation-direction: alternate-reverse; }
.di-line    { width: 66px; height: 40px; top: 50%; left: 3%;   animation-duration: 38s;   animation-delay: -12s;   }
.di-pie     { width: 48px; height: 48px; top: 44%; right: 4%;  animation-duration: 41s;   animation-delay: -3s;    animation-direction: alternate-reverse; }
.di-table   { width: 58px; height: 44px; top: 78%; left: 5%;   animation-duration: 35s;   animation-delay: -20s;   }
.di-scatter { width: 54px; height: 42px; top: 80%; right: 6%;  animation-duration: 48s;   animation-delay: -8s;    animation-direction: alternate-reverse; }
.di-nodes   { width: 54px; height: 44px; top: 18%; right: 4%;  animation-duration: 43s;   animation-delay: -15s;   }
.di-sql     { width: 56px; height: 34px; top: 68%; left: 42%;  animation-duration: 37s;   animation-delay: -2s;    animation-direction: alternate-reverse; }
.di-cloud   { width: 56px; height: 56px; top: 28%; left: 24%;  animation-duration: 50s;   animation-delay: -25s;   }
.di-brain   { width: 52px; height: 52px; top: 32%; right: 28%; animation-duration: 39s;   animation-delay: -10s;   animation-direction: alternate-reverse; }
.di-search  { width: 48px; height: 48px; top: 62%; right: 26%; animation-duration: 46s;   animation-delay: -18s;   }
.di-gear    { width: 46px; height: 46px; top: 86%; left: 30%;  animation-duration: 34s;   animation-delay: -7s;    animation-direction: alternate-reverse; }

/* ── Responsive ── */
@media (max-width: 900px) {
  .rg-right { display: none; }
  .rg-left  { width: 100%; padding: 36px 24px; }
}
`;
