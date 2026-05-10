"use client";

import React from "react";

export function BrandLogo() {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes shimmer-logo { 0%{background-position:0% 50%} 100%{background-position:200% 50%} }
        @keyframes fadeUp-logo { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
        @keyframes dash-logo { from{stroke-dashoffset:200} to{stroke-dashoffset:0} }
        @keyframes spin-slow-logo { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes bar-pulse-logo { 0%,100%{transform:scaleY(1)} 50%{transform:scaleY(0.55)} }

        .logo-wrap {
          display:flex;flex-direction:column;align-items:center;justify-content:center;
          background:transparent;
          position:relative;
        }
        .logo-row-inner {
          display:flex;align-items:center;gap:12px;
        }
        .logo-brand-text {
          font-size:28px;font-weight:800;letter-spacing:-1px;line-height:1;
          font-family:var(--font-sans,'Inter',sans-serif);
          background:linear-gradient(100deg,#00e5b0 0%,#00c4ff 40%,#b48afa 75%,#00e5b0 100%);
          background-size:220% auto;
          -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
          animation:shimmer-logo 4.5s linear infinite;
        }
      ` }} />
      <div className="logo-wrap">
        <div className="logo-row-inner">
          <svg width="40" height="40" viewBox="0 0 62 62" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="lg1-brand" x1="0" y1="0" x2="62" y2="62" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stopColor="#00e5b0" stopOpacity="0.9"/>
                <stop offset="55%" stopColor="#00c4ff" stopOpacity="0.8"/>
                <stop offset="100%" stopColor="#b48afa" stopOpacity="0.9"/>
              </linearGradient>
            </defs>
            <circle cx="31" cy="31" r="29" fill="#0d1525" stroke="url(#lg1-brand)" strokeWidth="1.2"/>
            <circle cx="31" cy="31" r="22" fill="none" stroke="rgba(0,220,170,0.1)" strokeWidth="1"
              strokeDasharray="3 6"
              style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
            <circle cx="31" cy="9" r="3.5" fill="#00e5b0" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
            <circle cx="31" cy="9" r="3.5" fill="#00e5b0" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite", opacity:0.9 }}/>
            <circle cx="49.5" cy="42" r="3" fill="#00c4ff" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
            <circle cx="12.5" cy="42" r="3" fill="#b48afa" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
            <g style={{ transformOrigin:"31px 38px" }}>
              <rect x="14" y="30" width="5" height="12" rx="2" fill="#00e5b0" opacity="0.9"
                style={{ transformOrigin:"16.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 0s" }}/>
              <rect x="21" y="23" width="5" height="19" rx="2" fill="#00c4ff" opacity="0.8"
                style={{ transformOrigin:"23.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 0.35s" }}/>
              <rect x="28" y="27" width="5" height="15" rx="2" fill="#b48afa" opacity="0.8"
                style={{ transformOrigin:"30.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 0.7s" }}/>
              <rect x="35" y="19" width="5" height="23" rx="2" fill="#00e5b0" opacity="0.7"
                style={{ transformOrigin:"37.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 1.05s" }}/>
              <rect x="42" y="24" width="5" height="18" rx="2" fill="#00c4ff" opacity="0.6"
                style={{ transformOrigin:"44.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 1.4s" }}/>
            </g>
            <path d="M16 28 Q22 20 28 24 Q34 18 44 15" fill="none"
              stroke="#00e5b0" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
              strokeDasharray="70" style={{ animation:"dash-logo 2.8s ease-in-out infinite alternate" }} opacity="0.7"/>
          </svg>
          <div className="logo-brand-text">DataSage</div>
        </div>
      </div>
    </>
  );
}

export function BrandLogoIcon({ size = 24 }: { size?: number }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: `
        @keyframes dash-logo { from{stroke-dashoffset:200} to{stroke-dashoffset:0} }
        @keyframes spin-slow-logo { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        @keyframes bar-pulse-logo { 0%,100%{transform:scaleY(1)} 50%{transform:scaleY(0.55)} }
      ` }} />
      <svg width={size} height={size} viewBox="0 0 62 62" fill="none" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="lg1-brand" x1="0" y1="0" x2="62" y2="62" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#00e5b0" stopOpacity="0.9"/>
            <stop offset="55%" stopColor="#00c4ff" stopOpacity="0.8"/>
            <stop offset="100%" stopColor="#b48afa" stopOpacity="0.9"/>
          </linearGradient>
        </defs>
        <circle cx="31" cy="31" r="29" fill="#0d1525" stroke="url(#lg1-brand)" strokeWidth="1.2"/>
        <circle cx="31" cy="31" r="22" fill="none" stroke="rgba(0,220,170,0.1)" strokeWidth="1"
          strokeDasharray="3 6"
          style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
        <circle cx="31" cy="9" r="3.5" fill="#00e5b0" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
        <circle cx="49.5" cy="42" r="3" fill="#00c4ff" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
        <circle cx="12.5" cy="42" r="3" fill="#b48afa" style={{ transformOrigin:"31px 31px", animation:"spin-slow-logo 20s linear infinite" }}/>
        <g style={{ transformOrigin:"31px 38px" }}>
          <rect x="14" y="30" width="5" height="12" rx="2" fill="#00e5b0" opacity="0.9"
            style={{ transformOrigin:"16.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 0s" }}/>
          <rect x="21" y="23" width="5" height="19" rx="2" fill="#00c4ff" opacity="0.8"
            style={{ transformOrigin:"23.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 0.35s" }}/>
          <rect x="28" y="27" width="5" height="15" rx="2" fill="#b48afa" opacity="0.8"
            style={{ transformOrigin:"30.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 0.7s" }}/>
          <rect x="35" y="19" width="5" height="23" rx="2" fill="#00e5b0" opacity="0.7"
            style={{ transformOrigin:"37.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 1.05s" }}/>
          <rect x="42" y="24" width="5" height="18" rx="2" fill="#00c4ff" opacity="0.6"
            style={{ transformOrigin:"44.5px 38px", animation:"bar-pulse-logo 2s ease-in-out infinite 1.4s" }}/>
        </g>
        <path d="M16 28 Q22 20 28 24 Q34 18 44 15" fill="none"
          stroke="#00e5b0" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
          strokeDasharray="70" style={{ animation:"dash-logo 2.8s ease-in-out infinite alternate" }} opacity="0.7"/>
      </svg>
    </>
  );
}
