import { useEffect, useRef, useState, useCallback } from 'react';
import { ToastProvider, useToast } from './hooks/useToast';
import { useLiveSync } from './hooks/useLiveSync';
import { useStore } from './store';
import { checkHealth, venueApi, floorPlanApi, legacyApi } from './api/client';

import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import MapCanvas from './components/canvas/MapCanvas';
import { FloorPlanPanel } from './components/panels/FloorPlanPanel';
import { ZonesPanel } from './components/panels/ZonesPanel';
import { GridPanel } from './components/panels/GridPanel';
import { APsPanel } from './components/panels/APsPanel';
import { RadioMapPanel } from './components/panels/RadioMapPanel';
import { ExportPanel } from './components/panels/ExportPanel';
import { CreateVenueModal } from './components/modals/CreateVenueModal';

export default function App() {
  return (
    <ToastProvider>
      <AppInner />
    </ToastProvider>
  );
}

function AppInner() {
  const toast = useToast();
  const canvasRef = useRef(null);

  const [zoom, setZoom]             = useState(100);
  const [liveStatus, setLiveStatus] = useState('offline');
  const [liveTs, setLiveTs]         = useState('');
  const [venueModalOpen, setVenueModalOpen] = useState(false);
  const [inspectEntries, setInspectEntries] = useState([]);

  const step          = useStore(s => s.step);
  const setStep       = useStore(s => s.setStep);
  const isOffline     = useStore(s => s.isOffline);
  const allVenues     = useStore(s => s.allVenues);
  const activeVenueId = useStore(s => s.activeVenueId);
  const activeFpId    = useStore(s => s.activeFpId);
  const setVenues     = useStore(s => s.setVenues);
  const addVenue      = useStore(s => s.addVenue);
  const removeVenue   = useStore(s => s.removeVenue);
  const setActiveVenue = useStore(s => s.setActiveVenue);
  const setActiveFp   = useStore(s => s.setActiveFp);
  const resetCanvas   = useStore(s => s.resetCanvas);
  const setFloorPlan  = useStore(s => s.setFloorPlan);
  const setAPs        = useStore(s => s.setAPs);
  const setGrid       = useStore(s => s.setGrid);
  const scale         = useStore(s => s.scale);
  const setScale      = useStore(s => s.setScale);

  // ── Live sync (active when on step 4) ────────────────────────────────────
  const { sync } = useLiveSync(step === 4);
  const aps = useStore(s => s.aps);
  useEffect(() => {
    if (step !== 4) return;
    setLiveStatus(isOffline ? 'offline' : aps.list.length === 0 ? 'waiting' : 'live');
    if (!isOffline) setLiveTs(new Date().toLocaleTimeString());
  }, [aps.list, isOffline, step]);

  // ── Handle venue selector change from sidebar ─────────────────────────────
  // Track the venue ID that was *loaded* (distinct from what the selector shows)
  const loadedVenueRef = useRef(null);

  const switchVenue = useCallback(async (venueId) => {
    if (venueId === loadedVenueRef.current) return;
    loadedVenueRef.current = venueId;
    await loadVenueData(venueId, null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Boot: health + load venues ────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        await checkHealth();
        setLiveStatus('waiting');
      } catch {
        setLiveStatus('offline');
        toast('Backend offline — working in local mode', 'error');
        return;
      }

      try {
        const data = await venueApi.list();
        const venues = data.venues || [];
        setVenues(venues);

        if (venues.length === 0) return;
        const savedVenueId = localStorage.getItem('trakn_active_venue');
        const savedFpId    = localStorage.getItem('trakn_active_fp');
        const venue = (savedVenueId && venues.find(v => v.id === savedVenueId)) || venues[0];
        loadedVenueRef.current = venue.id;
        await loadVenueData(venue.id, savedFpId);
      } catch (e) {
        toast('Could not load venues: ' + e.message, 'error');
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadVenueData(venueId, preferredFpId) {
    resetCanvas();
    setActiveVenue(venueId);
    try {
      const data = await venueApi.get(venueId);
      const fps  = data.floor_plans || [];
      if (fps.length === 0) { setActiveFp(null); return; }
      const fp = (preferredFpId && fps.find(f => f.id === preferredFpId)) || fps[0];
      await loadFloorPlanData(fp.id);
    } catch (e) {
      toast('Failed to load venue: ' + e.message, 'error');
    }
  }

  async function loadFloorPlanData(fpId) {
    setActiveFp(fpId);

    // Floor plan image
    try {
      const res  = await floorPlanApi.getImage(fpId);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      setFloorPlan(url);
      setTimeout(() => canvasRef.current?.fitToScreen(), 150);
    } catch {
      // no image yet
    }

    // Grid
    try {
      const grid = await floorPlanApi.getGrid(fpId);
      const s = grid.scale_px_per_m || scale;
      setScale(s);
      const pts = grid.points.map(p => ({ x: p.x * s, y: p.y * s }));
      setGrid({ points: pts, spacing: grid.grid_spacing_m || 0.5, generated: true });
    } catch {
      // no grid yet
    }

    // APs
    try {
      const data = await legacyApi.getAPs();
      setAPs(data.access_points || []);
    } catch {
      // no APs yet
    }
  }

  // ── Create venue ──────────────────────────────────────────────────────────
  async function handleCreateVenue(name) {
    try {
      const venue = await venueApi.create(name);
      addVenue(venue);
      setActiveVenue(venue.id);
      loadedVenueRef.current = venue.id;
      setActiveFp(null);
      resetCanvas();
      setVenueModalOpen(false);
      toast(`Venue "${name}" created. Upload a floor plan in Step 1.`, 'success');
      setStep(1);
    } catch (e) {
      toast('Failed to create venue: ' + e.message, 'error');
      throw e;
    }
  }

  // ── Delete venue ──────────────────────────────────────────────────────────
  async function handleDeleteVenue() {
    if (!activeVenueId) { toast('No venue selected', 'error'); return; }
    const venue = allVenues.find(v => v.id === activeVenueId);
    if (!venue) return;
    if (!confirm(`Delete venue "${venue.name}"?\n\nThis will permanently delete all floor plans, APs, and grid data.`)) return;
    try {
      await venueApi.delete(activeVenueId);
      removeVenue(activeVenueId);
      resetCanvas();
      const remaining = allVenues.filter(v => v.id !== activeVenueId);
      if (remaining.length > 0) {
        await loadVenueData(remaining[0].id, null);
      } else {
        setActiveVenue(null);
        setActiveFp(null);
        localStorage.removeItem('trakn_active_venue');
        localStorage.removeItem('trakn_active_fp');
      }
      toast('Venue deleted', 'success');
    } catch (e) {
      toast('Failed to delete venue: ' + e.message, 'error');
    }
  }

  const fitToScreen = useCallback(() => canvasRef.current?.fitToScreen(), []);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', overflow: 'hidden' }}>
      <Header zoom={zoom} onFit={fitToScreen} liveStatus={liveStatus} />

      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
        {/* Left Sidebar */}
        <Sidebar
          onNewVenue={() => setVenueModalOpen(true)}
          onDeleteVenue={handleDeleteVenue}
          onVenueSwitch={switchVenue}
        />

        {/* Canvas area */}
        <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#050810' }}>
          {/* Offline banner */}
          {isOffline && (
            <div className="absolute top-0 left-0 right-0 z-20 text-center text-xs font-medium py-1.5 px-3 animate-fade-in-up"
              style={{ background: 'rgba(234,179,8,0.1)', borderBottom: '1px solid rgba(234,179,8,0.3)', color: 'var(--yellow)' }}>
              ⚠ Backend unreachable — working in local mode. Export will still work.
            </div>
          )}
          {/* Mode banner */}
          <ModeBanner />
          {/* Canvas */}
          <MapCanvas
            ref={canvasRef}
            onZoomChange={setZoom}
            onInspect={setInspectEntries}
          />
        </div>

        {/* Right panel */}
        <div
          style={{
            width: 220, flexShrink: 0, overflowY: 'auto',
            background: 'var(--bg2)', borderLeft: '1px solid var(--border)',
          }}
        >
          {step === 1 && <FloorPlanPanel canvasRef={canvasRef} />}
          {step === 2 && <ZonesPanel />}
          {step === 3 && <GridPanel />}
          {step === 4 && <APsPanel liveTs={liveTs} />}
          {step === 5 && <RadioMapPanel inspectEntries={inspectEntries} />}
          {step === 6 && <ExportPanel />}
        </div>
      </div>

      <CreateVenueModal
        open={venueModalOpen}
        onClose={() => setVenueModalOpen(false)}
        onCreate={handleCreateVenue}
      />
    </div>
  );
}

function ModeBanner() {
  const tool = useStore(s => s.tool);
  if (tool === 'select') return null;
  const msg = tool === 'draw'
    ? 'DRAW MODE — click to add vertices | Snap ring to close | Esc to cancel'
    : 'ERASE MODE — click near a polygon edge to delete it';
  return (
    <div
      className="absolute top-2.5 left-1/2 -translate-x-1/2 z-20 text-xs font-medium px-3.5 py-1.5 rounded pointer-events-none animate-fade-in-up"
      style={{ background: 'rgba(124,58,237,0.9)', color: '#fff', border: '1px solid rgba(255,255,255,0.2)' }}
    >
      {msg}
    </div>
  );
}
