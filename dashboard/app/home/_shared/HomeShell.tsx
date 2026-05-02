"use client";

import { useEffect, type ReactNode } from "react";
import { surfaceCss } from "./home.css";

interface HomeShellProps {
  lang: "he" | "en";
  children: ReactNode;
}

export function HomeShell({ lang, children }: HomeShellProps) {
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  const dir = lang === "he" ? "rtl" : "ltr";
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: surfaceCss }} />
      <div
        dir={dir}
        lang={lang}
        className={[
          "maya-shell",
          lang === "he" ? "maya-hebrew" : "",
          "fixed inset-0 z-[60] overflow-y-auto bg-surface-0 text-white/90",
        ].join(" ").trim()}
      >
        {children}
      </div>
    </>
  );
}
