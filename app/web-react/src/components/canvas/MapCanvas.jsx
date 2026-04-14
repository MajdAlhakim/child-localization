import { useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react';
import Konva from 'konva';
import { useStore } from '../../store';

const SNAP_RADIUS = 14;

function rssiToColor(rssi, rssiRef) {
  const strong = rssiRef - 10, weak = rssiRef - 40;
  const t = Math.max(0, Math.min(1, (rssi - weak) / (strong - weak)));
  const r = Math.round(t < 0.5 ? 255 : 255 * (1 - (t - 0.5) * 2));
  const g = Math.round(t < 0.5 ? 255 * t * 2 : 255);
  return `rgba(${r},${g},0,0.6)`;
}

function polygonArea(verts) {
  let a = 0;
  for (let i = 0; i < verts.length; i++) {
    const j = (i + 1) % verts.length;
    a += verts[i].x * verts[j].y - verts[j].x * verts[i].y;
  }
  return Math.abs(a) / 2;
}
function polygonCentroid(verts) {
  let cx = 0, cy = 0;
  verts.forEach(v => { cx += v.x; cy += v.y; });
  return { x: cx / verts.length, y: cy / verts.length };
}
function pointInPolygon(px, py, verts) {
  let inside = false;
  for (let i = 0, j = verts.length - 1; i < verts.length; j = i++) {
    const xi = verts[i].x, yi = verts[i].y, xj = verts[j].x, yj = verts[j].y;
    if (((yi > py) !== (yj > py)) && (px < (xj - xi) * (py - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function ptSegDist(pt, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y;
  if (dx === 0 && dy === 0) return Math.hypot(pt.x - a.x, pt.y - a.y);
  const t = Math.max(0, Math.min(1, ((pt.x - a.x) * dx + (pt.y - a.y) * dy) / (dx * dx + dy * dy)));
  return Math.hypot(pt.x - a.x - t * dx, pt.y - a.y - t * dy);
}

// eslint-disable-next-line react/display-name
const MapCanvas = forwardRef(function MapCanvas({ onZoomChange, onInspect }, ref) {
  const containerRef = useRef(null);
  const stageRef     = useRef(null);
  const layersRef    = useRef({});
  const zoomRef      = useRef(1);
  const panningRef   = useRef(false);
  const panStartRef  = useRef(null);
  const vKeyRef      = useRef(false);
  const stateRef     = useRef({}); // live snapshot for event handlers

  const {
    tool, scale, floorPlanImageData, polygons,
    grid, aps, heatmap, radioMap, scaleCal, drawing,
    addCalPt, resetCal, setScale,
    addDrawVertex, popDrawVertex, cancelDrawing, commitDraw, addPolygon,
    deletePolygon, selectAP, clearHeatmap,
  } = useStore();

  // Keep stateRef fresh every render
  useEffect(() => {
    stateRef.current = {
      tool, scale, polygons, grid, aps, heatmap, radioMap, scaleCal, drawing,
      zoom: zoomRef.current,
    };
  });

  // ── Init stage once ──────────────────────────────────────────────────────
  useEffect(() => {
    const container = containerRef.current;
    const stage = new Konva.Stage({
      container,
      width: container.offsetWidth,
      height: container.offsetHeight,
    });
    stageRef.current = stage;

    const bg      = new Konva.Layer({ name: 'bg' });
    const heatL   = new Konva.Layer({ name: 'heatmap' });
    const gridL   = new Konva.Layer({ name: 'grid' });
    const polyL   = new Konva.Layer({ name: 'poly' });
    const apL     = new Konva.Layer({ name: 'ap' });
    const drawL   = new Konva.Layer({ name: 'drawing' });
    const overlayL= new Konva.Layer({ name: 'overlay' });

    stage.add(bg, heatL, gridL, polyL, apL, drawL, overlayL);
    layersRef.current = { bg, heat: heatL, grid: gridL, poly: polyL, ap: apL, draw: drawL, overlay: overlayL };

    // Resize
    const onResize = () => { stage.width(container.offsetWidth); stage.height(container.offsetHeight); };
    window.addEventListener('resize', onResize);

    // Zoom
    stage.on('wheel', (e) => {
      e.evt.preventDefault();
      const old = zoomRef.current;
      const ptr = stage.getPointerPosition();
      const by  = 1.08;
      const nxt = Math.max(0.05, Math.min(40, e.evt.deltaY < 0 ? old * by : old / by));
      zoomRef.current = nxt;
      const mx = { x: (ptr.x - stage.x()) / old, y: (ptr.y - stage.y()) / old };
      stage.scale({ x: nxt, y: nxt });
      stage.position({ x: ptr.x - mx.x * nxt, y: ptr.y - mx.y * nxt });
      stage.batchDraw();
      onZoomChange(Math.round(nxt * 100));
    });

    // Pan
    stage.on('mousedown', (e) => {
      if (e.evt.button === 1 || (e.evt.button === 0 && vKeyRef.current)) {
        panningRef.current = true;
        panStartRef.current = { x: e.evt.clientX - stage.x(), y: e.evt.clientY - stage.y() };
        stage.container().style.cursor = 'grabbing';
        e.evt.preventDefault();
      }
    });
    stage.on('mousemove', (e) => {
      if (panningRef.current) {
        stage.position({ x: e.evt.clientX - panStartRef.current.x, y: e.evt.clientY - panStartRef.current.y });
        stage.batchDraw();
        return;
      }
      const { tool: t, drawing: dr } = stateRef.current;
      if (t === 'draw' && dr.active) {
        const cp = stageToCanvas(stage, e.evt.clientX, e.evt.clientY);
        renderPreviewLine(layersRef.current.draw, dr.vertices, cp, zoomRef.current);
      }
    });
    window.addEventListener('mouseup', () => {
      if (panningRef.current) {
        panningRef.current = false;
        const { tool: t } = stateRef.current;
        stage.container().style.cursor = t === 'draw' ? 'crosshair' : 'default';
      }
    });

    // Context menu — remove last draw vertex
    stage.on('contextmenu', (e) => {
      e.evt.preventDefault();
      const { tool: t, drawing: dr } = stateRef.current;
      if (t === 'draw' && dr.active) popDrawVertex();
    });

    return () => {
      window.removeEventListener('resize', onResize);
      stage.destroy();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Keyboard shortcuts ────────────────────────────────────────────────────
  const setTool = useStore(s => s.setTool);
  const toggleGridVisible = useStore(s => s.toggleGridVisible);

  useEffect(() => {
    const kd = (e) => {
      const tag = e.target.tagName;
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
      if (e.key === 'v' || e.key === 'V') vKeyRef.current = true;
      if (e.key === 'w' || e.key === 'W') setTool('draw');
      if (e.key === 'e' || e.key === 'E') setTool('erase');
      if (e.key === 's' || e.key === 'S') setTool('select');
      if (e.key === 'g' || e.key === 'G') toggleGridVisible();
      if (e.key === 'Escape') cancelDrawing();
    };
    const ku = (e) => { if (e.key === 'v' || e.key === 'V') vKeyRef.current = false; };
    document.addEventListener('keydown', kd);
    document.addEventListener('keyup', ku);
    return () => { document.removeEventListener('keydown', kd); document.removeEventListener('keyup', ku); };
  }, [setTool, toggleGridVisible, cancelDrawing]);

  // ── Click handler (tap) ────────────────────────────────────────────────────
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;

    const onClick = (e) => {
      if (panningRef.current) return;
      if (e.evt.button !== 0) return;
      const pos = stage.getPointerPosition();
      const cp  = { x: (pos.x - stage.x()) / zoomRef.current, y: (pos.y - stage.y()) / zoomRef.current };
      const st  = stateRef.current;

      // Calibration
      if (st.scaleCal.active) {
        const pts = addCalPt(cp);
        const { overlay } = layersRef.current;
        overlay.add(new Konva.Circle({ x: cp.x, y: cp.y, radius: 6 / zoomRef.current, fill: '#eab308', stroke: '#fff', strokeWidth: 1 / zoomRef.current, name: 'cal-marker' }));
        overlay.batchDraw();
        if (pts.length === 2) {
          // Auto-confirm is done externally via panel; just stop placement
        }
        return;
      }

      // Draw mode
      if (st.tool === 'draw') {
        addDrawVertex(cp);
        const verts = [...st.drawing.vertices, cp];
        if (verts.length >= 3) {
          const first = verts[0];
          const sd = Math.hypot((cp.x - first.x) * zoomRef.current, (cp.y - first.y) * zoomRef.current);
          if (sd < SNAP_RADIUS) {
            // close polygon
            const id = 'poly-' + Date.now();
            const area = polygonArea(verts) / (st.scale * st.scale);
            addPolygon({ id, vertices: verts, area });
            commitDraw();
            layersRef.current.draw.destroyChildren();
            layersRef.current.draw.batchDraw();
            return;
          }
        }
        return;
      }

      // Erase mode
      if (st.tool === 'erase') {
        const target = e.target;
        if (target && target.name() === 'polygon') {
          deletePolygon(target.id());
          return;
        }
        let closest = null, closestD = 15 / zoomRef.current;
        st.polygons.forEach(poly => {
          for (let i = 0; i < poly.vertices.length; i++) {
            const j = (i + 1) % poly.vertices.length;
            const d = ptSegDist(cp, poly.vertices[i], poly.vertices[j]);
            if (d < closestD) { closestD = d; closest = poly; }
          }
        });
        if (closest) deletePolygon(closest.id);
        return;
      }

      // Inspect mode (step 5 with radio map data)
      if (st.radioMap?.data) {
        const xm = cp.x / st.scale, ym = cp.y / st.scale;
        const entries = st.radioMap.data.filter(entry => {
          const dx = entry.x_m - xm, dy = entry.y_m - ym;
          return Math.hypot(dx, dy) < st.grid.spacing * 0.7;
        });
        if (entries.length && onInspect) onInspect(entries);
      }
    };

    stage.on('click', onClick);
    return () => stage.off('click', onClick);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addCalPt, addDrawVertex, addPolygon, deletePolygon, commitDraw, onInspect]);

  // ── Tool cursor ──────────────────────────────────────────────────────────
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    stage.container().style.cursor = tool === 'draw' ? 'crosshair' : tool === 'erase' ? 'cell' : 'default';
  }, [tool]);

  // ── Floor plan image ─────────────────────────────────────────────────────
  useEffect(() => {
    const { bg } = layersRef.current;
    if (!bg) return;
    bg.destroyChildren();
    if (!floorPlanImageData) { bg.batchDraw(); return; }
    const img = new Image();
    img.onload = () => {
      bg.add(new Konva.Image({ image: img, x: 0, y: 0, listening: false }));
      bg.batchDraw();
    };
    img.src = floorPlanImageData;
  }, [floorPlanImageData]);

  // ── Polygons ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const { poly } = layersRef.current;
    if (!poly) return;
    poly.destroyChildren();
    const z = zoomRef.current;
    polygons.forEach((p, i) => {
      const flat = p.vertices.flatMap(v => [v.x, v.y]);
      poly.add(new Konva.Line({
        points: flat, fill: 'rgba(124,58,237,0.08)',
        stroke: 'rgba(124,58,237,0.6)', strokeWidth: 1.5 / z,
        closed: true, name: 'polygon', id: p.id, hitStrokeWidth: 15,
      }));
      p.vertices.forEach(v => poly.add(new Konva.Circle({ x: v.x, y: v.y, radius: 4 / z, fill: 'rgba(124,58,237,0.8)', listening: false })));
      const c = polygonCentroid(p.vertices);
      const lbl = new Konva.Text({
        x: c.x, y: c.y - 8 / z,
        text: `#${i + 1}\n${p.area.toFixed(1)}m²`,
        fontSize: 11 / z, fill: 'rgba(124,58,237,0.8)',
        align: 'center', listening: false,
      });
      lbl.offsetX(lbl.width() / 2);
      poly.add(lbl);
    });
    poly.batchDraw();
  }, [polygons]);

  // ── Drawing preview layer ────────────────────────────────────────────────
  useEffect(() => {
    const { draw } = layersRef.current;
    if (!draw) return;
    if (!drawing.active || drawing.vertices.length === 0) { draw.destroyChildren(); draw.batchDraw(); return; }
    renderDrawing(draw, drawing.vertices, zoomRef.current);
  }, [drawing]);

  // ── Grid ─────────────────────────────────────────────────────────────────
  useEffect(() => {
    const { grid: gridL } = layersRef.current;
    if (!gridL) return;
    gridL.destroyChildren();
    gridL.visible(grid.visible);
    if (grid.points.length === 0) { gridL.batchDraw(); return; }
    // Use a single custom shape for performance
    gridL.add(new Konva.Shape({
      sceneFunc(ctx) {
        ctx.fillStyle = 'rgba(124,58,237,0.7)';
        const r = Math.max(1, 2 / zoomRef.current);
        grid.points.forEach(pt => {
          ctx.beginPath();
          ctx.arc(pt.x, pt.y, r, 0, Math.PI * 2);
          ctx.fill();
        });
      },
      listening: false,
    }));
    gridL.batchDraw();
  }, [grid.points, grid.visible]);

  // ── APs ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const { ap: apL } = layersRef.current;
    if (!apL) return;
    apL.destroyChildren();
    aps.list.forEach(ap => {
      const xpx = ap.x * scale, ypx = ap.y * scale;
      const g = new Konva.Group({ x: xpx, y: ypx, name: 'ap-group', id: 'apg-' + ap.bssid.replace(/:/g, '') });
      const z = zoomRef.current;
      [30, 22, 14].forEach((r, i) => g.add(new Konva.Circle({ radius: r / z, stroke: `rgba(249,115,22,${0.12 - i * 0.03})`, strokeWidth: 1 / z, fill: 'transparent', listening: false })));
      g.add(new Konva.Circle({ radius: 14 / z, stroke: 'rgba(249,115,22,0.4)', strokeWidth: 1.5 / z, fill: 'transparent', listening: false }));
      const selected = ap.bssid === aps.selected;
      g.add(new Konva.Circle({ radius: 8 / z, fill: selected ? '#a78bfa' : '#f97316', stroke: '#fff', strokeWidth: 1 / z }));
      const lbl = new Konva.Text({ text: ap.bssid.slice(-8), fontSize: 9 / z, fill: '#f97316', y: 11 / z, listening: false });
      lbl.offsetX(lbl.width() / 2);
      g.add(lbl);
      g.on('click', () => selectAP(ap.bssid));
      apL.add(g);
    });
    apL.batchDraw();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aps.list, aps.selected, scale]);

  // ── Heatmap ──────────────────────────────────────────────────────────────
  useEffect(() => {
    const { heat } = layersRef.current;
    if (!heat) return;
    heat.destroyChildren();
    if (!heatmap.visible) { heat.batchDraw(); return; }

    const bssid = heatmap.apBssid;
    const r = Math.max(2, grid.spacing * scale * 0.5);

    if (radioMap.data && bssid) {
      const entries = radioMap.data.filter(e => e.bssid === bssid);
      const rssiVals = entries.map(e => e.rssi_est);
      const maxR = Math.max(...rssiVals);
      heat.add(new Konva.Shape({
        sceneFunc(ctx) {
          entries.forEach(e => {
            const xpx = e.x_m * scale, ypx = e.y_m * scale;
            const rad = r / zoomRef.current;
            ctx.fillStyle = rssiToColor(e.rssi_est, maxR - 10);
            ctx.beginPath(); ctx.arc(xpx, ypx, rad, 0, Math.PI * 2); ctx.fill();
          });
        },
        listening: false,
      }));
    } else if (!radioMap.data && bssid) {
      const ap = aps.list.find(a => a.bssid === bssid);
      if (ap) {
        heat.add(new Konva.Shape({
          sceneFunc(ctx) {
            grid.points.forEach(pt => {
              const dx = (pt.x / scale) - ap.x, dy = (pt.y / scale) - ap.y;
              const dist = Math.hypot(dx, dy);
              const rssi = ap.rssi_ref - 10 * ap.path_loss_n * Math.log10(Math.max(dist, 0.1));
              const rad = r / zoomRef.current;
              ctx.fillStyle = rssiToColor(rssi, ap.rssi_ref);
              ctx.beginPath(); ctx.arc(pt.x, pt.y, rad, 0, Math.PI * 2); ctx.fill();
            });
          },
          listening: false,
        }));
      }
    }
    heat.batchDraw();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [heatmap, radioMap.data, grid.points, aps.list, scale]);

  // ── Expose fitToScreen via ref ────────────────────────────────────────────
  useImperativeHandle(ref, () => ({
    fitToScreen() {
      const stage = stageRef.current;
      const { bg } = layersRef.current;
      if (!stage || !bg) return;
      const img = bg.findOne('Image');
      if (!img) return;
      const container = containerRef.current;
      const w = container.offsetWidth, h = container.offsetHeight;
      const iw = img.width(), ih = img.height();
      const s = Math.min(w / iw, h / ih) * 0.9;
      zoomRef.current = s;
      stage.scale({ x: s, y: s });
      stage.position({ x: (w - iw * s) / 2, y: (h - ih * s) / 2 });
      stage.batchDraw();
      onZoomChange(Math.round(s * 100));
    },
    // Expose stage for calibration confirm
    getScale: () => zoomRef.current,
    getStage: () => stageRef.current,
    clearOverlay: () => {
      const { overlay } = layersRef.current;
      overlay.find('.cal-marker').forEach(n => n.destroy());
      overlay.batchDraw();
    },
    // For AP pulse animation on new APs
    pulseAP: (bssid) => {
      const { ap: apL } = layersRef.current;
      const gid = 'apg-' + bssid.replace(/:/g, '');
      const g = apL.findOne('#' + gid);
      if (!g) return;
      const z = zoomRef.current;
      const pulse = new Konva.Circle({ radius: 0, stroke: '#eab308', strokeWidth: 2 / z, fill: 'rgba(234,179,8,0.2)', opacity: 1 });
      g.add(pulse);
      const anim = new Konva.Animation((frame) => {
        const rr = (frame.time / 2000) * 40 / z;
        const op = 1 - frame.time / 2000;
        pulse.radius(rr); pulse.opacity(Math.max(0, op));
        if (frame.time > 2000) { anim.stop(); pulse.destroy(); apL.batchDraw(); }
      }, apL);
      anim.start();
    },
  }), [onZoomChange]);

  return (
    <div ref={containerRef} id="canvas-container" style={{ width: '100%', height: '100%' }} />
  );
});

// ── Drawing helpers ────────────────────────────────────────────────────────

function stageToCanvas(stage, cx, cy) {
  const rect = stage.container().getBoundingClientRect();
  const px = cx - rect.left, py = cy - rect.top;
  return { x: (px - stage.x()) / stage.scaleX(), y: (py - stage.y()) / stage.scaleY() };
}

function renderDrawing(layer, verts, zoom) {
  layer.destroyChildren();
  if (verts.length === 0) { layer.batchDraw(); return; }
  if (verts.length > 1) {
    layer.add(new Konva.Line({ points: verts.flatMap(v => [v.x, v.y]), stroke: 'rgba(124,58,237,0.7)', strokeWidth: 1.5 / zoom }));
  }
  verts.forEach(v => layer.add(new Konva.Circle({ x: v.x, y: v.y, radius: 4 / zoom, fill: '#7c3aed', listening: false })));
  if (verts.length >= 3) {
    layer.add(new Konva.Circle({ x: verts[0].x, y: verts[0].y, radius: SNAP_RADIUS / zoom, stroke: 'rgba(34,197,94,0.5)', strokeWidth: 1.5 / zoom, fill: 'transparent', name: 'snap-ring' }));
  }
  layer.batchDraw();
}

function renderPreviewLine(layer, verts, cp, zoom) {
  layer.find('.preview-line').forEach(n => n.destroy());
  layer.find('.snap-ring').forEach(n => n.destroy());
  layer.find('.snap-label').forEach(n => n.destroy());
  if (verts.length === 0) { layer.batchDraw(); return; }
  const last = verts[verts.length - 1];
  layer.add(new Konva.Line({ points: [last.x, last.y, cp.x, cp.y], stroke: 'rgba(124,58,237,0.4)', strokeWidth: 1.2 / zoom, dash: [4 / zoom, 4 / zoom], name: 'preview-line' }));
  if (verts.length >= 3) {
    const first = verts[0];
    const sd = Math.hypot((cp.x - first.x) * zoom, (cp.y - first.y) * zoom);
    const inSnap = sd < SNAP_RADIUS;
    layer.add(new Konva.Circle({ x: first.x, y: first.y, radius: SNAP_RADIUS / zoom, stroke: inSnap ? '#22c55e' : 'rgba(34,197,94,0.5)', strokeWidth: (inSnap ? 2.5 : 1.5) / zoom, fill: inSnap ? 'rgba(34,197,94,0.1)' : 'transparent', name: 'snap-ring' }));
    if (inSnap) {
      layer.add(new Konva.Text({ x: first.x - 30 / zoom, y: first.y - 20 / zoom, text: 'close shape ✓', fontSize: 10 / zoom, fill: '#22c55e', name: 'snap-label' }));
    }
  }
  layer.batchDraw();
}

export default MapCanvas;
