import { create } from 'zustand';

const DEFAULT_GRID = { points: [], spacing: 0.5, visible: true, generated: false };
const DEFAULT_APS  = { list: [], selected: null };
const DEFAULT_RM   = { taskId: null, status: null, data: null, computed: false };
const DEFAULT_CAL  = { active: false, pts: [] };
const DEFAULT_DRAW = { active: false, vertices: [] };

export const useStore = create((set, get) => ({
  // ── Navigation
  step: 1,
  setStep: (step) => set({ step }),

  // ── Canvas tool
  tool: 'select',
  setTool: (tool) => set({ tool }),

  // ── Scale
  scale: 10.0,
  setScale: (scale) => set({ scale }),

  // ── Offline / live
  isOffline: false,
  setOffline: (isOffline) => set({ isOffline }),

  // ── Venues
  allVenues: [],
  activeVenueId: null,
  activeFpId: null,
  setVenues:     (allVenues)   => set({ allVenues }),
  setActiveVenue:(id)          => { set({ activeVenueId: id }); localStorage.setItem('trakn_active_venue', id || ''); },
  setActiveFp:   (id)          => { set({ activeFpId: id });    localStorage.setItem('trakn_active_fp', id || ''); },
  addVenue:      (venue)       => set(s => ({ allVenues: [...s.allVenues, { ...venue, floor_plans: [] }] })),
  removeVenue:   (id)          => set(s => ({ allVenues: s.allVenues.filter(v => v.id !== id) })),

  // ── Floor plan
  floorPlanLoaded: false,
  floorPlanImageData: null,     // data URL or blob URL
  setFloorPlan: (dataUrl) => set({ floorPlanLoaded: !!dataUrl, floorPlanImageData: dataUrl }),

  // ── Calibration
  scaleCal: DEFAULT_CAL,
  startCal: () => set({ scaleCal: { active: true, pts: [] } }),
  addCalPt: (pt) => {
    const pts = [...get().scaleCal.pts, pt];
    set({ scaleCal: { active: pts.length < 2, pts } });
    return pts;
  },
  resetCal: () => set({ scaleCal: DEFAULT_CAL }),

  // ── Polygons
  polygons: [],
  addPolygon:    (poly)   => set(s => ({ polygons: [...s.polygons, poly] })),
  deletePolygon: (id)     => set(s => ({ polygons: s.polygons.filter(p => p.id !== id) })),
  clearPolygons: ()       => set({ polygons: [] }),

  // ── Drawing
  drawing: DEFAULT_DRAW,
  addDrawVertex:  (pt) => set(s => ({ drawing: { active: true, vertices: [...s.drawing.vertices, pt] } })),
  popDrawVertex:  ()   => set(s => {
    const verts = s.drawing.vertices.slice(0, -1);
    return { drawing: { active: verts.length > 0, vertices: verts } };
  }),
  cancelDrawing: () => set({ drawing: DEFAULT_DRAW }),
  commitDraw:    ()  => set({ drawing: DEFAULT_DRAW }),

  // ── Grid
  grid: DEFAULT_GRID,
  setGrid:    (updates) => set(s => ({ grid: { ...s.grid, ...updates } })),
  clearGrid:  ()        => set({ grid: DEFAULT_GRID }),
  toggleGridVisible: () => set(s => ({ grid: { ...s.grid, visible: !s.grid.visible } })),

  // ── APs
  aps: DEFAULT_APS,
  knownBssids: new Set(),
  setAPs: (list) => set({ aps: { list, selected: null }, knownBssids: new Set(list.map(a => a.bssid)) }),
  updateAPs: (list) => {
    const prev = get().knownBssids;
    const fresh = new Set(list.map(a => a.bssid));
    const newOnes = [...fresh].filter(b => !prev.has(b));
    set(s => ({ aps: { ...s.aps, list }, knownBssids: fresh }));
    return newOnes;
  },
  selectAP: (bssid) => set(s => ({ aps: { ...s.aps, selected: bssid } })),

  // ── Heatmap
  heatmap: { visible: false, apBssid: null },
  toggleHeatmap: () => set(s => ({ heatmap: { ...s.heatmap, visible: !s.heatmap.visible } })),
  setHeatmapAP:  (bssid) => set({ heatmap: { visible: true, apBssid: bssid } }),
  clearHeatmap:  ()      => set({ heatmap: { visible: false, apBssid: null } }),

  // ── Radio map
  radioMap: DEFAULT_RM,
  setRadioMap: (updates) => set(s => ({ radioMap: { ...s.radioMap, ...updates } })),

  // ── Full reset (when switching venue)
  resetCanvas: () => set({
    floorPlanLoaded: false,
    floorPlanImageData: null,
    polygons: [],
    drawing: DEFAULT_DRAW,
    grid: DEFAULT_GRID,
    aps: DEFAULT_APS,
    knownBssids: new Set(),
    heatmap: { visible: false, apBssid: null },
    radioMap: DEFAULT_RM,
    scaleCal: DEFAULT_CAL,
    scale: 10.0,
    step: 1,
  }),
}));
