// /home/* — surface CSS injected via <style dangerouslySetInnerHTML>.
// Ships keyframes + a few utility classes the prototype relies on.
// Tokens (bg-surface-*, brand-*, border-*) come from Tailwind config.
//
// Option B integration: exported as a string constant (zero loader config).

export const surfaceCss = String.raw`
/* ── Hebrew font stack (system only — no @import) ───────────── */
.maya-hebrew {
  font-family: "Heebo", "Assistant", "Rubik", "Segoe UI",
               "Helvetica Neue", system-ui, sans-serif;
  font-feature-settings: "kern", "liga";
  letter-spacing: 0.005em;
}

/* ── Fullscreen shell — escapes the dashboard sidebar ──────── */
.maya-shell {
  position: fixed;
  inset: 0;
  z-index: 60;
  overflow-y: auto;
  background:
    radial-gradient(1200px 700px at 70% 0%, rgba(64, 196, 180, 0.06), transparent 60%),
    radial-gradient(900px 600px at 30% 100%, rgba(132, 102, 245, 0.05), transparent 60%),
    #0b0e13;
}

/* ── Maya core radar ───────────────────────────────────────── */
.maya-core {
  position: relative;
  aspect-ratio: 1 / 1;
  display: grid;
  place-items: center;
}
.maya-core-orb {
  width: 38%;
  aspect-ratio: 1 / 1;
  border-radius: 50%;
  background:
    radial-gradient(circle at 32% 32%, rgba(160, 240, 220, 0.85), rgba(64, 196, 180, 0.35) 38%, rgba(20, 60, 70, 0.0) 70%);
  box-shadow:
    0 0 60px rgba(64, 196, 180, 0.35),
    inset 0 0 40px rgba(64, 196, 180, 0.4);
  animation: maya-breath 5.6s ease-in-out infinite;
}
.maya-core-ring {
  position: absolute;
  border-radius: 50%;
  border: 1px solid rgba(120, 200, 200, 0.12);
  pointer-events: none;
}
.maya-core-ring.r1 { inset: 8%;  animation: maya-ring 9s linear infinite; }
.maya-core-ring.r2 { inset: 22%; animation: maya-ring 14s linear infinite reverse; opacity: 0.7; }
.maya-core-ring.r3 { inset: 36%; animation: maya-ring 7s linear infinite; opacity: 0.5; }

/* ── Constellation node ────────────────────────────────────── */
.maya-orbit {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(20, 26, 34, 0.6);
  backdrop-filter: blur(6px);
  font-size: 11px;
  white-space: nowrap;
  transform: translate(-50%, -50%);
}
.maya-orbit.hot  { border-color: rgba(244, 113, 124, 0.6); box-shadow: 0 0 18px rgba(244, 113, 124, 0.25); }
.maya-orbit.warm { border-color: rgba(245, 184, 110, 0.45); box-shadow: 0 0 14px rgba(245, 184, 110, 0.18); }
.maya-orbit.cool { border-color: rgba(110, 220, 200, 0.35); }
.maya-orbit-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: currentColor;
}
.maya-orbit.hot  .maya-orbit-dot { color: rgb(244, 113, 124); animation: maya-pulse-dot 1.6s ease-in-out infinite; }
.maya-orbit.warm .maya-orbit-dot { color: rgb(245, 184, 110); }
.maya-orbit.cool .maya-orbit-dot { color: rgb(110, 220, 200); }

/* ── Live dot (mirrors existing globals.css if absent) ─────── */
.maya-live-dot {
  display: inline-block;
  width: 8px; height: 8px; border-radius: 50%;
  background: rgb(244, 113, 124);
  box-shadow: 0 0 0 0 rgba(244, 113, 124, 0.55);
  animation: maya-live 1.6s ease-out infinite;
}

/* ── Voice waveform bars (CSS-only, no canvas) ─────────────── */
.maya-wave {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 16px;
}
.maya-wave > i {
  width: 2px;
  background: currentColor;
  border-radius: 1px;
  animation: maya-wave 0.9s ease-in-out infinite;
}
.maya-wave > i:nth-child(1) { animation-delay: -0.0s; }
.maya-wave > i:nth-child(2) { animation-delay: -0.15s; }
.maya-wave > i:nth-child(3) { animation-delay: -0.3s; }
.maya-wave > i:nth-child(4) { animation-delay: -0.45s; }
.maya-wave > i:nth-child(5) { animation-delay: -0.6s; }

/* ── Hero card tone bar ────────────────────────────────────── */
.maya-tone-bar {
  position: absolute;
  inset-inline-start: 0;
  top: 0; bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, rgb(64, 196, 180), rgb(132, 102, 245));
  border-start-start-radius: inherit;
  border-end-start-radius: inherit;
}

/* ── Section label (mono uppercase tracking-wide) ──────────── */
.maya-section-label {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgb(110, 220, 200);
  opacity: 0.85;
}

/* ── Entry animation ───────────────────────────────────────── */
.maya-fade-in {
  animation: maya-fade 480ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
}

/* ── Keyframes ─────────────────────────────────────────────── */
@keyframes maya-breath {
  0%, 100% { box-shadow: 0 0 60px rgba(64, 196, 180, 0.35), inset 0 0 40px rgba(64, 196, 180, 0.4); opacity: 0.95; }
  50%      { box-shadow: 0 0 96px rgba(64, 196, 180, 0.5),  inset 0 0 56px rgba(64, 196, 180, 0.55); opacity: 1; }
}
@keyframes maya-ring {
  0%   { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
@keyframes maya-pulse-dot {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.45; }
}
@keyframes maya-live {
  0%   { box-shadow: 0 0 0 0   rgba(244, 113, 124, 0.55); }
  70%  { box-shadow: 0 0 0 8px rgba(244, 113, 124, 0); }
  100% { box-shadow: 0 0 0 0   rgba(244, 113, 124, 0); }
}
@keyframes maya-wave {
  0%, 100% { height: 4px; opacity: 0.5; }
  50%      { height: 14px; opacity: 1;   }
}
@keyframes maya-fade {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* ── Reduced motion ────────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .maya-core-orb,
  .maya-core-ring,
  .maya-live-dot,
  .maya-wave > i,
  .maya-orbit.hot .maya-orbit-dot,
  .maya-fade-in {
    animation: none !important;
  }
}
`;
