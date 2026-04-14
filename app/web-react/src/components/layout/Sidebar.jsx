import { Plus, Trash2, MousePointer, PenTool, Eraser } from 'lucide-react';
import { useStore } from '../../store';

const STEPS = [
  { n: 1, name: 'Floor Plan',   desc: 'Upload image, set scale' },
  { n: 2, name: 'Draw Zones',   desc: 'Polygon walkable areas' },
  { n: 3, name: 'Grid',         desc: 'Generate 0.5 m grid' },
  { n: 4, name: 'Access Points',desc: 'Live sync from Android' },
  { n: 5, name: 'Radio Map',    desc: 'Compute signal model' },
  { n: 6, name: 'Export',       desc: 'Download JSON files' },
];

const BADGE_KEY = ['', 'badge1', 'badge2', 'badge3', 'badge4', 'badge5', 'badge6'];

function stepBadgeState(n, { floorPlanLoaded, polygons, grid, aps, radioMap }) {
  if (n === 1) return floorPlanLoaded ? { type: 'ok', text: '✓' } : { type: '', text: '—' };
  if (n === 2) return polygons.length ? { type: 'ok', text: polygons.length + '' } : { type: '', text: '—' };
  if (n === 3) return grid.generated ? { type: grid.points.length >= 100 ? 'ok' : 'warn', text: grid.points.length + '' } : { type: '', text: '—' };
  if (n === 4) return aps.list.length ? { type: aps.list.length >= 3 ? 'ok' : 'warn', text: aps.list.length + '' } : { type: '', text: '—' };
  if (n === 5) return radioMap.computed ? { type: 'ok', text: '✓' } : { type: '', text: '—' };
  if (n === 6) return { type: '', text: '—' };
  return { type: '', text: '—' };
}

export function Sidebar({ onNewVenue, onDeleteVenue, onVenueSwitch }) {
  const step    = useStore(s => s.step);
  const setStep = useStore(s => s.setStep);
  const tool    = useStore(s => s.tool);
  const setTool = useStore(s => s.setTool);
  const allVenues    = useStore(s => s.allVenues);
  const activeVenueId = useStore(s => s.activeVenueId);
  const floorPlanLoaded = useStore(s => s.floorPlanLoaded);
  const polygons  = useStore(s => s.polygons);
  const grid      = useStore(s => s.grid);
  const aps       = useStore(s => s.aps);
  const radioMap  = useStore(s => s.radioMap);

  const badgeData = { floorPlanLoaded, polygons, grid, aps, radioMap };

  return (
    <aside
      className="flex flex-col flex-shrink-0 overflow-y-auto"
      style={{ width: 240, background: 'var(--bg2)', borderRight: '1px solid var(--border)' }}
    >
      {/* Venue selector */}
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Venue</div>
        <div className="flex items-center gap-1">
          <select
            value={activeVenueId || ''}
            onChange={e => e.target.value && onVenueSwitch?.(e.target.value)}
            className="flex-1 text-[11px] outline-none font-medium"
            style={{
              background: 'var(--bg3)', border: '1px solid var(--border)',
              color: 'var(--text)', padding: '5px 8px', borderRadius: 'var(--radius)',
            }}
          >
            {allVenues.length === 0
              ? <option value="">— no venues —</option>
              : allVenues.map(v => <option key={v.id} value={v.id}>{v.name}</option>)
            }
          </select>
          <button className="icon-btn" onClick={onNewVenue} title="New venue">
            <Plus size={13} />
          </button>
          <button className="icon-btn danger" onClick={onDeleteVenue} title="Delete venue">
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {/* Step list */}
      {STEPS.map(({ n, name, desc }) => {
        const active = step === n;
        const badge = stepBadgeState(n, badgeData);
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
              <div className="text-xs font-semibold" style={{ color: active ? 'var(--text)' : 'var(--text)' }}>{name}</div>
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
