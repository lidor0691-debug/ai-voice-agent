// /home/* — Maya Command Center v4 surface CSS (Editorial Bento, private-banking).
// Injected via <style dangerouslySetInnerHTML> from HomeShell.

export const surfaceCss = String.raw`
@import url('https://fonts.googleapis.com/css2?family=Frank+Ruhl+Libre:wght@300;400;500;700&family=Heebo:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  /* ── Morning-fold palette — from the actual clinic at 06:45 ── */
  --canvas:    #f5f0e6;   /* morning-light cream, pinker than Vercel */
  --paper:     #fbf7ee;   /* warm card surface, not white */
  --ink:       #1a1a14;   /* warm black */
  --ink-2:     #3a3729;
  --ink-3:     #76705c;
  --ink-4:     #a8a190;
  --rule:      rgba(26, 26, 20, 0.08);
  --rule-2:    rgba(26, 26, 20, 0.14);

  --eucalyptus: #0f4c3a;  /* the signature recovery green — used ONLY for הוחזר */
  --bronze:     #b08a3e;  /* afternoon-light bronze — eyebrows, accents */
  --sienna:     #c25a2e;  /* burnt orange — vigil active + decision CTA only */

  /* ── Second-fold legacy tokens (unchanged so old classes keep working) ── */
  --bg:        #f5f0e6;
  --bg-tint:   #e9e3d4;
  --line:      rgba(26, 26, 20, 0.08);
  --line-2:    rgba(26, 26, 20, 0.14);
  --forest:    #0e1a14;
  --forest-2:  #16271e;
  --forest-3:  #1f3a2d;
  --cream:     #efe7d0;
  --cream-2:   #c4baa0;
  --gold:      #b08a3e;
  --gold-2:    #8a6b30;
  --gold-soft: #e6d4a8;
  --up:        #4f7a4a;
  --down:      #b04a3a;

  --radius:    22px;
  --radius-sm: 12px;
}

.maya-hebrew {
  font-family: 'Heebo', 'Assistant', 'Rubik', system-ui, sans-serif;
  font-feature-settings: "kern", "liga";
  letter-spacing: 0.005em;
}

.serif { font-family: 'Frank Ruhl Libre', 'Heebo', serif; }
.mono  { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace; font-feature-settings: "tnum"; }
.tnum  { font-feature-settings: "tnum"; font-variant-numeric: tabular-nums; }

/* ── Fullscreen shell ──────────────────────────────────────── */
.maya-shell {
  position: fixed;
  inset: 0;
  z-index: 60;
  overflow-y: auto;
  background: var(--bg);
  color: var(--ink);
  font-family: 'Heebo', 'Assistant', 'Rubik', system-ui, sans-serif;
  font-weight: 400;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* ── APP SHELL — fixed rail + full-bleed canvas ───────────── */
.maya-app {
  position: relative;
  height: 100vh;
  width: 100%;
  overflow: hidden;
}

/* ── Rail (fixed; does not affect canvas flow) ────────────── */
.maya-rail {
  position: fixed;
  top: 0; bottom: 0;
  inset-inline-start: 0;
  width: 168px;
  background: var(--forest);
  color: var(--cream);
  padding: 22px 12px 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  z-index: 5;
}
.maya-rail__brand {
  display: flex; align-items: center; gap: 10px;
  padding: 0 6px;
  margin: 0 0 18px;
}
.maya-rail__logo {
  width: 36px; height: 36px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 700; font-size: 20px;
  color: var(--gold);
  letter-spacing: 0.05em;
  background: rgba(201,168,106,0.10);
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(201,168,106,0.25) inset;
}
.maya-rail__brand-text {
  display: flex; flex-direction: column;
  line-height: 1.1;
  min-width: 0;
}
.maya-rail__brand-name {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--cream);
}
.maya-rail__brand-sub {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(239,231,208,0.50);
  font-weight: 500;
  margin-top: 2px;
}
.maya-rail__nav {
  display: flex; flex-direction: column; gap: 2px;
  width: 100%; flex: 1;
}
.maya-rail__item {
  display: flex; align-items: center; gap: 10px;
  width: 100%;
  height: 38px;
  padding: 0 10px;
  border-radius: 9px;
  color: rgba(239, 231, 208, 0.65);
  cursor: pointer;
  transition: all 180ms ease;
  position: relative;
  background: transparent;
  border: 0;
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  letter-spacing: -0.005em;
  text-align: start;
}
.maya-rail__item-icon {
  display: inline-flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  width: 20px; height: 20px;
}
.maya-rail__item-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.maya-rail__item:hover {
  color: var(--cream);
  background: rgba(239,231,208,0.06);
}
.maya-rail__item.is-active {
  color: var(--gold);
  background: rgba(201,168,106,0.12);
  box-shadow: 0 0 0 1px rgba(201,168,106,0.30) inset;
}
.maya-rail__item.is-active .maya-rail__item-icon { color: var(--gold); }
.maya-rail__item.is-active::before {
  content: "";
  position: absolute;
  top: 8px; bottom: 8px;
  width: 2px;
  background: var(--gold);
  border-radius: 0 2px 2px 0;
  right: -14px;
}
[dir="rtl"] .maya-rail__item.is-active::before {
  right: auto; left: -14px;
  border-radius: 2px 0 0 2px;
}
.maya-rail__item:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.maya-rail__section {
  margin-top: 8px;
  padding-top: 12px;
  border-top: 1px solid rgba(239,231,208,0.10);
}
.maya-rail__badge {
  position: absolute; top: 6px; left: 6px;
  min-width: 18px; height: 18px; padding: 0 5px;
  background: var(--gold); color: var(--forest);
  border-radius: 9px; font-size: 10px; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.maya-rail__divider { height: 1px; background: rgba(239,231,208,0.10); margin: 10px 6px; }
.maya-rail__user {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 8px;
  border-radius: 10px;
  margin-top: 4px;
  background: rgba(239,231,208,0.04);
  border: 1px solid rgba(239,231,208,0.08);
}
.maya-rail__avatar {
  width: 36px; height: 36px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--gold-soft), var(--gold-2));
  display: flex; align-items: center; justify-content: center;
  font-weight: 600; font-size: 14px; color: var(--forest);
  font-family: 'Frank Ruhl Libre', serif;
}
.maya-rail__user-text {
  display: flex; flex-direction: column;
  line-height: 1.2;
  min-width: 0;
  flex: 1;
}
.maya-rail__user-name {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--cream);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.maya-rail__user-role {
  font-size: 10.5px;
  color: rgba(239,231,208,0.55);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  margin-top: 1px;
}

/* ── Canvas — full-bleed, flex column ─────────────────────── */
.maya-canvas {
  padding: 10px clamp(18px, 2.2vw, 32px) 12px;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  min-height: 0;
}
@media (min-width: 1024px) {
  .maya-canvas { padding-inline-start: calc(168px + clamp(20px, 2.4vw, 36px)); }
}

/* ── Top strip — full-width header + KPIs ─────────────────── */
.maya-top {
  display: grid;
  grid-template-columns: minmax(200px, auto) 1fr auto;
  gap: 28px;
  align-items: center;
  padding: 4px 0 16px;
  border-bottom: 1px solid var(--line);
  flex: 0 0 auto;
}
.maya-top__greet {
  display: flex; flex-direction: column; gap: 2px;
  min-width: 0;
}
.maya-top__greet h1 {
  margin: 0;
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 400;
  font-size: 22px;
  line-height: 1.1;
  letter-spacing: -0.01em;
  color: var(--ink);
}
.maya-top__greet h1 strong { font-weight: 600; }
.maya-top__greet .sub {
  font-size: 11.5px;
  color: var(--ink-3);
}
.maya-top__kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border-inline-start: 1px solid var(--line);
  border-inline-end: 1px solid var(--line);
}
.maya-top__kpis .maya-ticker__cell {
  padding: 0 16px;
  gap: 2px;
  position: relative;
}
.maya-top__kpis .maya-ticker__cell + .maya-ticker__cell::before {
  content: ""; position: absolute;
  top: 6px; bottom: 6px; width: 1px; background: var(--line);
  right: 0;
}
[dir="rtl"] .maya-top__kpis .maya-ticker__cell + .maya-ticker__cell::before { right: auto; left: 0; }
.maya-top__kpis .maya-ticker__value { font-size: 22px; font-weight: 500; }
.maya-top__kpis .maya-ticker__label { font-size: 10px; letter-spacing: 0.18em; }
.maya-top__kpis .maya-ticker__cell { padding: 4px 16px 8px; }

.maya-ticker__delta { display: inline-flex; align-items: baseline; gap: 4px; }
.maya-ticker__delta.flat,
.maya-ticker__delta.none {
  color: var(--ink-3);
  font-weight: 500;
}
.maya-ticker__delta.none { font-style: italic; opacity: 0.75; }
.maya-ticker__delta.up   { color: var(--up); }
.maya-ticker__delta.down { color: var(--down); }

/* Honest direction indicator — 2px baseline whose color signals dir.
   It does NOT represent magnitude or time-series; only sign of the real delta. */
.maya-ticker__indicator {
  margin-top: 8px;
  height: 2px;
  width: 100%;
  border-radius: 2px;
  background: var(--rule);
  position: relative;
  overflow: hidden;
}
.maya-ticker__indicator span {
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.maya-ticker__indicator.dir-up   span { background: linear-gradient(90deg, transparent, var(--up) 70%); }
.maya-ticker__indicator.dir-down span { background: linear-gradient(90deg, transparent, var(--down) 70%); }
.maya-ticker__indicator.dir-flat span { background: var(--rule-2); }
[dir="rtl"] .maya-ticker__indicator.dir-up   span { background: linear-gradient(-90deg, transparent, var(--up) 70%); }
[dir="rtl"] .maya-ticker__indicator.dir-down span { background: linear-gradient(-90deg, transparent, var(--down) 70%); }
.maya-top__right {
  display: flex; align-items: center; gap: 16px;
  flex-shrink: 0;
}

/* ── Body — 3-column command grid filling viewport ────────── */
.maya-body {
  display: grid;
  grid-template-columns: minmax(300px, 1fr) minmax(0, 2fr) minmax(300px, 1fr);
  gap: 18px;
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
}
.maya-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}
.maya-col::-webkit-scrollbar { width: 4px; }
.maya-col::-webkit-scrollbar-thumb { background: var(--rule-2); border-radius: 4px; }
.maya-col::-webkit-scrollbar-track { background: transparent; }
.maya-col--mid { gap: 14px; }
/* Side columns: cards share available height equally with internal scroll */
.maya-col .maya-card {
  min-height: 0;
  flex: 1 1 0;
}
/* Center column: hero owns most height; revenue + dock are intrinsic-sized */
.maya-col--mid > .maya-hero {
  flex: 0 1 auto;
  max-height: min(560px, 56vh);
  display: flex; flex-direction: column;
}
.maya-col--mid > .maya-rev,
.maya-col--mid > .maya-dock { flex: 0 0 auto; }
.maya-col--mid > .maya-dock { margin-top: auto; }
.maya-col--mid > .maya-hero .maya-hero__decision { flex: 1 1 auto; min-height: 0; }
.maya-col--mid > .maya-hero .maya-hero__lead { justify-content: flex-start; }
.maya-col--mid > .maya-hero .maya-reco { justify-content: space-between; }
.maya-col--mid { justify-content: flex-start; }
@media (max-width: 1180px) {
  .maya-body { grid-template-columns: 1fr; overflow-y: auto; }
}

/* ── Header strip ─────────────────────────────────────────── */
.maya-header {
  display: flex; align-items: flex-end; justify-content: space-between;
  gap: 24px;
  padding-bottom: 10px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
}
.maya-header h1 {
  margin: 0;
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 300;
  font-size: clamp(26px, 2.6vw, 32px);
  letter-spacing: -0.01em;
  line-height: 1.1;
  color: var(--ink);
}
.maya-header h1 strong { font-weight: 500; color: var(--ink); }
.maya-header__sub { margin-top: 6px; color: var(--ink-3); font-size: 14px; letter-spacing: 0.01em; }
.maya-header__meta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.maya-pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 14px;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 13px;
  color: var(--ink-2);
  cursor: pointer;
  transition: border-color 180ms;
}
.maya-pill:hover { border-color: var(--line-2); }
.maya-pill .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--gold); }
.maya-pill .kbd {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 2px 6px;
  background: var(--bg);
  border-radius: 5px;
  color: var(--ink-2);
}

/* ── HERO — single morning decision block ────────────────── */
.maya-hero {
  background: var(--forest);
  background-image:
    radial-gradient(ellipse 70% 50% at 100% 0%, rgba(201,168,106,0.18), transparent 65%),
    radial-gradient(ellipse 90% 60% at 0% 100%, rgba(201,168,106,0.08), transparent 60%);
  color: var(--cream);
  border-radius: 18px;
  padding: 26px clamp(28px, 3.5vw, 48px) 28px;
  position: relative;
  overflow: hidden;
  width: 100%;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.05) inset,
    0 28px 56px -30px rgba(14,26,20,0.60),
    0 12px 24px -16px rgba(14,26,20,0.38);
}
.maya-hero::before {
  content: "";
  position: absolute; top: 0; right: 0; left: 0; height: 3px;
  background: linear-gradient(90deg, transparent 5%, var(--gold) 50%, transparent 95%);
  opacity: 0.95;
  filter: blur(0.2px);
}
.maya-hero::after {
  content: "";
  position: absolute; inset: 0;
  pointer-events: none;
  border-radius: inherit;
  box-shadow: 0 0 0 1px rgba(201,168,106,0.10) inset;
}
.maya-hero__head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 18px; margin-bottom: 16px;
}
.maya-hero__meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.maya-hero__label {
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--gold);
  font-weight: 600;
}
.maya-hero__metasub { font-size: 12px; color: var(--cream-2); }
.maya-hero__sep { width: 3px; height: 3px; border-radius: 50%; background: rgba(239,231,208,0.25); }
.maya-hero__status {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px;
  background: transparent;
  border: 1px solid rgba(201,168,106,0.30);
  border-radius: 999px;
  font-size: 11px;
  color: var(--cream-2);
  letter-spacing: 0.04em;
}
.maya-hero__decision {
  display: grid;
  grid-template-columns: 1.35fr 1fr;
  gap: 36px;
  align-items: stretch;
}
@media (max-width: 1180px) { .maya-hero__decision { grid-template-columns: 1fr; gap: 22px; } }

.maya-hero__lead { display: flex; flex-direction: column; gap: 18px; }
.maya-hero__headline {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 500;
  font-size: clamp(30px, 3vw, 40px);
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: #f5ecd2;
  margin: 0;
  text-wrap: balance;
  max-width: 820px;
}
.maya-hero__headline em {
  font-style: normal;
  font-weight: 500;
  color: var(--gold);
}
.maya-hero__impact {
  display: flex; align-items: baseline; gap: 14px;
  padding: 12px 0 14px;
  border-top: 1px solid rgba(239,231,208,0.10);
  border-bottom: 1px solid rgba(239,231,208,0.10);
}
.maya-hero__impact-l {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--cream-2);
  font-weight: 500;
}
.maya-hero__impact-v {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 500;
  font-size: clamp(48px, 5vw, 68px);
  line-height: 0.92;
  letter-spacing: -0.04em;
  color: var(--gold);
  font-feature-settings: "tnum";
  margin-inline-start: auto;
  text-shadow: 0 1px 0 rgba(0,0,0,0.20);
}
.maya-hero__impact-v .cur { font-size: 0.55em; opacity: 0.9; margin-inline-end: 0.06em; }

.maya-sit { display: flex; flex-direction: column; }
.maya-sit__row {
  display: grid;
  grid-template-columns: 20px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 8px 0;
  font-size: 13px;
  color: var(--cream-2);
  border-top: 1px dashed rgba(239,231,208,0.08);
}
.maya-sit__row:first-child { border-top: 0; }
.maya-sit__pip {
  width: 18px; height: 18px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 600;
  background: rgba(201,168,106,0.10);
  color: var(--gold);
  border: 1px solid rgba(201,168,106,0.25);
}
.maya-sit__row.is-priority { color: var(--cream); }
.maya-sit__row.is-priority .maya-sit__pip { background: var(--gold); color: var(--forest); border-color: var(--gold); }
.maya-sit__meta { color: var(--gold); font-size: 12px; font-feature-settings: "tnum"; }

/* Reco panel (right column) */
.maya-reco {
  background: linear-gradient(160deg, rgba(201,168,106,0.10), rgba(201,168,106,0.04));
  border: 1px solid rgba(201,168,106,0.28);
  border-radius: 14px;
  padding: 18px 22px;
  display: flex; flex-direction: column;
  position: relative;
}
.maya-reco__why { margin-bottom: 14px; }
.maya-reco__label {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 10px;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  color: var(--gold);
  font-weight: 600;
  margin-bottom: 8px;
}
.maya-reco__label::before { content: ""; width: 14px; height: 1px; background: var(--gold); }
.maya-reco__title {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 500;
  font-size: 19px;
  line-height: 1.28;
  color: #f5ecd2;
  margin: 0 0 8px;
  text-wrap: balance;
}
.maya-reco__sub {
  font-size: 12.5px;
  color: var(--cream-2);
  line-height: 1.5;
  margin-bottom: 14px;
}
.maya-reco__why { margin-bottom: 14px; }
.maya-reco__why {
  list-style: none;
  margin: 0 0 18px;
  padding: 0;
  display: flex; flex-direction: column; gap: 6px;
}
.maya-reco__why li {
  display: flex; gap: 8px; align-items: flex-start;
  font-size: 12.5px; color: var(--cream-2); line-height: 1.55;
}
.maya-reco__why li::before {
  content: ""; margin-top: 7px; width: 4px; height: 4px; border-radius: 50%;
  background: var(--gold); flex: 0 0 4px;
}

/* CTA button (gold) — used inside hero */
.maya-cta {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%;
  padding: 14px 22px;
  background: linear-gradient(180deg, #dabb7b 0%, #c19c52 100%);
  color: var(--forest);
  border: 0;
  border-radius: 12px;
  font: inherit;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.005em;
  cursor: pointer;
  transition: transform 200ms ease, box-shadow 200ms ease, background 200ms ease;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.45) inset,
    0 0 0 1px rgba(138,107,48,0.55) inset,
    0 10px 22px -10px rgba(201,168,106,0.80),
    0 0 0 5px rgba(201,168,106,0.12);
}
.maya-cta:hover:not(:disabled) {
  background: #d4b577;
  transform: translateY(-1px);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.25) inset,
    0 10px 24px -8px rgba(201,168,106,0.7),
    0 0 0 8px rgba(201,168,106,0.14);
}
.maya-cta:disabled { opacity: 0.55; cursor: not-allowed; }
.maya-cta__arrow {
  display: inline-flex; align-items: center; justify-content: center;
  width: 26px; height: 26px;
  border-radius: 50%;
  background: var(--forest);
  color: var(--gold);
}
.maya-reco__secondary {
  margin-top: 12px;
  background: transparent;
  border: 0;
  color: var(--cream-2);
  font: inherit;
  font-size: 12.5px;
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-color: rgba(239,231,208,0.25);
  align-self: center;
  cursor: pointer;
  padding: 6px;
}
.maya-reco__secondary:hover { color: var(--cream); text-decoration-color: var(--gold); }
.maya-reco__secondary:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Maya orb — demoted to small status mark ──────────────── */
.maya-orb {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, var(--cream) 0%, var(--gold-soft) 40%, var(--gold) 100%);
  box-shadow:
    inset 0 0 0 1px rgba(255,255,255,0.4),
    0 0 0 4px rgba(201,168,106,0.10);
  position: relative; flex-shrink: 0;
}
.maya-orb::after {
  content: "";
  position: absolute; inset: 2px;
  border-radius: 50%;
  background: radial-gradient(circle at 60% 30%, rgba(255,255,255,0.5), transparent 50%);
  animation: maya-orb-breath 4s ease-in-out infinite;
}
@keyframes maya-orb-breath {
  0%, 100% { opacity: 0.7; transform: scale(1); }
  50%      { opacity: 1;   transform: scale(1.05); }
}

/* ── Revenue mini (chart + this-month) ────────────────────── */
.maya-rev {
  display: grid;
  grid-template-columns: 1.05fr 1.4fr;
  gap: 24px;
  align-items: center;
  background: #fffdf7;
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 22px;
  margin-top: 0;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.6) inset,
    0 1px 2px rgba(20,19,14,0.03),
    0 8px 24px -18px rgba(20,19,14,0.18);
}
@media (max-width: 900px) { .maya-rev { grid-template-columns: 1fr; } }
.maya-rev__left {
  display: flex; flex-direction: column; gap: 6px;
  border-inline-start: 1px solid var(--line);
  padding-inline-start: 24px;
}
.maya-rev__label {
  font-size: 10px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 600;
}
.maya-rev__row { display: flex; align-items: baseline; gap: 14px; }
.maya-rev__value {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 500;
  font-size: 32px;
  line-height: 1;
  letter-spacing: -0.03em;
  color: var(--ink);
  font-feature-settings: "tnum";
}
.maya-rev__value .cur { font-size: 0.55em; color: var(--gold-2); margin-inline-end: 0.08em; }
.maya-rev__delta {
  display: inline-flex; align-items: baseline; gap: 4px;
  font-size: 13px; font-weight: 500;
  color: var(--up);
  font-feature-settings: "tnum";
}
.maya-rev__compare { font-size: 12px; color: var(--ink-3); }
.maya-rev__compare strong { color: var(--ink-2); font-weight: 500; }
.maya-rev__chart { height: 72px; position: relative; }
.maya-rev__chart svg { width: 100%; height: 100%; display: block; }
.maya-rev__chart--empty {
  display: flex; align-items: center;
  border: 1px dashed var(--line-2);
  border-radius: 10px;
  padding: 10px 14px;
  background: rgba(26,26,20,0.015);
}
.maya-rev__empty-title {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 14px;
  font-weight: 500;
  color: var(--ink-2);
  line-height: 1.2;
}
.maya-rev__empty-sub {
  font-size: 11.5px;
  color: var(--ink-3);
  margin-top: 4px;
  line-height: 1.4;
}
.maya-rev__delta.is-down { color: var(--down); }

/* ── KPI ticker strip ─────────────────────────────────────── */
.maya-ticker {
  margin: 10px 0 4px;
  padding: 10px 8px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  position: relative;
}
.maya-ticker__spark { margin-top: 4px; height: 14px; }
.maya-ticker__cell { gap: 2px; padding: 0 18px; }
.maya-ticker__label { font-size: 10px; }
@media (max-width: 1180px) {
  .maya-ticker { grid-template-columns: repeat(2, 1fr); row-gap: 18px; }
  .maya-ticker__cell:nth-child(3)::before { display: none; }
}
@media (max-width: 720px) {
  .maya-ticker { grid-template-columns: 1fr; }
  .maya-ticker__cell + .maya-ticker__cell::before { display: none; }
}
.maya-ticker__cell {
  padding: 0 22px;
  position: relative;
  display: flex; flex-direction: column;
  gap: 4px;
}
.maya-ticker__cell + .maya-ticker__cell::before {
  content: ""; position: absolute;
  top: 6px; bottom: 6px; width: 1px; background: var(--line);
  right: 0;
}
[dir="rtl"] .maya-ticker__cell + .maya-ticker__cell::before { right: auto; left: 0; }
.maya-ticker__label {
  font-size: 11px;
  letter-spacing: 0.14em;
  color: var(--ink-3);
  text-transform: uppercase;
  font-weight: 500;
}
.maya-ticker__row { display: flex; align-items: baseline; gap: 10px; margin-top: 2px; }
.maya-ticker__value {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 500;
  font-size: 24px;
  letter-spacing: -0.02em;
  color: var(--ink);
  line-height: 1;
  font-feature-settings: "tnum";
}
.maya-ticker__value .unit { font-size: 18px; color: var(--ink-3); margin-inline-end: 2px; font-weight: 300; }
.maya-ticker__delta { font-size: 12px; font-weight: 500; font-feature-settings: "tnum"; }
.maya-ticker__delta.up   { color: var(--up); }
.maya-ticker__delta.down { color: var(--down); }
.maya-ticker__spark { margin-top: 6px; height: 22px; }
.maya-ticker__spark svg { display: block; width: 100%; height: 100%; }

/* ── Bottom grid + cards ──────────────────────────────────── */
.maya-bottom {
  display: grid;
  grid-template-columns: 1.1fr 1.2fr 1fr;
  gap: 12px;
  align-items: stretch;
  margin-top: 10px;
}
@media (max-width: 1180px) { .maya-bottom { grid-template-columns: 1fr; } }

.maya-card {
  background: var(--paper);
  border: 1px solid var(--line-2);
  border-radius: 16px;
  padding: 18px 22px;
  display: flex; flex-direction: column;
  min-width: 0;
  position: relative;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.70) inset,
    0 1px 2px rgba(20,19,14,0.04),
    0 12px 26px -18px rgba(20,19,14,0.24);
  transition: box-shadow 200ms ease, transform 200ms ease;
}
/* "System is working" status dot — top-end corner of every card */
.maya-card::after {
  content: "";
  position: absolute;
  top: 14px;
  inset-inline-end: 14px;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--up);
  box-shadow: 0 0 0 0 rgba(79,122,74, 0.45);
  animation: maya-card-pulse 2.6s ease-out infinite;
  pointer-events: none;
}
@keyframes maya-card-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(79,122,74, 0.45); }
  70%  { box-shadow: 0 0 0 6px rgba(79,122,74, 0); }
  100% { box-shadow: 0 0 0 0   rgba(79,122,74, 0); }
}
.maya-card:hover {
  box-shadow:
    0 1px 0 rgba(255,255,255,0.75) inset,
    0 2px 4px rgba(20,19,14,0.05),
    0 18px 36px -20px rgba(20,19,14,0.30);
}
/* Ghost row — visible placeholder when a panel has no real data. */
.maya-ghost-row {
  display: grid;
  grid-template-columns: 30px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 11px 0;
  border-top: 1px dashed var(--rule);
  font-size: 12.5px;
  color: var(--ink-4);
  font-style: italic;
}
.maya-ghost-row:first-child { border-top: 0; }
.maya-ghost-row__avatar {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: var(--bg-tint);
  border: 1px dashed var(--rule-2);
  flex-shrink: 0;
}
.maya-ghost-row__meta {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  color: var(--ink-4);
  letter-spacing: 0.04em;
}
.maya-card__head {
  display: flex; justify-content: space-between; align-items: baseline;
  gap: 12px;
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line-2);
}
.maya-card__title {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 600;
  font-size: 18px;
  letter-spacing: -0.015em;
  color: var(--ink);
  display: inline-flex;
  align-items: center;
  gap: 8px;
  line-height: 1.2;
}
.maya-card__live-dot {
  display: inline-block;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--up);
  box-shadow: 0 0 0 0 rgba(79,122,74, 0.55);
  animation: maya-card-pulse 2.6s ease-out infinite;
}
.maya-card__title-sub {
  font-size: 11.5px;
  color: var(--ink-3);
  margin-inline-start: 6px;
  font-family: 'Heebo', system-ui, sans-serif;
  font-weight: 400;
  letter-spacing: 0;
}

/* ── Panel patterns — rich card internals ─────────────────── */

/* Hero-stat: big numeric anchor at the top of a panel (e.g. "9 פגישות מתוכננות") */
.maya-stat {
  display: flex; align-items: baseline; gap: 10px;
  margin: 4px 0 14px;
}
.maya-stat__v {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 500;
  font-size: 34px;
  line-height: 0.95;
  letter-spacing: -0.02em;
  color: var(--ink);
  font-feature-settings: "tnum";
}
.maya-stat__l { font-size: 12.5px; color: var(--ink-3); line-height: 1.4; }

/* Dashed-divided list (today schedule, handled today, voice calls, whatsapp) */
.maya-list { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; overflow-y: auto; }
.maya-list__row {
  display: grid;
  gap: 12px;
  align-items: center;
  padding: 10px 0;
  border-top: 1px dashed var(--rule);
  position: relative;
}
.maya-list__row:first-child { border-top: 0; padding-top: 4px; }
.maya-list__row:last-child { padding-bottom: 4px; }

/* Schedule row layout: time | content | tag */
.maya-list__row--schedule { grid-template-columns: 56px 1fr auto; }
.maya-list__time {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
  font-feature-settings: "tnum";
}
.maya-list__time.is-now { color: var(--gold-2); font-weight: 600; }
.maya-list__name {
  font-size: 14px;
  font-weight: 500;
  color: var(--ink);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.maya-list__sub { font-size: 11.5px; color: var(--ink-3); margin-top: 1px; }
.maya-list__row.is-now-line { border-top: 1px solid var(--gold) !important; padding-top: 8px; }
.maya-list__row.is-now-line::after {
  content: "עכשיו";
  position: absolute; top: -8px; inset-inline-start: 0;
  font-size: 9.5px;
  background: var(--gold); color: var(--forest);
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

/* Status tag pills */
.maya-tag {
  font-size: 10px;
  padding: 3px 9px;
  border-radius: 4px;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
}
.maya-tag--ok    { background: rgba(79,122,74,0.12); color: var(--up); }
.maya-tag--wait  { background: rgba(201,168,106,0.18); color: var(--gold-2); }
.maya-tag--new   { background: var(--forest); color: var(--cream); }
.maya-tag--risk  { background: rgba(176,74,58,0.12); color: var(--down); }

/* Funnel row (lead pipeline) — label / bar / value */
.maya-funnel { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
.maya-funnel-row {
  display: grid;
  grid-template-columns: 1fr 90px auto;
  gap: 16px;
  align-items: center;
  padding: 13px 0;
  border-top: 1px solid var(--rule);
}
.maya-funnel-row:first-child { border-top: 0; }
.maya-funnel-row__label .name { font-size: 15px; font-weight: 600; color: var(--ink); }
.maya-funnel-row__label .sub  { font-size: 12.5px; color: var(--ink-2); margin-top: 3px; }
.maya-funnel-row__bar {
  width: 100%; height: 5px;
  background: var(--bg-tint);
  border-radius: 999px;
  overflow: hidden;
  position: relative;
}
.maya-funnel-row__bar i {
  display: block;
  height: 100%;
  background: var(--forest);
  border-radius: 999px;
}
.maya-funnel-row.is-down .maya-funnel-row__bar i { background: var(--cream-2); }
.maya-funnel-row__val {
  display: flex; align-items: baseline; gap: 8px;
  justify-content: flex-end;
}
.maya-funnel-row__val .v {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 23px;
  font-weight: 600;
  color: var(--ink);
  font-feature-settings: "tnum";
  line-height: 1;
}

/* Activity feed row — icon circle | title+sub | time */
.maya-act-row {
  display: grid;
  grid-template-columns: 34px 1fr auto;
  gap: 14px;
  align-items: flex-start;
  padding: 13px 0;
  border-top: 1px solid var(--rule);
}
.maya-act-row:first-child { border-top: 0; padding-top: 4px; }
.maya-act-row__icon {
  width: 34px; height: 34px;
  border-radius: 50%;
  background: var(--bg-tint);
  color: var(--ink-2);
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 0 0 1px var(--rule-2) inset;
}
.maya-act-row__icon.tone-payment  { background: var(--forest); color: var(--gold); }
.maya-act-row__icon.tone-message  { background: var(--gold-soft); color: var(--gold-2); }
.maya-act-row__icon.tone-meeting  { background: var(--forest-3); color: var(--cream); }
.maya-act-row__icon.tone-alert    { background: rgba(176,74,58,0.15); color: var(--down); }
.maya-act-row__icon.tone-win      { background: rgba(79,122,74,0.15); color: var(--up); }
.maya-act-row__title { font-size: 15px; font-weight: 600; color: var(--ink); line-height: 1.3; }
.maya-act-row__sub   { font-size: 13px; color: var(--ink-2); margin-top: 3px; line-height: 1.45; }
.maya-act-row__time {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11.5px;
  color: var(--ink-3);
  white-space: nowrap;
  font-feature-settings: "tnum";
  font-weight: 500;
}

/* Voice / WhatsApp row variant — avatar + content + meta */
.maya-comm-row {
  display: grid;
  grid-template-columns: 34px 1fr auto;
  gap: 14px;
  align-items: center;
  padding: 13px 0;
  border-top: 1px solid var(--rule);
  width: 100%;
  text-align: start;
  background: transparent;
  border-inline: 0; border-bottom: 0;
}
.maya-comm-row:first-child { border-top: 0; }
.maya-comm-row__avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--forest-2), var(--forest));
  color: var(--gold);
  display: flex; align-items: center; justify-content: center;
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 14px; font-weight: 700;
  flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(201,168,106, 0.18) inset;
}
.maya-comm-row__avatar.tone-human {
  background: linear-gradient(135deg, var(--gold-soft), var(--bronze));
  color: var(--forest);
}
/* Color-rotated avatar tones so rows of people feel like people, not duplicates */
.maya-comm-row:nth-child(3n+1) .maya-comm-row__avatar { background: linear-gradient(135deg, var(--gold-soft), var(--bronze)); color: var(--forest); }
.maya-comm-row:nth-child(3n+2) .maya-comm-row__avatar { background: linear-gradient(135deg, var(--forest-2), var(--forest)); color: var(--gold); }
.maya-comm-row:nth-child(3n)   .maya-comm-row__avatar { background: linear-gradient(135deg, rgba(15,76,58,0.85), var(--eucalyptus)); color: var(--cream); }
.maya-comm-row__name { font-size: 15px; font-weight: 600; color: var(--ink); }
.maya-comm-row__sub  { font-size: 13px; color: var(--ink-2); margin-top: 3px; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; }
.maya-comm-row__meta {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: var(--ink-2);
  font-feature-settings: "tnum";
  white-space: nowrap;
  font-weight: 500;
}
.maya-comm-row__live-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--down);
  box-shadow: 0 0 0 0 rgba(176,74,58, 0.55);
  animation: maya-live 1.6s ease-out infinite;
}

/* Card footer — bottom action strip */
.maya-card__foot {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--rule);
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px;
  color: var(--ink-3);
}
.maya-card__foot a {
  color: var(--ink);
  font-weight: 500;
  text-decoration: none;
  display: inline-flex; align-items: center; gap: 4px;
}
.maya-card__foot a:hover { color: var(--gold-2); }
.maya-card__action {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 700;
  text-decoration: none;
  cursor: pointer;
  background: rgba(201,168,106, 0.10);
  border: 1px solid rgba(201,168,106, 0.30);
  padding: 4px 9px;
  border-radius: 999px;
}
.maya-card__action:hover { color: var(--gold-2); background: rgba(201,168,106, 0.15); }

/* ── Section label (mono uppercase) — back-compat alias ──── */
.maya-section-label {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--gold-2);
}

/* ── Talk-to-Maya dock — restyled ─────────────────────────── */
.maya-dock {
  background: #fffdf7;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px 14px;
  display: flex; flex-direction: column; gap: 6px;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.6) inset,
    0 1px 2px rgba(20,19,14,0.03),
    0 8px 18px -18px rgba(20,19,14,0.22);
}

/* ── Entry animation ──────────────────────────────────────── */
.maya-fade-in { animation: maya-fade 480ms cubic-bezier(0.2, 0.8, 0.2, 1) both; }
@keyframes maya-fade { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

/* ── Live dot + tone bar (kept from legacy) ────────────────── */
.maya-live-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--down);
  box-shadow: 0 0 0 0 rgba(176,74,58, 0.55);
  animation: maya-live 1.6s ease-out infinite;
}
@keyframes maya-live {
  0%   { box-shadow: 0 0 0 0   rgba(176,74,58, 0.55); }
  70%  { box-shadow: 0 0 0 8px rgba(176,74,58, 0); }
  100% { box-shadow: 0 0 0 0   rgba(176,74,58, 0); }
}
.maya-tone-bar {
  position: absolute;
  inset-inline-start: 0; top: 0; bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, var(--gold), var(--forest));
  border-start-start-radius: inherit;
  border-end-start-radius: inherit;
}

/* ── Wave + footer ────────────────────────────────────────── */
.maya-wave { display: inline-flex; align-items: flex-end; gap: 2px; height: 16px; }
.maya-wave > i { width: 2px; background: currentColor; border-radius: 1px; animation: maya-wave 0.9s ease-in-out infinite; }
.maya-wave > i:nth-child(1) { animation-delay: -0.0s; }
.maya-wave > i:nth-child(2) { animation-delay: -0.15s; }
.maya-wave > i:nth-child(3) { animation-delay: -0.3s; }
.maya-wave > i:nth-child(4) { animation-delay: -0.45s; }
.maya-wave > i:nth-child(5) { animation-delay: -0.6s; }
@keyframes maya-wave { 0%,100% { height: 4px; opacity: 0.5; } 50% { height: 14px; opacity: 1; } }

.maya-foot {
  margin-top: 36px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
  display: flex; justify-content: space-between; align-items: center;
  font-size: 11px;
  color: var(--ink-4);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.maya-foot__brand { display: inline-flex; align-items: center; gap: 8px; }
.maya-foot__brand .spark { color: var(--gold); }

/* ── Legacy maya-core (orb radar) — kept for back-compat ──── */
.maya-core { position: relative; aspect-ratio: 1 / 1; display: grid; place-items: center; }
.maya-core-orb {
  width: 38%;
  aspect-ratio: 1 / 1;
  border-radius: 50%;
  background: radial-gradient(circle at 32% 32%, var(--cream), var(--gold-soft) 38%, rgba(201,168,106,0) 70%);
  box-shadow: 0 0 60px rgba(201,168,106, 0.30), inset 0 0 40px rgba(201,168,106, 0.35);
  animation: maya-core-breath 5.6s ease-in-out infinite;
}
@keyframes maya-core-breath {
  0%, 100% { box-shadow: 0 0 60px rgba(201,168,106,0.30), inset 0 0 40px rgba(201,168,106,0.35); opacity: 0.95; }
  50%      { box-shadow: 0 0 96px rgba(201,168,106,0.45), inset 0 0 56px rgba(201,168,106,0.50); opacity: 1; }
}
.maya-core-ring { position: absolute; border-radius: 50%; border: 1px solid rgba(168,136,75,0.20); pointer-events: none; }
.maya-core-ring.r1 { inset: 8%;  animation: maya-core-ring 9s linear infinite; }
.maya-core-ring.r2 { inset: 22%; animation: maya-core-ring 14s linear infinite reverse; opacity: 0.7; }
.maya-core-ring.r3 { inset: 36%; animation: maya-core-ring 7s linear infinite; opacity: 0.5; }
@keyframes maya-core-ring { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

.maya-orbit {
  position: absolute;
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid rgba(230,220,203,0.9);
  background: rgba(255,252,246,0.85);
  backdrop-filter: blur(6px);
  font-size: 11px; white-space: nowrap;
  transform: translate(-50%, -50%);
  color: var(--ink);
  box-shadow: 0 1px 2px rgba(11,23,20,0.04);
}
.maya-orbit.hot  { border-color: rgba(176,74,58, 0.6);  box-shadow: 0 0 18px rgba(176,74,58, 0.20); }
.maya-orbit.warm { border-color: rgba(201,168,106,0.50); box-shadow: 0 0 14px rgba(201,168,106,0.15); }
.maya-orbit.cool { border-color: rgba(168,136,75, 0.35); }
.maya-orbit-dot  { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.maya-orbit.hot  .maya-orbit-dot { color: var(--down); animation: maya-pulse-dot 1.6s ease-in-out infinite; }
.maya-orbit.warm .maya-orbit-dot { color: var(--gold); }
.maya-orbit.cool .maya-orbit-dot { color: var(--gold-2); }
@keyframes maya-pulse-dot { 0%,100% { opacity: 1; } 50% { opacity: 0.45; } }

/* ═══════════════════════════════════════════════════════════════
   HYBRID COMMAND BRIEFING — Maya talks first, system right below
   ═══════════════════════════════════════════════════════════════ */

/* ── Byline — "── מאיה · date · time ──" newspaper masthead ── */
.maya-byline {
  display: flex; align-items: center; gap: 12px;
  margin: 2px 0 6px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 600;
}
.maya-byline__label { flex-shrink: 0; }
.maya-byline::after {
  content: "";
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, rgba(176,138,62,0.45), transparent);
}
[dir="rtl"] .maya-byline::after {
  background: linear-gradient(-90deg, rgba(176,138,62,0.45), transparent);
}

/* ── Greeting line (single line, recovered amount embedded) ── */
.maya-greet-line {
  margin: 0 0 14px;
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 400;
  font-size: clamp(20px, 2vw, 26px);
  line-height: 1.3;
  letter-spacing: -0.01em;
  color: var(--ink-2);
}
.maya-greet-line strong { font-weight: 600; color: var(--ink); }
.maya-greet-line .recovered {
  font-weight: 600;
  color: var(--eucalyptus);
  font-feature-settings: "tnum";
  letter-spacing: -0.015em;
}

/* ── Briefing zone — ONE premium surface (greeting + decision + sidecol) ── */
.maya-briefing-zone {
  position: relative;
  background:
    linear-gradient(180deg, rgba(201,168,106,0.04) 0%, transparent 18%),
    var(--paper);
  border: 1px solid rgba(176,138,62, 0.38);
  border-radius: 22px;
  padding: 0;
  margin-bottom: 14px;
  flex: 0 0 auto;
  overflow: hidden;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.70) inset,
    0 30px 64px -30px rgba(20,19,14,0.36),
    0 12px 26px -14px rgba(20,19,14,0.14),
    0 0 0 1px rgba(201,168,106,0.10);
}
/* Gold hairline across the very top */
.maya-briefing-zone::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent 6%, var(--bronze) 50%, transparent 94%);
  opacity: 0.9;
}

.maya-briefing-zone__head {
  padding: 14px 28px 12px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid var(--rule);
  background: linear-gradient(180deg, rgba(201,168,106,0.07), transparent);
  flex-wrap: wrap;
}
.maya-briefing-zone__greet {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: clamp(22px, 2.2vw, 28px);
  line-height: 1.18;
  letter-spacing: -0.02em;
  color: var(--ink);
  font-weight: 500;
  margin: 0;
  flex: 1; min-width: 0;
}
.maya-briefing-zone__greet strong { color: var(--ink); font-weight: 700; }
.maya-briefing-zone__greet .recovered {
  font-weight: 700;
  color: var(--eucalyptus);
  font-feature-settings: "tnum";
  padding: 0 4px;
}
.maya-briefing-zone__eyebrow {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 700;
  display: inline-flex; align-items: center; gap: 8px;
  flex-shrink: 0;
}
.maya-briefing-zone__eyebrow .dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--eucalyptus);
  box-shadow: 0 0 0 0 rgba(15,76,58, 0.45);
  animation: maya-counter-pulse 2.0s ease-out infinite;
}

.maya-briefing-zone__body {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.maya-briefing-zone__body > .maya-decision {
  border: 0;
  background:
    radial-gradient(ellipse 80% 60% at 100% 0%, rgba(201,168,106,0.08), transparent 65%),
    linear-gradient(180deg, rgba(255,253,247,0.85) 0%, rgba(245,240,230,0.50) 100%);
  border-radius: 0;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.55) inset,
    0 -1px 0 rgba(176,138,62, 0.10) inset;
  padding: 16px 30px 18px;
  padding-inline-start: 50px;
  gap: 12px;
  position: relative;
}
.maya-briefing-zone__body > .maya-decision::before {
  top: 22px; bottom: 22px;
  inset-inline-start: 22px;
  width: 5px;
}

/* ── Briefing follow-up row — Night log + Day rhythm ──────── */
.maya-briefing-zone__followup {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 0;
  border-top: 1px solid rgba(176,138,62, 0.22);
  background: linear-gradient(180deg, rgba(15,76,58,0.025) 0%, transparent 70%);
}
@media (max-width: 1180px) {
  .maya-briefing-zone__followup { grid-template-columns: 1fr; }
}
.maya-briefing-zone__followup__block {
  padding: 12px 28px 14px;
  min-width: 0;
  display: flex; flex-direction: column;
  gap: 8px;
  position: relative;
}
.maya-briefing-zone__followup__block + .maya-briefing-zone__followup__block {
  border-inline-start: 1px solid var(--rule);
}
@media (max-width: 1180px) {
  .maya-briefing-zone__followup__block + .maya-briefing-zone__followup__block {
    border-inline-start: 0;
    border-top: 1px solid var(--rule);
  }
}
.maya-briefing-zone__followup__title {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 15.5px;
  letter-spacing: -0.012em;
  text-transform: none;
  color: var(--ink);
  font-weight: 600;
  display: inline-flex; align-items: center; gap: 10px;
}
.maya-briefing-zone__followup__title::before {
  content: "";
  width: 18px; height: 2px;
  background: linear-gradient(90deg, var(--bronze), transparent);
  border-radius: 2px;
}
[dir="rtl"] .maya-briefing-zone__followup__title::before {
  background: linear-gradient(-90deg, var(--bronze), transparent);
}

/* Constrain the decision quote so it stays scannable at full briefing width */
.maya-briefing-zone__body > .maya-decision .maya-decision__quote { max-width: 560px; }

/* ── The Decision — premium card, split body + full-width CTA ── */
.maya-decision {
  position: relative;
  background: var(--paper);
  border: 1px solid rgba(176,138,62, 0.34);
  border-radius: 20px;
  padding: 28px 32px 24px;
  padding-inline-start: 44px;
  display: flex; flex-direction: column; gap: 20px;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.70) inset,
    0 28px 60px -28px rgba(20,19,14,0.35),
    0 10px 22px -12px rgba(20,19,14,0.12),
    0 0 0 1px rgba(201,168,106,0.08);
}
.maya-decision::before {
  content: "";
  position: absolute;
  inset-inline-start: 16px;
  top: 30px; bottom: 30px;
  width: 4px;
  border-radius: 4px;
  background: linear-gradient(180deg, var(--bronze) 0%, var(--forest-3) 100%);
}

/* Split internal layout: lead (avatar + quote) | recommendation */
.maya-decision__body {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  width: 100%;
}
.maya-decision__body > * {
  max-width: 720px;
}
.maya-decision__lead {
  display: flex; gap: 16px;
  align-items: center;
  min-width: 0;
}
.maya-decision__avatar {
  width: 58px; height: 58px;
  flex-shrink: 0;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--gold-soft), var(--bronze));
  color: var(--forest);
  display: flex; align-items: center; justify-content: center;
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 700;
  font-size: 23px;
  letter-spacing: -0.02em;
  box-shadow:
    0 0 0 1px rgba(176,138,62,0.50) inset,
    0 0 0 7px rgba(201,168,106,0.10),
    0 12px 24px -10px rgba(176,138,62,0.55);
}
.maya-decision__lead-body {
  display: flex; flex-direction: column;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.maya-decision__recommend {
  display: flex; flex-direction: column;
  gap: 6px;
  padding-top: 10px;
  margin-top: 0;
  border-top: 1px dashed var(--rule-2);
  min-width: 0;
}
.maya-decision__recommend-headline {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: clamp(22px, 2.3vw, 30px);
  font-weight: 600;
  line-height: 1.15;
  letter-spacing: -0.022em;
  color: var(--ink);
  margin: 0;
  text-wrap: balance;
}
.maya-decision__head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 18px; flex-wrap: wrap;
}
.maya-decision__name {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: clamp(24px, 2.4vw, 30px);
  font-weight: 600;
  line-height: 1.1;
  letter-spacing: -0.022em;
  color: var(--ink);
  margin: 0;
}
.maya-decision__when {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.04em;
  font-feature-settings: "tnum";
}
.maya-decision__quote {
  font-family: 'Frank Ruhl Libre', serif;
  font-style: italic;
  font-size: clamp(18px, 1.8vw, 21px);
  line-height: 1.42;
  color: var(--ink);
  margin: 0;
  letter-spacing: -0.005em;
  text-wrap: balance;
}
.maya-decision__quote::before { content: "“"; color: var(--bronze); margin-inline-end: 2px; }
.maya-decision__quote::after  { content: "”"; color: var(--bronze); margin-inline-start: 2px; }
.maya-decision__meta {
  display: flex; gap: 22px;
  font-size: 13px;
  color: var(--ink-3);
  flex-wrap: wrap;
  font-feature-settings: "tnum";
  margin-top: 2px;
}
.maya-decision__meta strong {
  color: var(--eucalyptus);
  font-weight: 700;
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 16px;
  letter-spacing: -0.015em;
  margin-inline-end: 4px;
}
.maya-decision__meta__label {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--ink-4);
  font-weight: 600;
  display: block;
  margin-bottom: 2px;
}
.maya-decision__reco-tag {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.maya-decision__reco-tag::before {
  content: "";
  width: 22px; height: 2px;
  background: var(--bronze);
  border-radius: 2px;
}

/* Decision-area section eyebrow ("דורש החלטה") sits at the very top */
.maya-decision__section-eyebrow {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 0.24em;
  text-transform: uppercase;
  color: var(--sienna);
  font-weight: 700;
  display: inline-flex; align-items: center; gap: 8px;
  margin-bottom: 2px;
}
.maya-decision__section-eyebrow .pulse {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--sienna);
  box-shadow: 0 0 0 0 rgba(194,90,46, 0.55);
  animation: maya-urgent-pulse 1.8s ease-out infinite;
}

/* Outcome hint below the CTA: "אם תאשר — …" */
.maya-decision__outcome {
  font-family: 'Frank Ruhl Libre', serif;
  font-style: italic;
  font-size: 12.5px;
  color: var(--ink-3);
  line-height: 1.35;
  max-width: 600px;
  margin: 0;
}
.maya-decision__outcome strong {
  color: var(--ink-2);
  font-weight: 500;
}
.maya-decision__cta {
  display: flex; align-items: center; justify-content: space-between;
  gap: 16px;
  width: 100%;
  max-width: 600px;
  margin: 4px 0 0;
  padding: 17px 28px;
  background:
    linear-gradient(180deg, #e6c887 0%, #c19c52 55%, #a6864b 100%);
  color: var(--forest);
  border: 0;
  border-radius: 12px;
  font: inherit;
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.005em;
  cursor: pointer;
  transition: transform 200ms ease, box-shadow 200ms ease, background 200ms ease;
  text-align: start;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.55) inset,
    0 0 0 1px rgba(138,107,48,0.55) inset,
    0 22px 44px -14px rgba(166,134,75, 0.55),
    0 0 0 8px rgba(201,168,106, 0.12);
}
.maya-decision__cta:hover:not(:disabled) {
  background: linear-gradient(180deg, #efd198 0%, #ccab63 55%, #b1925a 100%);
  transform: translateY(-1px);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.65) inset,
    0 0 0 1px rgba(138,107,48,0.60) inset,
    0 26px 52px -14px rgba(166,134,75, 0.65),
    0 0 0 10px rgba(201,168,106, 0.14);
}
.maya-decision__cta:disabled { opacity: 0.5; cursor: not-allowed; }
.maya-decision__cta-arrow {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px;
  border-radius: 50%;
  background: var(--forest);
  color: var(--gold-soft);
  flex-shrink: 0;
  box-shadow: 0 0 0 1px rgba(255,255,255,0.20) inset;
}
.maya-decision__cta-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.maya-decision__alt {
  display: flex; align-items: center; gap: 18px;
  font-size: 12.5px; color: var(--ink-3);
  flex-wrap: wrap;
  max-width: 640px;
  width: 100%;
}
.maya-decision__alt button {
  background: transparent;
  border: 0;
  color: var(--ink-3);
  font: inherit;
  cursor: pointer;
  padding: 4px 0;
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-color: var(--rule-2);
}
.maya-decision__alt button:hover:not(:disabled) {
  color: var(--ink);
  text-decoration-color: var(--bronze);
}
.maya-decision__alt button:disabled { opacity: 0.4; cursor: not-allowed; }
.maya-decision__alt .more {
  margin-inline-start: auto;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: var(--bronze);
  font-weight: 600;
}
.maya-decision--quiet { padding-block: 18px; gap: 8px; }
.maya-decision--quiet .maya-decision__quote { font-style: italic; font-weight: 400; color: var(--ink-2); }

/* ── Sidecol — Night receipts + Rhythm ─────────────────────── */
.maya-sidecol {
  display: flex; flex-direction: column;
  gap: 18px;
  background: var(--paper);
  border: 1px solid var(--line-2);
  border-radius: 18px;
  padding: 22px 24px;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.65) inset,
    0 10px 22px -14px rgba(20,19,14,0.14),
    0 2px 6px -4px rgba(20,19,14,0.05);
}
.maya-sidecol__title {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 700;
  margin: 0 0 8px;
}
.maya-nightlog {
  display: flex; flex-direction: column;
}
.maya-nightlog__row {
  display: grid;
  grid-template-columns: 22px 1fr;
  gap: 12px;
  align-items: center;
  padding: 7px 0;
  border-top: 1px solid var(--rule);
  font-size: 13.5px;
  color: var(--ink-2);
  line-height: 1.4;
}
.maya-nightlog__row:first-child { border-top: 0; padding-top: 2px; }
.maya-nightlog__check {
  color: var(--up);
  font-weight: 700;
  font-size: 11.5px;
  width: 22px; height: 22px;
  border-radius: 50%;
  background: rgba(79,122,74, 0.15);
  display: inline-flex; align-items: center; justify-content: center;
  box-shadow: 0 0 0 1px rgba(79,122,74, 0.20) inset;
}
.maya-nightlog__row strong { color: var(--ink); font-weight: 500; }
.maya-nightlog__empty {
  font-family: 'Frank Ruhl Libre', serif;
  font-style: italic;
  font-size: 13px;
  color: var(--ink-3);
  line-height: 1.4;
}
.maya-rhythm {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 13.5px;
  color: var(--ink-2);
  line-height: 1.55;
  font-weight: 400;
  margin: 0;
}
.maya-rhythm strong { color: var(--ink); font-weight: 500; }
.maya-rhythm .num {
  font-weight: 600;
  color: var(--ink);
  font-feature-settings: "tnum";
  letter-spacing: -0.01em;
}
.maya-rhythm .recovered-inline {
  color: var(--eucalyptus);
  font-weight: 600;
  font-feature-settings: "tnum";
}

/* ── Section rule "── המערכת ──" separator ─────────────────── */
.maya-section-rule {
  display: flex; align-items: center; gap: 12px;
  margin: 0;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 700;
  border: 0;
  height: auto;
  background: transparent;
  flex: 0 0 auto;
}
.maya-section-rule::before { content: attr(data-label); flex-shrink: 0; }
.maya-section-rule::after { content: ""; flex: 1; height: 1px; background: var(--rule); }

/* ── KPI cards — 4 full cards in a row ────────────────────── */
.maya-kpi-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  flex: 0 0 auto;
}
@media (max-width: 1180px) { .maya-kpi-cards { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 720px)  { .maya-kpi-cards { grid-template-columns: 1fr; } }

.maya-kpi {
  background: var(--paper);
  border: 1px solid var(--line-2);
  border-radius: 12px;
  padding: 8px 14px 8px;
  display: flex; flex-direction: column;
  gap: 4px;
  position: relative;
  flex: 0 0 auto;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.55) inset,
    0 8px 18px -16px rgba(20,19,14,0.20),
    0 2px 6px -4px rgba(20,19,14,0.05);
  transition: box-shadow 200ms ease, transform 200ms ease;
}
.maya-kpi:hover {
  box-shadow:
    0 1px 0 rgba(255,255,255,0.65) inset,
    0 14px 28px -16px rgba(20,19,14,0.26),
    0 4px 10px -4px rgba(20,19,14,0.08);
}
.maya-kpi__label {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 600;
}
.maya-kpi__row {
  display: flex; align-items: baseline; gap: 12px;
}
.maya-kpi__value {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 22px;
  font-weight: 500;
  line-height: 1;
  color: var(--ink);
  letter-spacing: -0.022em;
  font-feature-settings: "tnum";
}
.maya-kpi__delta {
  font-size: 12.5px;
  font-weight: 600;
  display: inline-flex; align-items: baseline; gap: 4px;
  font-feature-settings: "tnum";
}
.maya-kpi__delta.up   { color: var(--up); }
.maya-kpi__delta.down { color: var(--down); }
.maya-kpi__delta.flat,
.maya-kpi__delta.none { color: var(--ink-3); font-style: italic; opacity: 0.8; font-weight: 500; }

/* Honest direction baseline (no fake time series) */
.maya-kpi__indicator {
  height: 10px;
  position: relative;
  overflow: hidden;
}
.maya-kpi__indicator svg { width: 100%; height: 100%; display: block; }
.maya-kpi__indicator.dir-up   svg { color: var(--up); }
.maya-kpi__indicator.dir-down svg { color: var(--down); }
.maya-kpi__indicator.dir-flat svg { color: var(--rule-2); }

/* ── Operations row — 4 cards, fills remaining height ─────── */
.maya-ops-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  flex: 1 1 0;
  min-height: 0;
  margin-top: 4px;
}
@media (max-width: 1280px) {
  .maya-ops-row { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 720px) {
  .maya-ops-row { grid-template-columns: 1fr; }
}
.maya-ops-row > .maya-card {
  min-height: 0;
  overflow: hidden;
  display: flex; flex-direction: column;
  padding: 14px 18px 10px;
  position: relative;
}
/* Cap visible rows inside each card to a clean 3-row preview.
   Anything beyond scrolls inside via .maya-list overflow-y:auto.
   The card's height still flexes — this only governs the inner list. */
.maya-ops-row > .maya-card .maya-list,
.maya-ops-row > .maya-card .maya-funnel {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
}
.maya-ops-row > .maya-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent 5%, var(--bronze) 50%, transparent 95%);
  opacity: 0.45;
  border-radius: 16px 16px 0 0;
}
.maya-ops-row > .maya-card .maya-list,
.maya-ops-row > .maya-card .maya-funnel {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
}
.maya-ops-row > .maya-card .maya-list::-webkit-scrollbar,
.maya-ops-row > .maya-card .maya-funnel::-webkit-scrollbar { width: 4px; }
.maya-ops-row > .maya-card .maya-list::-webkit-scrollbar-thumb,
.maya-ops-row > .maya-card .maya-funnel::-webkit-scrollbar-thumb { background: var(--rule-2); border-radius: 4px; }

/* "View all" footer on operational cards */
.maya-card__viewall {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--rule);
  display: flex; justify-content: space-between; align-items: center;
  font-size: 12px;
  color: var(--ink-3);
}
.maya-card__viewall a,
.maya-card__viewall button {
  color: var(--ink);
  font-weight: 500;
  text-decoration: none;
  background: transparent; border: 0;
  font: inherit; cursor: pointer;
  display: inline-flex; align-items: center; gap: 4px;
}
.maya-card__viewall a:hover,
.maya-card__viewall button:hover { color: var(--bronze); }
.maya-card__viewall .count {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10.5px;
  letter-spacing: 0.10em;
  color: var(--ink-3);
}

/* ── Dock strip (pinned at bottom) ────────────────────────── */
.maya-dock-strip { flex: 0 0 auto; margin-top: 4px; }

/* ── Reduced motion ───────────────────────────────────────── */
@media (prefers-reduced-motion: reduce) {
  .maya-orb::after,
  .maya-core-orb, .maya-core-ring,
  .maya-live-dot, .maya-wave > i,
  .maya-orbit.hot .maya-orbit-dot,
  .maya-fade-in,
  .maya-vigil__pulse { animation: none !important; }
}

/* ═══════════════════════════════════════════════════════════════
   MORNING FOLD — Maya signature surface
   The screen Mira sees at 06:45 before her first patient.
   Reading column, not dashboard. Decision, not analytics.
   ═══════════════════════════════════════════════════════════════ */

.maya-shell {
  background: var(--bg);
  overflow: hidden !important;
}

/* ── הפלוט — the vigil line (subtle ambient detail) ───────── */
.maya-vigil {
  position: relative;
  height: 1px;
  width: 100%;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(176,138,62, 0.28) 20%,
    rgba(176,138,62, 0.48) 50%,
    rgba(176,138,62, 0.28) 80%,
    transparent 100%);
  margin: 0 0 6px;
}
.maya-vigil__pulse {
  position: absolute;
  top: -1px;
  height: 3px;
  width: 80px;
  border-radius: 999px;
  background: radial-gradient(ellipse at center,
    rgba(194, 90, 46, 0.85) 0%,
    rgba(194, 90, 46, 0.15) 50%,
    transparent 100%);
  animation: maya-vigil-travel 18s ease-in-out infinite;
}
@keyframes maya-vigil-travel {
  0%   { inset-inline-start: 0%;   opacity: 0; }
  10%  {                            opacity: 1; }
  85%  { inset-inline-start: calc(100% - 80px); opacity: 1; }
  100% { inset-inline-start: calc(100% - 80px); opacity: 0; }
}
.maya-vigil.is-dormant .maya-vigil__pulse { display: none; }

/* ── Morning fold container ──────────────────────────────── */
.maya-fold {
  max-width: 880px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* ── Recovered chip — compact product signal in header ────── */
.maya-recovered {
  display: inline-flex;
  align-items: center;
  gap: 16px;
  padding: 12px 18px 12px 16px;
  background: linear-gradient(180deg, rgba(15,76,58, 0.08) 0%, rgba(15,76,58, 0.03) 100%);
  border: 1px solid rgba(15,76,58, 0.28);
  border-radius: 14px;
  position: relative;
  box-shadow: 0 6px 18px -14px rgba(15,76,58, 0.35);
}
.maya-recovered::before {
  content: "";
  position: absolute;
  inset-inline-start: 0;
  top: 12px; bottom: 12px;
  width: 3px;
  background: var(--eucalyptus);
  border-radius: 0 3px 3px 0;
}
[dir="rtl"] .maya-recovered::before { border-radius: 3px 0 0 3px; }
.maya-recovered__l {
  display: flex; flex-direction: column;
  gap: 4px;
}
.maya-recovered__label {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--eucalyptus);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.maya-recovered__label .est {
  color: var(--ink-4);
  font-size: 9px;
  letter-spacing: 0.10em;
  font-weight: 500;
  text-transform: lowercase;
}
.maya-recovered__value {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 30px;
  font-weight: 600;
  letter-spacing: -0.025em;
  color: var(--eucalyptus);
  line-height: 1;
  font-feature-settings: "tnum";
}
.maya-recovered__value .cur {
  font-size: 0.50em; color: var(--bronze);
  margin-inline-end: 0.08em; font-weight: 400;
  vertical-align: 0.15em;
}
.maya-recovered__value.is-dormant {
  font-size: 18px;
  color: var(--ink-2);
  font-style: italic;
  font-weight: 400;
  letter-spacing: -0.005em;
}
.maya-recovered__r {
  border-inline-start: 1px solid rgba(15,76,58, 0.20);
  padding-inline-start: 16px;
  display: flex; flex-direction: column;
  gap: 3px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: var(--ink-2);
  line-height: 1.4;
  font-feature-settings: "tnum";
}
.maya-recovered__r .stat {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 20px;
  color: var(--ink);
  font-weight: 600;
  line-height: 1;
}
.maya-recovered__r .live {
  display: inline-flex; align-items: center; gap: 5px;
  color: var(--eucalyptus);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 9px;
  font-weight: 600;
}
.maya-recovered__r .live::before {
  content: "";
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--eucalyptus);
  box-shadow: 0 0 0 0 rgba(15,76,58, 0.45);
  animation: maya-counter-pulse 2.0s ease-out infinite;
}
@keyframes maya-counter-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(15,76,58, 0.45); }
  70%  { box-shadow: 0 0 0 7px rgba(15,76,58, 0); }
  100% { box-shadow: 0 0 0 0   rgba(15,76,58, 0); }
}

/* ── Recovered counter — banner at top of fold (legacy, kept) */
.maya-counter {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: end;
  gap: 28px;
  padding: 22px 26px 22px 24px;
  background: linear-gradient(180deg, rgba(15,76,58, 0.04) 0%, rgba(15,76,58, 0.02) 100%);
  border: 1px solid rgba(15,76,58, 0.18);
  border-radius: 16px;
  position: relative;
}
.maya-counter::before {
  content: "";
  position: absolute;
  inset-inline-start: 0;
  top: 22px; bottom: 22px;
  width: 3px;
  background: var(--eucalyptus);
  border-radius: 0 3px 3px 0;
}
[dir="rtl"] .maya-counter::before { border-radius: 3px 0 0 3px; }
.maya-counter__cluster {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.maya-counter__label {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.22em;
  text-transform: uppercase;
  color: var(--eucalyptus);
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.maya-counter__label .est {
  color: var(--ink-4);
  font-size: 9px;
  letter-spacing: 0.12em;
  font-weight: 500;
  text-transform: lowercase;
}
.maya-counter__value {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: clamp(52px, 5.5vw, 76px);
  font-weight: 500;
  letter-spacing: -0.04em;
  color: var(--eucalyptus);
  line-height: 0.92;
  text-shadow: 0 1px 0 rgba(15, 76, 58, 0.08);
  font-feature-settings: "tnum";
}
.maya-counter__value .cur {
  font-size: 0.42em;
  color: var(--bronze);
  margin-inline-end: 0.10em;
  font-weight: 400;
  vertical-align: 0.18em;
}
.maya-counter__value.is-dormant {
  font-size: clamp(34px, 3.2vw, 44px);
  color: var(--ink-2);
  font-style: italic;
  font-weight: 400;
  letter-spacing: -0.01em;
}
.maya-counter__sub {
  text-align: end;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-feature-settings: "tnum";
  font-size: 11px;
  color: var(--ink-2);
  line-height: 1.45;
}
.maya-counter__sub .stat {
  font-size: 22px;
  font-family: 'Frank Ruhl Libre', serif;
  color: var(--ink);
  font-weight: 500;
  line-height: 1;
}
.maya-counter__sub .live {
  display: inline-flex; align-items: center; gap: 6px;
  color: var(--eucalyptus);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-size: 10px;
  font-weight: 600;
}
.maya-counter__sub .live::before {
  content: "";
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--eucalyptus);
  box-shadow: 0 0 0 0 rgba(15,76,58, 0.45);
  animation: maya-counter-pulse 2.0s ease-out infinite;
}
@keyframes maya-counter-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(15,76,58, 0.45); }
  70%  { box-shadow: 0 0 0 8px rgba(15,76,58, 0); }
  100% { box-shadow: 0 0 0 0   rgba(15,76,58, 0); }
}
@media (max-width: 640px) {
  .maya-counter { grid-template-columns: 1fr; gap: 12px; }
  .maya-counter__sub { text-align: start; }
}

/* ── Greeting — quieter so the decision dominates ─────────── */
.maya-greet {
  font-family: 'Frank Ruhl Libre', serif;
  font-weight: 300;
  font-size: clamp(28px, 3vw, 36px);
  line-height: 1.15;
  letter-spacing: -0.015em;
  color: var(--ink-2);
  margin: 0;
}
.maya-greet strong { font-weight: 500; color: var(--ink); }
.maya-greet__narrative {
  margin-top: 8px;
  font-family: 'Heebo', system-ui, sans-serif;
  font-size: 14.5px;
  line-height: 1.5;
  color: var(--ink-3);
  max-width: 640px;
  font-weight: 400;
}

/* ── Eyebrow ──────────────────────────────────────────────── */
.maya-eyebrow {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 10px;
  letter-spacing: 0.20em;
  text-transform: uppercase;
  color: var(--bronze);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 10px;
}
.maya-eyebrow::before {
  content: "";
  width: 22px; height: 1px;
  background: var(--bronze);
}

/* ── Decision block — the urgent thing ────────────────────── */
.maya-decision {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
  padding: 24px 26px 26px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: 16px;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.5) inset,
    0 14px 40px -24px rgba(194,90,46, 0.22),
    0 4px 12px -6px rgba(26,26,20,0.06);
}
.maya-decision::before {
  content: "";
  position: absolute;
  top: 22px; bottom: 22px;
  inset-inline-start: 0;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(180deg, var(--sienna) 0%, var(--bronze) 100%);
}
[dir="rtl"] .maya-decision::before { border-radius: 3px 0 0 3px; }
.maya-decision .maya-eyebrow {
  color: var(--sienna);
}
.maya-decision .maya-eyebrow::before { background: var(--sienna); }
.maya-decision .maya-eyebrow::after {
  content: "";
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--sienna);
  box-shadow: 0 0 0 0 rgba(194,90,46, 0.55);
  animation: maya-urgent-pulse 1.8s ease-out infinite;
}
@keyframes maya-urgent-pulse {
  0%   { box-shadow: 0 0 0 0   rgba(194,90,46, 0.55); }
  70%  { box-shadow: 0 0 0 9px rgba(194,90,46, 0); }
  100% { box-shadow: 0 0 0 0   rgba(194,90,46, 0); }
}
.maya-decision__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
}
.maya-decision__who {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: clamp(28px, 3vw, 36px);
  font-weight: 500;
  line-height: 1.15;
  letter-spacing: -0.018em;
  color: var(--ink);
}
.maya-decision__when {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: var(--ink-3);
  font-feature-settings: "tnum";
  letter-spacing: 0.04em;
}
.maya-decision__quote {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 22px;
  line-height: 1.4;
  color: var(--ink);
  font-style: italic;
  padding-inline-start: 18px;
  border-inline-start: 2px solid var(--bronze);
  margin: 0;
  letter-spacing: -0.005em;
}
.maya-decision__meta {
  display: flex;
  gap: 18px;
  font-size: 12.5px;
  color: var(--ink-3);
  flex-wrap: wrap;
}
.maya-decision__meta strong {
  color: var(--ink);
  font-weight: 500;
}

.maya-decision__cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  width: 100%;
  padding: 20px 26px;
  background: linear-gradient(180deg, #d36a3a 0%, var(--sienna) 100%);
  color: #fff;
  border: 0;
  border-radius: 14px;
  font: inherit;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.005em;
  cursor: pointer;
  transition: transform 200ms ease, box-shadow 200ms ease, background 200ms ease;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.24) inset,
    0 0 0 1px rgba(155,72,37,0.45) inset,
    0 14px 32px -12px rgba(194,90,46, 0.70),
    0 0 0 8px rgba(194,90,46, 0.08);
  text-align: start;
  margin-top: 4px;
}
.maya-decision__cta:hover:not(:disabled) {
  background: #cf6634;
  transform: translateY(-1px);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.22) inset,
    0 14px 30px -10px rgba(194,90,46, 0.65),
    0 0 0 8px rgba(194,90,46, 0.10);
}
.maya-decision__cta:disabled { opacity: 0.55; cursor: not-allowed; }
.maya-decision__cta-arrow {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px;
  border-radius: 50%;
  background: rgba(0,0,0,0.18);
}

.maya-decision__alt {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.maya-decision__alt button {
  background: transparent;
  border: 0;
  color: var(--ink-3);
  font: inherit;
  cursor: pointer;
  padding: 6px 4px;
  text-decoration: underline;
  text-underline-offset: 4px;
  text-decoration-color: var(--rule-2);
}
.maya-decision__alt button:hover:not(:disabled) {
  color: var(--ink);
  text-decoration-color: var(--bronze);
}
.maya-decision__alt button:disabled { opacity: 0.4; cursor: not-allowed; }
.maya-decision__more {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  color: var(--ink-3);
}

.maya-decision__quiet {
  font-family: 'Frank Ruhl Libre', serif;
  font-size: 22px;
  font-weight: 400;
  color: var(--ink-2);
  line-height: 1.4;
  font-style: italic;
}
.maya-decision__quiet small {
  display: block;
  margin-top: 6px;
  font-family: 'Heebo', system-ui, sans-serif;
  font-size: 13px;
  font-style: normal;
  color: var(--ink-3);
}

/* ── Today schedule (quiet row list) ──────────────────────── */
.maya-schedule {
  display: flex; flex-direction: column;
}
.maya-schedule__row {
  display: grid;
  grid-template-columns: 64px 1fr auto;
  gap: 14px;
  align-items: baseline;
  padding: 11px 0;
  border-top: 1px dashed var(--rule);
  font-size: 14px;
}
.maya-schedule__row:first-child { border-top: 0; padding-top: 4px; }
.maya-schedule__time {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 12px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
  font-feature-settings: "tnum";
}
.maya-schedule__name {
  font-weight: 500;
  color: var(--ink);
}
.maya-schedule__type {
  display: block;
  font-size: 11.5px;
  color: var(--ink-3);
  font-weight: 400;
  margin-top: 1px;
}
.maya-schedule__tag {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 4px;
  font-weight: 500;
  letter-spacing: 0.02em;
}
.maya-schedule__tag.ok    { background: rgba(15,76,58, 0.10); color: var(--eucalyptus); }
.maya-schedule__tag.wait  { background: rgba(176,138,62, 0.16); color: var(--bronze); }
.maya-schedule__empty {
  font-family: 'Frank Ruhl Libre', serif;
  font-style: italic;
  font-size: 14px;
  color: var(--ink-3);
  padding: 4px 0;
}

/* ── Section rule — minimal connective tissue ─────────────── */
.maya-rule {
  display: block;
  width: 24px;
  height: 1px;
  background: var(--rule);
  margin: -4px 0;
}

/* ── Second fold (collapsible — everything else lives here) ─ */
.maya-second-fold {
  margin-top: 40px;
  padding-top: 24px;
  border-top: 1px solid var(--rule);
}
.maya-second-fold > summary {
  list-style: none;
  cursor: pointer;
  display: flex; align-items: center; gap: 10px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-3);
  padding: 4px 0;
  user-select: none;
}
.maya-second-fold > summary::-webkit-details-marker { display: none; }
.maya-second-fold > summary::before {
  content: "▸";
  display: inline-block;
  font-size: 10px;
  color: var(--bronze);
  transition: transform 180ms ease;
}
.maya-second-fold[open] > summary::before { transform: rotate(90deg); }
[dir="rtl"] .maya-second-fold[open] > summary::before { transform: rotate(-90deg); }
.maya-second-fold > summary:hover { color: var(--ink); }
.maya-second-fold__body {
  padding-top: 24px;
  display: flex; flex-direction: column; gap: 18px;
}
`;
