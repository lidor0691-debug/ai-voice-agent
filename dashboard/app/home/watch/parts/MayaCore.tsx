"use client";

import type { OrbitNode } from "../watch-mock";

export function MayaCore() {
  return (
    <div className="maya-core w-full">
      <div className="maya-core-ring r1" />
      <div className="maya-core-ring r2" />
      <div className="maya-core-ring r3" />
      <div className="maya-core-orb" />
      <div className="absolute inset-0 grid place-items-center pointer-events-none">
        <div className="text-center">
          <div className="maya-section-label mb-1">MAYA · LIVE</div>
          <div className="text-white/85 text-sm font-medium">מנטרת 8 לקוחות</div>
        </div>
      </div>
    </div>
  );
}

interface ConstellationProps {
  orbits: OrbitNode[];
  /** Max nodes to render — keeps the field uncluttered. */
  max?: number;
}

const STATE_PRIORITY: Record<OrbitNode["state"], number> = { hot: 0, warm: 1, cool: 2 };

export function ConstellationRing({ orbits, max = 6 }: ConstellationProps) {
  // Show the most important nodes first (hot → warm → cool), capped at `max`.
  const visible = orbits
    .slice()
    .sort((a, b) => STATE_PRIORITY[a.state] - STATE_PRIORITY[b.state])
    .slice(0, max);

  return (
    <div className="absolute inset-0 pointer-events-none">
      {visible.map(o => {
        const x = 50 + Math.cos(o.theta) * o.r * 42;
        const y = 50 + Math.sin(o.theta) * o.r * 42;
        return (
          <div
            key={o.id}
            className={`maya-orbit ${o.state} pointer-events-auto`}
            style={{ insetInlineStart: `${x}%`, top: `${y}%` }}
          >
            <span className="maya-orbit-dot" />
            <span className="text-white/85">{o.name}</span>
          </div>
        );
      })}
    </div>
  );
}
