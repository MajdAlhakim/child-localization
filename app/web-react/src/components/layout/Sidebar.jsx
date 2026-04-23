import { ArrowLeft, MousePointer, PenTool, Eraser } from 'lucide-react';
import { useStore } from '../../store';

const STEPS = [
  { n: 1, name: 'Floor Plan',    desc: 'Upload image, set scale' },
  { n: 2, name: 'Draw Zones',    desc: 'Polygon walkable areas' },
  { n: 3, name: 'Grid',          desc: 'Generate 0.5 m grid' },
  { n: 4, name: 'Access Points', desc: 'Live sync from Android' },
  { n: 5, name: 'Radio Map',     desc: 'Compute signal model' },
  { n: 6, name: 'Export',        desc: 'Download JSON files' },
];

function stepBadgeState(n, { floorPlanLoaded, polygons, grid, aps, radioMap }) {
  if (n === 1) return floorPlanLoaded ? { type: 'ok', text: '✓' } : { type: '', text: '—' };
  if (n === 2) return polygons.length ? { type: 'ok', text: polygons.length + '' } : { type: '', text: '—' };
  if (n === 3) return grid.generated ? { type: grid.points.length >= 100 ? 'ok' : 'warn', text: grid.points.length + '' } : { type: '', text: '—' };
  if (n === 4) return aps.list.length ? { type: aps.list.length >= 3 ? 'ok' : 'warn', text: aps.list.length + '' } : { type: '', text: '—' };
  if (n === 5) return radioMap.computed ? { type: 'ok', text: '✓' } : { type: '', text: '—' };
  return { type: '', text: '—' };
}

export function Sidebar({ onBack }) {
  const step    = useStore(s => s.step);
  const setStep = useStore(s => s.setStep);
  const tool    = useStore(s => s.tool);
  const setTool = useStore(s => s.setTool);
  const allVenues     = useStore(s => s.allVenues);
  const activeVenueId = useStore(s => s.activeVenueId);
  const activeFpId    = useStore(s => s.activeFpId);
  const floorPlanLoaded = useStore(s => s.floorPlanLoaded);
  const polygons = useStore(s => s.polygons);
  const grid     = useStore(s => s.grid);
  const aps      = useStore(s => s.aps);
  const radioMap = useStore(s => s.radioMap);

  const activeVenue = allVenues.find(v => v.id === activeVenueId);
  const activeFp    = activeVenue?.floor_plans?.find(f => f.id === activeFpId);
  const badgeData   = { floorPlanLoaded, polygons, grid, aps, radioMap };

  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-y-auto"
      style={{ width: 240, background: 'var(--bg2)', borderRight: '1px solid var(--border)' }}
    >
      {/* Back button + context */}
      <div
        className="p-3 flex items-center gap-2 cursor-pointer transition-all"
        style={{ borderBottom: '1px solid var(--border)' }}
        onClick={onBack}
        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg3)'}
        onMouseLeave={e => e.currentTarget.style.background = ''}
        title="Back to floor plans"
      >
        <ArrowLeft size={13} style={{ color: 'var(--text-dim)', flexShrink: 0 }} />
        <div className="min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-[1px]" style={{ color: 'var(--text-dim)' }}>
            {activeVenue?.name || 'Venue'}
          </div>
          <div className="text-xs font-semibold truncate" style={{ color: 'var(--text)' }}>
            {activeFp ? `Floor ${activeFp.floor_number} — ${activeFp.name}` : 'No floor plan'}
          </div>
        </div>
      </div>

      {/* Step list */}
      {STEPS.map(({ n, name, desc }) => {
        const active = step === n;
        const badge  = stepBadgeState(n, badgeData);
        return (
          <button
            key={n}
            onClick={() => setStep(n)}
            className="flex items-start gap-2.5 text-left cursor-pointer transition-all duration-150"
            style={{
              padding: '9px 14px',
              borderLeft: `2px solid ${active ? 'var(--primary)' : 'transparent'}`,
              background: active ? 'linear-gradient(90deg, var(--primary-dim), transparent)' : 'transparent',
              borderBottom: '1px solid var(--border-subtle)',
            }}
            onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg3)'; }}
            onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
          >
            <div
              className="flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono font-medium mt-0.5 transition-all duration-150"
              style={{
                background: active ? 'var(--primary)' : 'var(--bg4)',
                border: `1px solid ${active ? 'var(--primary)' : 'var(--border)'}`,
                color: active ? '#fff' : 'var(--text-dim)',
                boxShadow: active ? '0 0 8px var(--primary-glow)' : '',
              }}
            >
              {n}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-semibold" style={{ color: 'var(--text)' }}>{name}</div>
              <div className="text-[11px] mt-0.5 leading-snug" style={{ color: 'var(--text-muted)' }}>{desc}</div>
            </div>
            <div className={`step-badge ${badge.type}`}>{badge.text}</div>
          </button>
        );
      })}

      {/* Canvas tools */}
      <div className="p-3 mt-auto" style={{ borderTop: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Canvas Tools</div>
        <div className="flex gap-1 flex-wrap">
          <ToolBtn id="select" label="Select" shortcut="S" icon={<MousePointer size={11} />} tool={tool} setTool={setTool} />
          <ToolBtn id="draw"   label="Draw"   shortcut="W" icon={<PenTool size={11} />}     tool={tool} setTool={setTool} />
          <ToolBtn id="erase"  label="Erase"  shortcut="E" icon={<Eraser size={11} />}       tool={tool} setTool={setTool} />
        </div>
      </div>
    </aside>
  );
}

function ToolBtn({ id, label, shortcut, icon, tool, setTool }) {
  return (
    <button
      className={`tool-btn flex items-center gap-1 ${tool === id ? 'active' : ''}`}
      onClick={() => setTool(id)}
    >
      {icon} {label} <kbd className="text-[9px] opacity-60">{shortcut}</kbd>
    </button>
  );
}
