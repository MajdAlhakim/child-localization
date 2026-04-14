import { useStore } from '../../store';
import { Maximize2 } from 'lucide-react';

const STEPS = ['Floor Plan', 'Zones', 'Grid', 'APs', 'Radio Map', 'Export'];

export function Header({ onFit, zoom, liveStatus }) {
  const step   = useStore(s => s.step);
  const setStep = useStore(s => s.setStep);
  const scale  = useStore(s => s.scale);
  const grid   = useStore(s => s.grid);
  const aps    = useStore(s => s.aps);

  return (
    <header
      className="flex-shrink-0 flex items-center gap-4 px-4 border-b z-10"
      style={{
        height: 48,
        background: 'linear-gradient(180deg, var(--bg2) 0%, rgba(11,16,25,0.95) 100%)',
        borderColor: 'var(--border)',
        backdropFilter: 'blur(8px)',
      }}
    >
      {/* Logo */}
      <div className="font-mono text-sm font-medium tracking-[3px] whitespace-nowrap" style={{ color: 'var(--primary-b)', textShadow: '0 0 20px var(--primary-glow)' }}>
        TRAKN <span className="text-[10px] tracking-[1.5px] font-normal ml-2" style={{ color: 'var(--text-dim)' }}>MAPPING</span>
      </div>

      {/* Step indicator */}
      <div className="flex items-center gap-1">
        {STEPS.map((name, i) => {
          const n = i + 1;
          const active = step === n;
          return (
            <div key={n} className="flex items-center gap-1">
              <button
                onClick={() => setStep(n)}
                title={name}
                className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-mono font-medium transition-all duration-200 cursor-pointer"
                style={{
                  background: active ? 'var(--primary)' : 'var(--bg4)',
                  border: `1px solid ${active ? 'var(--primary)' : 'var(--border)'}`,
                  color: active ? '#fff' : 'var(--text-dim)',
                  transform: active ? 'scale(1.1)' : '',
                  boxShadow: active ? '0 0 12px var(--primary-glow)' : '',
                }}
              >
                {n}
              </button>
              {n < 6 && <span className="text-[9px] opacity-40" style={{ color: 'var(--text-dim)' }}>›</span>}
            </div>
          );
        })}
      </div>

      {/* Status bar */}
      <div className="flex-1 flex items-center gap-4 font-mono text-[11px] overflow-hidden" style={{ color: 'var(--text-muted)' }}>
        <span className="whitespace-nowrap">Scale: <span style={{ color: 'var(--text)' }}>{scale.toFixed(2)} px/m</span></span>
        <span className="whitespace-nowrap">Grid: <span style={{ color: 'var(--text)' }}>{grid.points.length} pts</span></span>
        <span className="whitespace-nowrap">APs: <span style={{ color: 'var(--text)' }}>{aps.list.length}</span></span>
        <span className="whitespace-nowrap">Zoom: <span style={{ color: 'var(--text)' }}>{zoom}%</span></span>
      </div>

      {/* Live indicator */}
      <LiveIndicator status={liveStatus} />

      {/* Fit button */}
      <button
        onClick={onFit}
        title="Fit to screen"
        className="flex items-center gap-1.5 text-[11px] font-mono font-medium px-2 py-1 rounded transition-all duration-150 cursor-pointer"
        style={{ background: 'var(--bg4)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.color = 'var(--primary-b)'; }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-muted)'; }}
      >
        <Maximize2 size={11} /> Fit
      </button>
    </header>
  );
}

function LiveIndicator({ status }) {
  const dot = status === 'live'
    ? { bg: '#22c55e', shadow: '0 0 6px #22c55e', anim: 'animate-live-pulse' }
    : status === 'waiting'
    ? { bg: '#eab308', shadow: '0 0 6px #eab308', anim: '' }
    : { bg: 'var(--text-dim)', shadow: 'none', anim: '' };

  return (
    <div className="flex items-center gap-1.5 whitespace-nowrap font-mono text-[11px]" style={{ color: 'var(--text-dim)' }}>
      <div className={`w-[7px] h-[7px] rounded-full transition-all duration-300 ${dot.anim}`}
        style={{ background: dot.bg, boxShadow: dot.shadow }} />
      <span style={{ color: status === 'live' ? 'var(--green)' : 'var(--text-dim)' }}>
        {status === 'live' ? 'Live' : status === 'waiting' ? 'Syncing…' : 'Offline'}
      </span>
    </div>
  );
}
