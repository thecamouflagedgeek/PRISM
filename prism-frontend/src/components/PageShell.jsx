import React from 'react';

// Shared cream dot paper used throughout the borrower journey.
export function PageShell({ children, style = {} }) {
  return <div className="dot-grid" style={{position:'relative',minHeight:'100vh',...style}}>{children}</div>;
}
