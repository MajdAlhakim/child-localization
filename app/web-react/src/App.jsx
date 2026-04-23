import { useEffect, useRef, useState, useCallback } from 'react';
import { ToastProvider, useToast } from './hooks/useToast';
import { useLiveSync } from './hooks/useLiveSync';
import { useStore } from './store';
import { checkHealth, venueApi, floorPlanApi } from './api/client';

import { Header } from './components/layout/Header';
import { Sidebar } from './components/layout/Sidebar';
import MapCanvas from './components/canvas/MapCanvas';
import { FloorPlanPanel } from './components/panels/FloorPlanPanel';
import { ZonesPanel } from './components/panels/ZonesPanel';
import { GridPanel } from './components/panels/GridPanel';
import { APsPanel } from './components/panels/APsPanel';
import { RadioMapPanel } from './components/panels/RadioMapPanel';
import { ExportPanel } from './components/panels/ExportPanel';
import { VenuesDashboard } from './components/dashboard/VenuesDashboard';
import { FloorPlansDashboard } from './components/dashboard/FloorPlansDashboard';

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

  const [appMode, setAppMode]       = useState('venues'); // 'venues' | 'floorplans' | 'mapping'
  const [zoom, setZoom]             = useState(100);
  const [liveStatus, setLiveStatus] = useState('offline');
  const [liveTs, setLiveTs]         = useState('');
  const [inspectEntries, setInspectEntries] = useState([]);

  const step           = useStore(s => s.step);
  const setStep        = useStore(s => s.setStep);
  const isOffline      = useStore(s => s.isOffline);
  const allVenues      = useStore(s => s.allVenues);
  const activeVenueId  = useStore(s => s.activeVenueId);
  const activeFpId     = useStore(s => s.activeFpId);
  const setVenues      = useStore(s => s.setVenues);
  const addVenue       = useStore(s => s.addVenue);
  const removeVenue    = useStore(s => s.removeVenue);
  const setActiveVenue = useStore(s => s.setActiveVenue);
  const setActiveFp    = useStore(s => s.setActiveFp);
  const resetCanvas    = useStore(s => s.resetCanvas);
  const setFloorPlan   = useStore(s => s.setFloorPlan);
  const setAPs         = useStore(s => s.setAPs);
  const setGrid        = useStore(s => s.setGrid);
  const scale          = useStore(s => s.scale);
  const setScale       = useStore(s => s.setScale);
  const addFloorPlanToVenue      = useStore(s => s.addFloorPlanToVenue);
  const removeFloorPlanFromVenue = useStore(s => s.removeFloorPlanFromVenue);

  // ── Live sync (active when on step 4 in mapping mode) ────────────────────
  useLiveSync(appMode === 'mapping' && step === 4);
  const aps = useStore(s => s.aps);
  useEffect(() => {
    if (appMode !== 'mapping' || step !== 4) return;
    setLiveStatus(isOffline ? 'offline' : aps.list.length === 0 ? 'waiting' : 'live');
    if (!isOffline) setLiveTs(new Date().toLocaleTimeString());
  }, [aps.list, isOffline, step, appMode]);

  // ── Boot: health check + load venues ─────────────────────────────────────
  useEffect(() => {
    (async () => {
      try {
        await checkHealth();
        setLiveStatus('waiting');
      } catch {
        setLiveStatus('offline');
        toast('Backend offline — some features unavailable', 'error');
      }
      try {
        const data = await venueApi.list();
        setVenues(data.venues || []);
      } catch (e) {
        toast('Could not load venues: ' + e.message, 'error');
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Load floor plan canvas data ───────────────────────────────────────────
  async function loadFloorPlanData(fpId) {
    setActiveFp(fpId);

    try {
      const res  = await floorPlanApi.getImage(fpId);
      const blob = await res.blob();
      setFloorPlan(URL.createObjectURL(blob));
      setTimeout(() => canvasRef.current?.fitToScreen(), 150);
    } catch { /* no image yet */ }

    try {
      const grid = await floorPlanApi.getGrid(fpId);
      const s = grid.scale_px_per_m || scale;
      setScale(s);
      setGrid({ points: grid.points.map(p => ({ x: p.x * s, y: p.y * s })), spacing: grid.grid_spacing_m || 0.5, generated: true });
    } catch { /* no grid yet */ }

    try {
      const data = await floorPlanApi.getAPs(fpId);
      setAPs(data.access_points || []);
    } catch { /* no APs yet */ }
  }

  // ── Navigation ────────────────────────────────────────────────────────────
  function handleOpenVenue(venueId) {
    setActiveVenue(venueId);
    setAppMode('floorplans');
  }

  async function handleOpenFloorPlan(fpId) {
    resetCanvas();
    await loadFloorPlanData(fpId);
    setAppMode('mapping');
    setStep(1);
  }

  function handleBackToVenues() {
    setAppMode('venues');
  }

  function handleBackToFloorPlans() {
    setAppMode('floorplans');
  }

  // ── Venue CRUD ────────────────────────────────────────────────────────────
  async function handleCreateVenue(name) {
    try {
      const venue = await venueApi.create(name);
      addVenue(venue);
      toast(`Venue "${name}" created`, 'success');
    } catch (e) {
      toast('Failed to create venue: ' + e.message, 'error');
      throw e;
    }
  }

  async function handleDeleteVenue(venueId, venueName) {
    if (!confirm(`Delete venue "${venueName}"?\n\nThis permanently deletes all floor plans and AP data.`)) return;
    try {
      await venueApi.delete(venueId);
      removeVenue(venueId);
      if (activeVenueId === venueId) {
        setActiveVenue(null);
        resetCanvas();
      }
      toast('Venue deleted', 'success');
      setAppMode('venues');
    } catch (e) {
      toast('Failed to delete venue: ' + e.message, 'error');
    }
  }

  // ── Floor plan CRUD ───────────────────────────────────────────────────────
  async function handleAddFloor(floorNumber, name) {
    if (!activeVenueId) { toast('No venue selected', 'error'); return; }
    try {
      const res = await floorPlanApi.createMeta(activeVenueId, name, floorNumber);
      const fp  = await res.json();
      addFloorPlanToVenue(activeVenueId, fp);
      toast(`Floor ${floorNumber} "${name}" created — click it to start mapping`, 'success');
    } catch (e) {
      toast('Failed to create floor plan: ' + e.message, 'error');
      throw e;
    }
  }

  async function handleDeleteFloorPlan(fpId, fpName) {
    if (!confirm(`Delete floor plan "${fpName}"?\n\nThis permanently deletes its image, grid, and all APs.`)) return;
    try {
      await floorPlanApi.delete(fpId);
      removeFloorPlanFromVenue(activeVenueId, fpId);
      if (activeFpId === fpId) { setActiveFp(null); resetCanvas(); }
      toast('Floor plan deleted', 'success');
    } catch (e) {
      toast('Failed to delete floor plan: ' + e.message, 'error');
    }
  }

  const fitToScreen = useCallback(() => canvasRef.current?.fitToScreen(), []);
  const activeVenue = allVenues.find(v => v.id === activeVenueId);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100dvh', overflow: 'hidden' }}>
      <Header zoom={zoom} onFit={fitToScreen} liveStatus={liveStatus} />

      {appMode === 'venues' && (
        <VenuesDashboard
          venues={allVenues}
          onOpen={handleOpenVenue}
          onDelete={handleDeleteVenue}
          onCreateVenue={handleCreateVenue}
        />
      )}

      {appMode === 'floorplans' && (
        <FloorPlansDashboard
          venue={activeVenue}
          onBack={handleBackToVenues}
          onOpen={handleOpenFloorPlan}
          onAdd={handleAddFloor}
          onDelete={handleDeleteFloorPlan}
        />
      )}

      {appMode === 'mapping' && (
        <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
          {/* Left Sidebar */}
          <Sidebar onBack={handleBackToFloorPlans} />

          {/* Canvas area */}
          <div style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#050810' }}>
            {isOffline && (
              <div className="absolute top-0 left-0 right-0 z-20 text-center text-xs font-medium py-1.5 px-3 animate-fade-in-up"
                style={{ background: 'rgba(234,179,8,0.1)', borderBottom: '1px solid rgba(234,179,8,0.3)', color: 'var(--yellow)' }}>
                ⚠ Backend unreachable — working in local mode
              </div>
            )}
            <ModeBanner />
            <MapCanvas ref={canvasRef} onZoomChange={setZoom} onInspect={setInspectEntries} />
          </div>

          {/* Right panel */}
          <div style={{ width: 220, flexShrink: 0, overflowY: 'auto', background: 'var(--bg2)', borderLeft: '1px solid var(--border)' }}>
            {step === 1 && <FloorPlanPanel canvasRef={canvasRef} />}
            {step === 2 && <ZonesPanel />}
            {step === 3 && <GridPanel />}
            {step === 4 && <APsPanel liveTs={liveTs} />}
            {step === 5 && <RadioMapPanel inspectEntries={inspectEntries} />}
            {step === 6 && <ExportPanel />}
          </div>
        </div>
      )}
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
