import { Download, CheckCircle, Circle } from 'lucide-react';
import { useStore } from '../../store';
import { legacyApi } from '../../api/client';
import { useToast } from '../../hooks/useToast';

function downloadJSON(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function ExportPanel() {
  const toast      = useToast();
  const floorPlanLoaded = useStore(s => s.floorPlanLoaded);
  const polygons   = useStore(s => s.polygons);
  const grid       = useStore(s => s.grid);
  const aps        = useStore(s => s.aps);
  const radioMap   = useStore(s => s.radioMap);
  const scale      = useStore(s => s.scale);

  const checks = [
    { label: 'Floor plan loaded',        ok: floorPlanLoaded },
    { label: 'Scale calibrated',         ok: scale > 0 },
    { label: '≥1 polygon drawn',         ok: polygons.length >= 1 },
    { label: 'Grid generated (≥100 pts)',ok: grid.generated && grid.points.length >= 100 },
    { label: '≥3 APs placed',           ok: aps.list.length >= 3 },
    { label: 'Radio map computed',       ok: radioMap.computed },
  ];
  const allGood = checks.every(c => c.ok);

  function exportGrid() {
    const pts = grid.points.map(p => ({ x: p.x / scale, y: p.y / scale }));
    downloadJSON({ scale_px_per_m: scale, grid_spacing_m: grid.spacing, points: pts }, 'trakn_grid.json');
    toast('Grid exported', 'success');
  }

  function exportAPs() {
    downloadJSON({ access_points: aps.list }, 'trakn_aps.json');
    toast('APs exported', 'success');
  }

  async function exportRadioMap() {
    try {
      const data = await legacyApi.getRadioMap();
      downloadJSON(data, 'trakn_radio_map.json');
      toast('Radio map exported', 'success');
    } catch {
      if (radioMap.data) {
        downloadJSON({ radio_map: radioMap.data }, 'trakn_radio_map.json');
        toast('Radio map exported (local cache)', 'info');
      } else {
        toast('No radio map data available', 'error');
      }
    }
  }

  return (
    <div className="animate-fade-in-up">
      {/* Checklist */}
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>System Readiness</div>
        <div className="space-y-1.5">
          {checks.map(c => (
            <div key={c.label} className="flex items-center gap-2">
              {c.ok
                ? <CheckCircle size={14} style={{ color: 'var(--green)', flexShrink: 0 }} />
                : <Circle size={14} style={{ color: 'var(--text-dim)', flexShrink: 0 }} />}
              <span className="text-[11px]" style={{ color: c.ok ? 'var(--green)' : 'var(--text-muted)' }}>{c.label}</span>
            </div>
          ))}
        </div>
        {allGood && (
          <div
            className="mt-3 p-2 rounded text-center text-xs font-semibold animate-scale-in"
            style={{ background: 'var(--green-dim)', border: '1px solid rgba(34,197,94,0.3)', color: 'var(--green)' }}
          >
            System Ready — all checks passed
          </div>
        )}
      </div>

      {/* Export buttons */}
      <div className="p-3 space-y-1">
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Export Files</div>

        {[
          { label: 'Grid JSON',       action: exportGrid,     disabled: !grid.generated },
          { label: 'APs JSON',        action: exportAPs,      disabled: aps.list.length === 0 },
          { label: 'Radio Map JSON',  action: exportRadioMap, disabled: !radioMap.computed },
        ].map(item => (
          <div key={item.label} className="flex items-center justify-between py-1.5" style={{ borderBottom: '1px solid var(--border)' }}>
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{item.label}</span>
            <button
              className="flex items-center gap-1 text-[10px] px-2 py-1 rounded transition-all cursor-pointer"
              style={{ background: 'var(--bg4)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}
              disabled={item.disabled}
              onClick={item.action}
              onMouseEnter={e => { if (!item.disabled) { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.color = 'var(--primary-b)'; } }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text-muted)'; }}
            >
              <Download size={10} /> Download
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
