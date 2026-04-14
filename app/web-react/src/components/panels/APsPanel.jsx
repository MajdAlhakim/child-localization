import { useStore } from '../../store';
import { Wifi, Thermometer } from 'lucide-react';

export function APsPanel({ liveTs }) {
  const aps      = useStore(s => s.aps);
  const selectAP = useStore(s => s.selectAP);
  const heatmap  = useStore(s => s.heatmap);
  const setHeatmapAP  = useStore(s => s.setHeatmapAP);
  const clearHeatmap  = useStore(s => s.clearHeatmap);
  const toggleHeatmap = useStore(s => s.toggleHeatmap);
  const isOffline = useStore(s => s.isOffline);

  const selectedAP = aps.list.find(a => a.bssid === aps.selected);

  return (
    <div className="animate-fade-in-up">
      {/* Sync status */}
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Live Sync — Android Tool</div>
        <div className="text-[11px] mb-2 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          APs are placed via the Android AP Tool.<br />They appear here automatically within 3 s.
        </div>
        <div
          className="text-[11px] font-mono px-2 py-1.5 rounded"
          style={{
            background: 'var(--bg3)', border: '1px solid var(--border)',
            color: isOffline ? 'var(--red)' : aps.list.length === 0 ? 'var(--yellow)' : 'var(--green)',
          }}
        >
          {isOffline
            ? '● Backend unreachable'
            : aps.list.length === 0
            ? '● Connected — waiting for first AP…'
            : `● Live — ${aps.list.length} AP${aps.list.length !== 1 ? 's' : ''} synced${liveTs ? ' at ' + liveTs : ''}`}
        </div>
        <div className="text-[10px] mt-2 leading-relaxed" style={{ color: 'var(--text-dim)' }}>
          Steps: Open Android AP Tool → Scan tab → Map tab → Tap location → Confirm
        </div>
      </div>

      {/* AP list */}
      <div className="p-3" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between mb-2">
          <div className="text-[10px] uppercase tracking-[1px] font-mono" style={{ color: 'var(--text-dim)' }}>Synced APs</div>
          <span className="text-xs font-mono" style={{ color: 'var(--orange)' }}>{aps.list.length}</span>
        </div>
        {aps.list.length === 0 ? (
          <div className="text-[11px] text-center py-3" style={{ color: 'var(--text-dim)' }}>No APs synced yet</div>
        ) : (
          <div className="max-h-48 overflow-y-auto space-y-1">
            {aps.list.map(ap => (
              <div
                key={ap.bssid}
                onClick={() => selectAP(ap.bssid)}
                className="px-2 py-1.5 rounded cursor-pointer transition-all duration-150 animate-fade-in-up"
                style={{
                  border: `1px solid ${ap.bssid === aps.selected ? 'var(--orange)' : 'transparent'}`,
                  background: ap.bssid === aps.selected ? 'var(--orange-dim)' : 'transparent',
                }}
                onMouseEnter={e => { if (ap.bssid !== aps.selected) { e.currentTarget.style.background = 'var(--bg3)'; e.currentTarget.style.transform = 'translateX(2px)'; } }}
                onMouseLeave={e => { if (ap.bssid !== aps.selected) { e.currentTarget.style.background = ''; e.currentTarget.style.transform = ''; } }}
              >
                <div className="flex items-center gap-1 mb-0.5">
                  <Wifi size={10} style={{ color: 'var(--orange)' }} />
                  <div className="text-[11px] font-medium" style={{ color: 'var(--text)' }}>{ap.ssid || '—'}</div>
                </div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>{ap.bssid}</div>
                <div className="font-mono text-[10px]" style={{ color: 'var(--text-dim)' }}>({ap.x.toFixed(1)}m, {ap.y.toFixed(1)}m)</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Selected AP heatmap */}
      {selectedAP && (
        <div className="p-3">
          <div className="text-[10px] uppercase tracking-[1px] mb-2 font-mono" style={{ color: 'var(--text-dim)' }}>Selected AP Heatmap</div>
          <div className="text-[10px] mb-2" style={{ color: 'var(--text-muted)' }}>
            {selectedAP.ssid || 'AP'} | RSSI ref: {selectedAP.rssi_ref} dBm | n: {selectedAP.path_loss_n}
          </div>
          <button
            className="btn-secondary flex items-center justify-center gap-1.5"
            onClick={() => { setHeatmapAP(selectedAP.bssid); }}
          >
            <Thermometer size={11} /> {heatmap.visible ? 'Refresh' : 'Show'} Heatmap
          </button>
          {heatmap.visible && (
            <button className="btn-secondary danger" onClick={clearHeatmap}>Clear Heatmap</button>
          )}
          {heatmap.visible && (
            <div className="flex items-center gap-1.5 mt-2 text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
              <span>strong</span>
              <div className="flex-1 h-1.5 rounded" style={{ background: 'linear-gradient(to right, #22c55e, #eab308, #ef4444)' }} />
              <span>weak</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
