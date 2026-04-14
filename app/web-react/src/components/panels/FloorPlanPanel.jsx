import { useRef, useState } from 'react';
import { Upload, Server, Crosshair } from 'lucide-react';
import { useStore } from '../../store';
import { floorPlanApi } from '../../api/client';
import { useToast } from '../../hooks/useToast';

export function FloorPlanPanel({ canvasRef }) {
  const toast = useToast();
  const fileInputRef = useRef(null);
  const [isDragging, setIsDragging] = useState(false);
  const [calDist, setCalDist] = useState(1);
  const [calStatus, setCalStatus] = useState('Click "Set Scale" then click two points on the floor plan');

  const activeVenueId = useStore(s => s.activeVenueId);
  const activeFpId    = useStore(s => s.activeFpId);
  const scale         = useStore(s => s.scale);
  const scaleCal      = useStore(s => s.scaleCal);
  const floorPlanLoaded = useStore(s => s.floorPlanLoaded);
  const setFloorPlan  = useStore(s => s.setFloorPlan);
  const setActiveFp   = useStore(s => s.setActiveFp);
  const setScale      = useStore(s => s.setScale);
  const startCal      = useStore(s => s.startCal);
  const resetCal      = useStore(s => s.resetCal);

  async function handleFile(file) {
    if (!file) return;
    if (!activeVenueId) { toast('Create or select a venue first', 'error'); return; }

    const reader = new FileReader();
    reader.onload = async (ev) => {
      const dataUrl = ev.target.result;
      setFloorPlan(dataUrl);
      setTimeout(() => canvasRef.current?.fitToScreen(), 100);

      try {
        const formData = new FormData();
        formData.append('file', file);
        if (!activeFpId) {
          formData.append('name', 'Floor 1');
          formData.append('floor_number', '1');
          const res = await floorPlanApi.create(activeVenueId, formData);
          const fp  = await res.json();
          setActiveFp(fp.id);
          toast('Floor plan uploaded to server', 'success');
        } else {
          await floorPlanApi.putImage(activeFpId, formData);
          toast('Floor plan updated on server', 'success');
        }
      } catch (e) {
        toast('Saved locally — upload failed: ' + e.message, 'info');
      }
    };
    reader.readAsDataURL(file);
  }

  async function loadFromServer() {
    if (!activeFpId) { toast('No floor plan selected', 'error'); return; }
    try {
      const res  = await floorPlanApi.getImage(activeFpId);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      setFloorPlan(url);
      setTimeout(() => canvasRef.current?.fitToScreen(), 100);
      toast('Floor plan loaded from server', 'success');
    } catch (e) {
      toast('Failed: ' + e.message, 'error');
    }
  }

  function confirmCalibration() {
    const pts = scaleCal.pts;
    if (pts.length < 2 || calDist <= 0) return;
    const dx = pts[1].x - pts[0].x, dy = pts[1].y - pts[0].y;
    const px = Math.hypot(dx, dy);
    const newScale = px / calDist;
    setScale(newScale);
    resetCal();
    canvasRef.current?.clearOverlay();
    setCalStatus(`Calibrated: ${newScale.toFixed(2)} px/m`);
    toast(`Scale set to ${newScale.toFixed(2)} px/m`, 'success');
  }

  return (
    <div className="animate-fade-in-up">
      <Section title="Floor Plan">
        {/* Drop zone */}
        <div
          className={`border-2 border-dashed rounded-lg text-center cursor-pointer transition-all duration-200 mb-2 ${isDragging ? 'border-purple-500 bg-purple-500/10' : ''}`}
          style={{ padding: '18px 14px', borderColor: isDragging ? 'var(--primary)' : 'var(--border)', color: isDragging ? 'var(--primary-b)' : 'var(--text-muted)' }}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={e => { e.preventDefault(); setIsDragging(false); handleFile(e.dataTransfer.files[0]); }}
        >
          <Upload size={18} className="mx-auto mb-1.5" style={{ color: 'var(--text-dim)' }} />
          <div className="text-xs">Drop PNG / SVG / JPG here</div>
          <div className="text-[10px] mt-1" style={{ color: 'var(--text-dim)' }}>or click to browse</div>
          {floorPlanLoaded && <div className="text-[10px] mt-1" style={{ color: 'var(--green)' }}>✓ Floor plan loaded</div>}
        </div>
        <input ref={fileInputRef} type="file" accept=".png,.svg,.jpg,.jpeg" style={{ display: 'none' }} onChange={e => handleFile(e.target.files[0])} />
        <button className="btn-secondary flex items-center justify-center gap-1.5" onClick={loadFromServer}>
          <Server size={11} /> Load from server
        </button>
      </Section>

      <Section title="Scale Calibration">
        <Row label="px / m">
          <input
            type="number" min="0.1" step="0.1" value={scale.toFixed(2)}
            className="panel-input text-right" style={{ width: 80 }}
            onChange={e => { const v = parseFloat(e.target.value); if (v > 0) setScale(v); }}
          />
        </Row>
        <button
          className="btn-secondary flex items-center justify-center gap-1.5"
          onClick={() => { startCal(); setCalStatus('Click first point on the floor plan'); }}
        >
          <Crosshair size={11} /> Set Scale (2-point)
        </button>
        <div className="text-[10px] mt-1.5 leading-snug" style={{ color: 'var(--text-muted)' }}>{calStatus}</div>
        {scaleCal.pts.length > 0 && (
          <div className="mt-2">
            <div className="text-[10px] mb-1" style={{ color: 'var(--text-dim)' }}>Points selected: {scaleCal.pts.length}/2</div>
          </div>
        )}
        <div className="mt-2">
          <Row label="Distance (m)">
            <input type="number" min="0.1" step="0.1" value={calDist} className="panel-input text-right" style={{ width: 70 }} onChange={e => setCalDist(parseFloat(e.target.value))} />
          </Row>
          <button className="btn-primary mt-1" disabled={scaleCal.pts.length < 2} onClick={confirmCalibration}>Apply</button>
        </div>
      </Section>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
      <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>{title}</div>
      {children}
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
