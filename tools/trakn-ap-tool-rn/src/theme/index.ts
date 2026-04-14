export const C = {
  bg:          '#060a10',
  bg2:         '#0b1019',
  bg3:         '#111824',
  bg4:         '#18222f',
  border:      '#1e2e42',
  text:        '#d0dbe8',
  textMuted:   '#526a85',
  textDim:     '#334558',
  primary:     '#f97316',   // orange — AP tool accent
  primaryDim:  'rgba(249,115,22,0.15)',
  primaryGlow: 'rgba(249,115,22,0.3)',
  green:       '#22c55e',
  greenDim:    'rgba(34,197,94,0.12)',
  red:         '#ef4444',
  redDim:      'rgba(239,68,68,0.12)',
  yellow:      '#eab308',
  purple:      '#7c3aed',
};

export const S = {
  r:    5,
  rLg:  8,
  rXl:  12,
};

export const F = {
  mono:  'monospace' as const,  // fallback; Fira Code loaded at OS level
  sans:  undefined as undefined,
};
