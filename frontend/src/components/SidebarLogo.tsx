export function SidebarLogo() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, padding: '4px 0 8px' }}>
      {/* GPU chip SVG mark */}
      <svg width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        {/* Chip body */}
        <rect x="11" y="11" width="26" height="26" rx="3" stroke="#e2e8f0" strokeWidth="1.75" fill="none" />

        {/* Inner grid - 3×3 compute cores */}
        <rect x="16" y="16" width="5" height="5" rx="1" fill="#94a3b8" />
        <rect x="21.5" y="16" width="5" height="5" rx="1" fill="#94a3b8" />
        <rect x="27" y="16" width="5" height="5" rx="1" fill="#94a3b8" />

        <rect x="16" y="21.5" width="5" height="5" rx="1" fill="#94a3b8" />
        <rect x="21.5" y="21.5" width="5" height="5" rx="1" fill="#00e5ff" opacity="0.9" />
        <rect x="27" y="21.5" width="5" height="5" rx="1" fill="#94a3b8" />

        <rect x="16" y="27" width="5" height="5" rx="1" fill="#94a3b8" />
        <rect x="21.5" y="27" width="5" height="5" rx="1" fill="#94a3b8" />
        <rect x="27" y="27" width="5" height="5" rx="1" fill="#94a3b8" />

        {/* Pins - top */}
        <line x1="18" y1="11" x2="18" y2="6"  stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="24" y1="11" x2="24" y2="6"  stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="30" y1="11" x2="30" y2="6"  stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />

        {/* Pins - bottom */}
        <line x1="18" y1="37" x2="18" y2="42" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="24" y1="37" x2="24" y2="42" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="30" y1="37" x2="30" y2="42" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />

        {/* Pins - left */}
        <line x1="11" y1="18" x2="6"  y2="18" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="11" y1="24" x2="6"  y2="24" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="11" y1="30" x2="6"  y2="30" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />

        {/* Pins - right */}
        <line x1="37" y1="18" x2="42" y2="18" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="37" y1="24" x2="42" y2="24" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
        <line x1="37" y1="30" x2="42" y2="30" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" />
      </svg>

      {/* Product name */}
      <div style={{ textAlign: 'center', lineHeight: 1, fontFamily: '"IBM Plex Sans", system-ui, sans-serif' }}>
        <div style={{
          fontSize: 13,
          fontWeight: 700,
          letterSpacing: '0.08em',
          color: '#e2e8f0',
          textTransform: 'uppercase',
        }}>
          Quda
        </div>
        <div style={{
          fontSize: 10,
          fontWeight: 500,
          letterSpacing: '0.12em',
          color: '#475569',
          textTransform: 'uppercase',
          marginTop: 3,
        }}>
          AIMS-DTU
        </div>
      </div>
    </div>
  );
}
