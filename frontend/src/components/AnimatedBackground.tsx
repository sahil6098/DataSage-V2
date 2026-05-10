"use client";

const particles = [
  { s: 28, l: "6%", d: "0s", dur: "11s" },
  { s: 18, l: "18%", d: "-3.5s", dur: "15s" },
  { s: 44, l: "32%", d: "-6s", dur: "10s" },
  { s: 16, l: "48%", d: "-1.5s", dur: "14s" },
  { s: 34, l: "62%", d: "-4.5s", dur: "9s" },
  { s: 22, l: "76%", d: "-7s", dur: "13s" },
  { s: 38, l: "87%", d: "-2s", dur: "12s" },
  { s: 14, l: "54%", d: "-5.5s", dur: "16s" },
];

export default function AnimatedBackground() {
  return (
    <div className="animated-background" aria-hidden="true">
      <div className="animated-background-grid" />
      {particles.map((particle, index) => (
        <span
          key={index}
          className="animated-background-particle"
          style={{
            width: particle.s,
            height: particle.s,
            left: particle.l,
            animationDelay: particle.d,
            animationDuration: particle.dur,
          }}
        />
      ))}

      <svg className="animated-background-defs" width="0" height="0">
        <defs>
          <linearGradient id="ab-grad-db" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#4F46E5" />
            <stop offset="100%" stopColor="#E02FEF" />
          </linearGradient>
          <linearGradient id="ab-grad-bar" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10B981" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id="ab-grad-line" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F59E0B" />
            <stop offset="100%" stopColor="#EF4444" />
          </linearGradient>
          <linearGradient id="ab-grad-pie" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#8B5CF6" />
            <stop offset="100%" stopColor="#14B8A6" />
          </linearGradient>
          <linearGradient id="ab-grad-table" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F43F5E" />
            <stop offset="100%" stopColor="#9333EA" />
          </linearGradient>
          <linearGradient id="ab-grad-scatter" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#14B8A6" />
            <stop offset="100%" stopColor="#EAB308" />
          </linearGradient>
          <linearGradient id="ab-grad-nodes" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06B6D4" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id="ab-grad-sql" x1="0%" y1="100%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#EC4899" />
            <stop offset="100%" stopColor="#F59E0B" />
          </linearGradient>
          <linearGradient id="ab-grad-cloud" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#0EA5E9" />
            <stop offset="100%" stopColor="#6366F1" />
          </linearGradient>
          <linearGradient id="ab-grad-sun" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#F97316" />
            <stop offset="100%" stopColor="#EAB308" />
          </linearGradient>
          <linearGradient id="ab-grad-brain" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#D946EF" />
            <stop offset="100%" stopColor="#3B82F6" />
          </linearGradient>
          <linearGradient id="ab-grad-search" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#10B981" />
            <stop offset="100%" stopColor="#14B8A6" />
          </linearGradient>
        </defs>
      </svg>

      <div className="ab-icon ab-db">
        <svg viewBox="0 0 40 44" fill="none">
          <ellipse cx="20" cy="9" rx="14" ry="5" stroke="url(#ab-grad-db)" strokeWidth="2.5" />
          <path d="M6 9v9c0 2.76 6.27 5 14 5s14-2.24 14-5V9" stroke="url(#ab-grad-db)" strokeWidth="2.5" />
          <path d="M6 18v9c0 2.76 6.27 5 14 5s14-2.24 14-5v-9" stroke="url(#ab-grad-db)" strokeWidth="2.5" />
          <path d="M6 27v8c0 2.76 6.27 5 14 5s14-2.24 14-5v-8" stroke="url(#ab-grad-db)" strokeWidth="2.5" />
        </svg>
      </div>

      <div className="ab-icon ab-bar">
        <svg viewBox="0 0 40 36" fill="none">
          <rect x="2" y="22" width="9" height="12" rx="2" fill="url(#ab-grad-bar)" opacity="0.9" />
          <rect x="15" y="14" width="9" height="20" rx="2" fill="url(#ab-grad-bar)" />
          <rect x="28" y="4" width="9" height="30" rx="2" fill="url(#ab-grad-bar)" opacity="0.95" />
          <line x1="1" y1="35" x2="39" y2="35" stroke="url(#ab-grad-bar)" strokeWidth="2" opacity="0.6" />
        </svg>
      </div>

      <div className="ab-icon ab-line">
        <svg viewBox="0 0 52 34" fill="none">
          <polyline points="2,28 13,18 23,22 34,8 46,13" stroke="url(#ab-grad-line)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="2" cy="28" r="3.5" fill="url(#ab-grad-line)" />
          <circle cx="13" cy="18" r="3.5" fill="url(#ab-grad-line)" />
          <circle cx="23" cy="22" r="3.5" fill="url(#ab-grad-line)" />
          <circle cx="34" cy="8" r="3.5" fill="url(#ab-grad-line)" />
          <circle cx="46" cy="13" r="3.5" fill="url(#ab-grad-line)" />
        </svg>
      </div>

      <div className="ab-icon ab-pie">
        <svg viewBox="0 0 40 40" fill="none">
          <circle cx="20" cy="20" r="16" stroke="url(#ab-grad-pie)" strokeWidth="8" strokeDasharray="40 60" strokeDashoffset="25" />
          <circle cx="20" cy="20" r="16" stroke="url(#ab-grad-pie)" strokeWidth="8" strokeDasharray="25 75" strokeDashoffset="-15" opacity="0.7" />
          <circle cx="20" cy="20" r="16" stroke="url(#ab-grad-pie)" strokeWidth="8" strokeDasharray="15 85" strokeDashoffset="-40" opacity="0.5" />
        </svg>
      </div>

      <div className="ab-icon ab-table">
        <svg viewBox="0 0 48 38" fill="none">
          <rect x="1.5" y="1.5" width="45" height="35" rx="3.5" stroke="url(#ab-grad-table)" strokeWidth="2.5" />
          <line x1="1" y1="13" x2="47" y2="13" stroke="url(#ab-grad-table)" strokeWidth="2" />
          <line x1="1" y1="25" x2="47" y2="25" stroke="url(#ab-grad-table)" strokeWidth="2" />
          <line x1="17" y1="1" x2="17" y2="37" stroke="url(#ab-grad-table)" strokeWidth="2" />
          <line x1="33" y1="1" x2="33" y2="37" stroke="url(#ab-grad-table)" strokeWidth="2" />
        </svg>
      </div>

      <div className="ab-icon ab-scatter">
        <svg viewBox="0 0 48 36" fill="none">
          <circle cx="8" cy="30" r="4.5" fill="url(#ab-grad-scatter)" />
          <circle cx="20" cy="20" r="4" fill="url(#ab-grad-scatter)" />
          <circle cx="30" cy="14" r="5" fill="url(#ab-grad-scatter)" />
          <circle cx="14" cy="10" r="3.5" fill="url(#ab-grad-scatter)" />
          <circle cx="40" cy="24" r="4" fill="url(#ab-grad-scatter)" />
          <circle cx="26" cy="30" r="3.5" fill="url(#ab-grad-scatter)" />
          <circle cx="42" cy="8" r="3" fill="url(#ab-grad-scatter)" />
        </svg>
      </div>

      <div className="ab-icon ab-nodes">
        <svg viewBox="0 0 48 38" fill="none">
          <circle cx="8" cy="19" r="5.5" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
          <circle cx="40" cy="8" r="5" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
          <circle cx="40" cy="30" r="5" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
          <circle cx="24" cy="19" r="4.5" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
          <line x1="13.5" y1="19" x2="19.5" y2="19" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
          <line x1="28.5" y1="16" x2="35" y2="10" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
          <line x1="28.5" y1="22" x2="35" y2="28" stroke="url(#ab-grad-nodes)" strokeWidth="2.5" />
        </svg>
      </div>

      <div className="ab-icon ab-sql">
        <svg viewBox="0 0 44 28" fill="none">
          <text x="2" y="22" fontFamily="monospace" fontSize="24" fontWeight="bold" fill="url(#ab-grad-sql)">{`{ }`}</text>
        </svg>
      </div>

      <div className="ab-icon ab-cloud">
        <svg viewBox="0 0 48 36" fill="none">
          <path d="M14 18c-4.4 0-8 3.6-8 8s3.6 8 8 8h22c5.5 0 10-4.5 10-10s-4.5-10-10-10c-1.1 0-2.2.2-3.2.6C31.5 8.2 26.2 4 20 4c-6.1 0-11.2 4.4-12.6 10.2-.4-.1-.9-.2-1.4-.2z" stroke="url(#ab-grad-cloud)" strokeWidth="2.5" strokeLinejoin="round" />
          <path d="M24 16v10M20 22l4-4 4 4" stroke="url(#ab-grad-cloud)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <div className="ab-icon ab-brain">
        <svg viewBox="0 0 48 40" fill="none">
          <path d="M24 8a6 6 0 0 0-11-2.5A8 8 0 0 0 12 18s-4 1-4 6 5 8 7 8" stroke="url(#ab-grad-brain)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M24 8a6 6 0 0 1 11-2.5A8 8 0 0 1 36 18s4 1 4 6-5 8-7 8" stroke="url(#ab-grad-brain)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M24 8v24M15 28s3-2 9-2 9 2 9 2M16 20s3-2 8-2 8 2 8 2M18 12s2-2 6-2 6 2 6 2" stroke="url(#ab-grad-brain)" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>

      <div className="ab-icon ab-search">
        <svg viewBox="0 0 44 44" fill="none">
          <circle cx="18" cy="18" r="12" stroke="url(#ab-grad-search)" strokeWidth="3" />
          <line x1="27" y1="27" x2="38" y2="38" stroke="url(#ab-grad-search)" strokeWidth="4" strokeLinecap="round" />
          <path d="M12 18h6M18 12v6" stroke="url(#ab-grad-search)" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </div>

      <div className="ab-icon ab-sun">
        <svg viewBox="0 0 44 44" fill="none">
          <circle cx="22" cy="22" r="8" stroke="url(#ab-grad-sun)" strokeWidth="3" />
          <path d="M22 5V1M22 43v-4M5 22H1M43 22h-4M10.4 10.4 7.6 7.6M36.4 36.4l-2.8-2.8M10.4 33.6l-2.8 2.8M36.4 7.6l-2.8 2.8" stroke="url(#ab-grad-sun)" strokeWidth="3" strokeLinecap="round" />
        </svg>
      </div>

    </div>
  );
}
