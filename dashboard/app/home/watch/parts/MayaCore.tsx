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
}

export function ConstellationRing({ orbits }: ConstellationProps) {
  return (
    <div className="absolute inset-0 pointer-events-none">
      {orbits.map(o => {
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
            <span className="text-white/50">·</span>
            <span className="text-white/65">{o.value}</span>
          </div>
        );
      })}
    </div>
  );
}
