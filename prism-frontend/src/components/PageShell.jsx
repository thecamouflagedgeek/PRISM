// src/components/PageShell.jsx
// Wraps every page.
// Canvas dot background fills the viewport.
// Children render above it on a transparent layer.

import { DottedGlowBackground } from "./DottedGlowBackground";

export function PageShell({ children, glowColor, style = {} }) {
  return (
    <div style={{
      position: "relative",
      minHeight: "100vh",
      background: "var(--cream)",
      ...style,
    }}>
      {/* ── Animated dot canvas — sits behind everything ── */}
      <DottedGlowBackground
        gap={22}
        radius={1.6}
        color="rgba(0,0,0,0.30)"
        glowColor={glowColor || "rgba(232, 104, 58, 0.75)"}
        opacity={0.75}
        speedMin={0.25}
        speedMax={0.9}
        speedScale={1}
        backgroundOpacity={0}
      />

      {/* ── Page content — above the canvas ── */}
      <div style={{ position: "relative", zIndex: 1 }}>
        {children}
      </div>
    </div>
  );
}