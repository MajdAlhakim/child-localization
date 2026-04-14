import { Trash2 } from 'lucide-react';
import { useStore } from '../../store';

export function ZonesPanel() {
  const polygons     = useStore(s => s.polygons);
  const deletePolygon = useStore(s => s.deletePolygon);
  const clearPolygons = useStore(s => s.clearPolygons);
  const scale        = useStore(s => s.scale);

  const totalArea = polygons.reduce((sum, p) => sum + p.area, 0);

  return (
    <div className="animate-fade-in-up">
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] uppercase tracking-[1px] font-mono" style={{ color: 'var(--text-dim)' }}>Walkable Zones</div>
          <span className="text-xs font-mono" style={{ color: 'var(--primary-b)' }}>{polygons.length}</span>
        </div>

        {polygons.length === 0 ? (
          <div className="text-[11px] text-center py-4" style={{ color: 'var(--text-dim)' }}>No zones drawn yet</div>
        ) : (
          <div className="max-h-40 overflow-y-auto space-y-1 mb-2">
            {polygons.map((p, i) => (
              <div
                key={p.id}
                className="flex items-center gap-2 px-2 py-1.5 rounded transition-all duration-150 cursor-pointer"
                style={{ border: '1px solid transparent' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg3)'; e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = ''; e.currentTarget.style.borderColor = 'transparent'; }}
              >
                <div className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ background: 'rgba(124,58,237,0.5)' }} />
                <div className="flex-1 text-[11px] font-medium" style={{ color: 'var(--text)' }}>#{i + 1} ({p.vertices.length} pts)</div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{p.area.toFixed(1)}m²</div>
                <button
                  className="text-[11px] px-1 py-0.5 rounded transition-all"
                  style={{ color: 'var(--text-dim)' }}
                  onClick={() => deletePolygon(p.id)}
                  onMouseEnter={e => { e.currentTarget.style.color = 'var(--red)'; e.currentTarget.style.background = 'var(--red-dim)'; }}
                  onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-dim)'; e.currentTarget.style.background = ''; }}
                >
                  <Trash2 size={11} />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex justify-between items-center py-1" style={{ borderTop: polygons.length ? '1px solid var(--border)' : 'none' }}>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Total area</span>
          <span className="font-mono text-[11px]" style={{ color: 'var(--text)' }}>{totalArea.toFixed(1)} m²</span>
        </div>

        {polygons.length > 0 && (
          <button className="btn-secondary danger" onClick={clearPolygons}>
            <Trash2 size={11} className="inline mr-1" /> Clear all zones
          </button>
        )}
      </div>

      <div className="p-3">
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Instructions</div>
        <div className="text-[10px] leading-relaxed space-y-0.5" style={{ color: 'var(--text-muted)' }}>
          <div><span className="font-medium" style={{ color: 'var(--text)' }}>W</span> — activate draw mode</div>
          <div>Click — add vertex</div>
          <div>Right-click — remove last vertex</div>
          <div>Snap ring — click to close polygon</div>
          <div><span className="font-medium" style={{ color: 'var(--text)' }}>Esc</span> — cancel drawing</div>
          <div><span className="font-medium" style={{ color: 'var(--text)' }}>E</span> — erase polygon</div>
        </div>
      </div>
    </div>
  );
}
