import { useState } from 'react';
import { Grid, Save, Eye, EyeOff } from 'lucide-react';
import { useStore } from '../../store';
import { legacyApi } from '../../api/client';
import { useToast } from '../../hooks/useToast';

function pointInPolygon(px, py, verts) {
  let inside = false;
  for (let i = 0, j = verts.length - 1; i < verts.length; j = i++) {
    const xi = verts[i].x, yi = verts[i].y, xj = verts[j].x, yj = verts[j].y;
    if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}

export function GridPanel() {
  const toast    = useToast();
  const [saving, setSaving] = useState(false);

  const polygons = useStore(s => s.polygons);
  const grid     = useStore(s => s.grid);
  const scale    = useStore(s => s.scale);
  const setGrid  = useStore(s => s.setGrid);
  const clearGrid = useStore(s => s.clearGrid);
  const toggleGridVisible = useStore(s => s.toggleGridVisible);

  function generateGrid() {
    if (polygons.length === 0) { toast('Draw at least one walkable zone first', 'error'); return; }
    const spacing = grid.spacing;
    const spacingPx = spacing * scale;

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    polygons.forEach(p => p.vertices.forEach(v => {
      minX = Math.min(minX, v.x); minY = Math.min(minY, v.y);
      maxX = Math.max(maxX, v.x); maxY = Math.max(maxY, v.y);
    }));

    const points = [];
    for (let x = minX; x <= maxX; x += spacingPx) {
      for (let y = minY; y <= maxY; y += spacingPx) {
        for (const poly of polygons) {
          if (pointInPolygon(x, y, poly.vertices)) { points.push({ x, y }); break; }
        }
      }
    }

    setGrid({ points, spacing, generated: true });
    toast(`Generated ${points.length} grid points`, 'success');
  }

  async function saveGrid() {
    if (grid.points.length === 0) { toast('Generate grid first', 'error'); return; }
    setSaving(true);
    try {
      const apiPoints = grid.points.map(p => ({
        x: parseFloat((p.x / scale).toFixed(3)),
        y: parseFloat((p.y / scale).toFixed(3)),
      }));
      await legacyApi.saveGrid({ scale_px_per_m: scale, grid_spacing_m: grid.spacing, points: apiPoints });
      toast(`Saved ${grid.points.length} points to server`, 'success');
    } catch (e) {
      toast('Failed to save grid: ' + e.message, 'error');
    } finally {
      setSaving(false);
    }
  }

  const areaPx2 = grid.points.length * grid.spacing * grid.spacing;

  return (
    <div className="animate-fade-in-up">
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Grid Generation</div>
        <Row label="Spacing">
          <select
            value={grid.spacing}
            onChange={e => setGrid({ spacing: parseFloat(e.target.value) })}
            className="panel-select" style={{ width: 90 }}
          >
            <option value="0.25">0.25 m</option>
            <option value="0.5">0.5 m</option>
            <option value="1.0">1.0 m</option>
          </select>
        </Row>
        <button className="btn-primary flex items-center justify-center gap-1.5" onClick={generateGrid}>
          <Grid size={12} /> Generate Grid
        </button>
        <button className="btn-secondary flex items-center justify-center gap-1.5" onClick={toggleGridVisible}>
          {grid.visible ? <EyeOff size={11} /> : <Eye size={11} />} Toggle Grid <kbd className="text-[9px] opacity-60">G</kbd>
        </button>
      </div>

      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Grid Stats</div>
        <Row label="Points"><Val>{grid.points.length}</Val></Row>
        <Row label="Spacing"><Val>{grid.spacing} m</Val></Row>
        <Row label="Area est."><Val>{areaPx2.toFixed(1)} m²</Val></Row>
      </div>

      <div className="p-3">
        <button
          className="btn-primary flex items-center justify-center gap-1.5"
          disabled={!grid.generated || saving}
          onClick={saveGrid}
        >
          {saving ? <><span className="spinner" /> Saving…</> : <><Save size={12} /> Save Grid to Server</>}
        </button>
      </div>
    </div>
  );
}

function Row({ label, children }) {
  return (
    <div className="flex items-center justify-between gap-2 mb-1.5">
      <label className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{label}</label>
      {children}
    </div>
  );
}
function Val({ children }) {
  return <span className="font-mono text-[11px]" style={{ color: 'var(--text)' }}>{children}</span>;
}
