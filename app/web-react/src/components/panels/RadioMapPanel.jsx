import { useState } from 'react';
import { Cpu, Thermometer, XCircle } from 'lucide-react';
import { useStore } from '../../store';
import { legacyApi } from '../../api/client';
import { useToast } from '../../hooks/useToast';

export function RadioMapPanel({ inspectEntries }) {
  const toast      = useToast();
  const radioMap   = useStore(s => s.radioMap);
  const setRadioMap = useStore(s => s.setRadioMap);
  const aps        = useStore(s => s.aps);
  const grid       = useStore(s => s.grid);
  const setHeatmapAP = useStore(s => s.setHeatmapAP);
  const clearHeatmap = useStore(s => s.clearHeatmap);
  const [selectedBssid, setSelectedBssid] = useState('');

  async function computeRadioMap() {
    setRadioMap({ status: 'starting', taskId: null });
    try {
      const res = await legacyApi.computeRadioMap();
      const taskId = res.task_id;
      setRadioMap({ taskId, status: 'computing' });
      pollStatus(taskId);
    } catch (e) {
      setRadioMap({ status: null });
      toast('Failed to start: ' + e.message, 'error');
    }
  }

  function pollStatus(taskId) {
    const iv = setInterval(async () => {
      try {
        const data = await legacyApi.radioMapStatus(taskId);
        setRadioMap({ status: data.status, progress: data.progress || 0 });
        if (data.status === 'done') {
          clearInterval(iv);
          setRadioMap({ computed: true, status: 'done', progress: 100 });
          toast('Radio map computed!', 'success');
          loadRadioMap();
        } else if (data.status === 'failed') {
          clearInterval(iv);
          setRadioMap({ status: 'failed' });
          toast('Radio map computation failed', 'error');
        }
      } catch {
        clearInterval(iv);
        setRadioMap({ status: null });
        toast('Status poll failed', 'error');
      }
    }, 500);
  }

  async function loadRadioMap() {
    try {
      const data = await legacyApi.getRadioMap();
      setRadioMap({ data: data.radio_map || [] });
    } catch (e) {
      toast('Failed to load radio map: ' + e.message, 'error');
    }
  }

  const isComputing = radioMap.status === 'computing' || radioMap.status === 'starting';
  const progress    = radioMap.progress || 0;
  const bssids      = radioMap.data ? [...new Set(radioMap.data.map(e => e.bssid))] : [];

  return (
    <div className="animate-fade-in-up">
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Radio Map Computation</div>
        <button
          className="btn-primary flex items-center justify-center gap-1.5"
          disabled={isComputing}
          onClick={computeRadioMap}
        >
          {isComputing ? <><span className="spinner" /> Computing…</> : <><Cpu size={12} /> Compute Radio Map</>}
        </button>
        <div className="progress-wrap mt-2">
          <div className="progress-fill" style={{ width: `${progress}%` }} />
        </div>
        <div className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>
          {isComputing ? `Computing… ${progress}%` : radioMap.computed ? 'Done ✓' : 'Ready'}
        </div>
      </div>

      {radioMap.computed && (
        <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
          <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Summary</div>
          <Row label="APs"><Val>{aps.list.length}</Val></Row>
          <Row label="Grid pts"><Val>{grid.points.length}</Val></Row>
          <Row label="Entries"><Val>{radioMap.data?.length || 0}</Val></Row>

          <div className="mt-2 mb-1 text-[10px] uppercase tracking-[1px] font-mono" style={{ color: 'var(--text-dim)' }}>AP Heatmap</div>
          <select
            value={selectedBssid}
            onChange={e => setSelectedBssid(e.target.value)}
            className="panel-select mb-1.5"
          >
            <option value="">Select AP…</option>
            {bssids.map(b => <option key={b} value={b}>{b}</option>)}
          </select>
          <button
            className="btn-secondary flex items-center justify-center gap-1.5"
            disabled={!selectedBssid}
            onClick={() => selectedBssid && setHeatmapAP(selectedBssid)}
          >
            <Thermometer size={11} /> Show Heatmap
          </button>
          <button className="btn-secondary danger flex items-center justify-center gap-1.5" onClick={clearHeatmap}>
            <XCircle size={11} /> Clear Heatmap
          </button>
        </div>
      )}

      {/* Point inspector */}
      {radioMap.computed && (
        <div className="p-3">
          <div className="text-[10px] uppercase tracking-[1px] mb-1 font-mono" style={{ color: 'var(--text-dim)' }}>Point Inspector</div>
          <div className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>Click a grid point to inspect RSSI from all APs</div>
          {inspectEntries.length > 0 && (
            <div className="space-y-0.5">
              {inspectEntries.map(e => (
                <div key={e.bssid} className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  <span style={{ color: 'var(--text)' }}>{e.bssid.slice(-8)}</span>: {e.rssi_est.toFixed(1)} dBm ({e.dist_m.toFixed(1)} m)
                </div>
              ))}
            </div>
          )}
        </div>
      )}
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
