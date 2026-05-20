# Maya Clinic Revenue — Public Landing Page Integration

**Date:** 2026-05-20
**Status:** Approved
**Scope:** Public landing page only. No backend / dashboard / auth / API / Supabase changes.

## Goal

Expose the premium "Maya Clinic Revenue Intelligence" design (Claude Design export)
as the public marketing landing page, with embedded demo video, WhatsApp CTAs,
RTL Hebrew, mobile responsiveness, and cinematic scroll animations.

## Source of truth

`C:\Users\lidor\Downloads\Maya - Clinic Revenue\Landing Page.html` — a complete,
self-contained, hand-tuned RTL landing page. Only external deps: Google Fonts +
one video. Design language: dark luxury emerald + cream/ivory surfaces + brass gold,
serif display type (Frank Ruhl Libre), elegant spacing, subtle glow.

Cinematic `app.jsx` + `scenes-*.jsx` are the **motion direction reference** only.

## Architecture decision

Serve the export as a **real static HTML document** (not a React rewrite) so its
CSS, inline scripts, fonts, and RTL render at 100% fidelity and zero drift risk.

- `dashboard/public/landing.html` — the export (enhanced in place).
- `dashboard/public/videos/maya-demo.mp4` — demo video (from `מאיה דמו .mp4`).
- `dashboard/middleware.ts` — the only edited file:
  - Logged-out visitor at `/` → internal **rewrite** to `/landing.html`.
  - Logged-in visitor at `/` → redirect to `/home/watch` (existing app entry).
  - Whitelist anonymous access to `/landing.html` and `/videos/*` (and Google Fonts
    are external so unaffected).
  - All other routes keep the existing auth gate untouched.

## Enhancements applied to landing.html

1. **Video hardening** — `object-fit: cover` + aspect-ratio frame so it never
   crops/overflows on mobile; keeps autoplay + muted + loop + playsinline + lazy
   `data-src` swap + `מאיה` poster fallback.
2. **Cinematic scroll animations** — `IntersectionObserver` staggered scroll-reveal
   per section (slow fade + rise), subtle hero/video parallax drift, elegant easing.
   Replaces the slideshow feel. Honors `prefers-reduced-motion`.
3. **Mobile sticky WhatsApp CTA** — premium pill fixed bottom on small screens only,
   same `data-wa` target (`wa.me/972524620550`).
4. **Mobile QA** — verify/extend existing media queries: RTL spacing, type scale,
   no overflow, smooth scroll.

## Deliverables / changed files

- `dashboard/public/landing.html` (new)
- `dashboard/public/videos/maya-demo.mp4` (new)
- `dashboard/middleware.ts` (edited)
- `docs/superpowers/specs/2026-05-20-public-landing-page-design.md` (this doc)

## Out of scope (untouched)

backend, dashboard pages, auth logic, admin routes, Supabase, API routes,
`app/page.tsx` (logged-in redirect now handled in middleware; page left as-is).

## Verification

- `npm run build` passes in `dashboard/`.
- Local: logged-out `/` shows landing; logged-in `/` → `/home/watch`.
- Video loads from `/videos/maya-demo.mp4`, autoplays muted/looped.
- WhatsApp CTAs (hero, final, footer, sticky-mobile) open `wa.me/972524620550`.
- Mobile: no overflow, sticky CTA visible, RTL correct.
