/**
 * useLocalization — client-side indoor positioning
 *
 * Algorithm:
 *   1. For each scanned BSSID that matches a placed AP, estimate distance via
 *      log-distance path loss:  dist = 10^((rssi_ref - rssi) / (10 * n))
 *   2. Weighted-least-squares (WLS) multilateration:
 *      weight_i = 1 / (dist_i + 0.5)   (penalise far APs)
 *   3. Exponential moving average (EMA) for both RSSI (α=0.25) and position (α=0.30)
 *      to smooth out measurement noise.
 *   4. Error estimate = weighted RMSE of distances.
 *
 * Falls back to server-side /api/v1/locate when enabled via useServerLocalize.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useStore } from '../store';
import type { WifiNetwork } from '../store';
import type { ApEntry, LocateResponse } from '../api/client';

const EMA_RSSI = 0.25;
const EMA_POS  = 0.30;

function logDistanceDist(rssi: number, rssiRef: number, n: number): number {
  return Math.pow(10, (rssiRef - rssi) / (10 * n));
}

/** Simple WLS centroid multilateration — works well for 3+ APs */
function multilaterate(
  anchors: Array<{ x: number; y: number; dist: number }>,
): { x: number; y: number; error: number } | null {
  if (anchors.length === 0) return null;

  // If only 1 AP, return its position (no lat)
  if (anchors.length === 1) {
    return { x: anchors[0].x, y: anchors[0].y, error: anchors[0].dist };
  }

  const weights = anchors.map(a => 1 / (a.dist + 0.5));
  const totalW  = weights.reduce((s, w) => s + w, 0);
  const x = weights.reduce((s, w, i) => s + w * anchors[i].x, 0) / totalW;
  const y = weights.reduce((s, w, i) => s + w * anchors[i].y, 0) / totalW;

  // Weighted RMSE as error estimate
  const rmse = Math.sqrt(
    anchors.reduce((s, a, i) => {
      const dx   = x - a.x;
      const dy   = y - a.y;
      const dRes = Math.sqrt(dx * dx + dy * dy) - a.dist;
      return s + weights[i] * dRes * dRes;
    }, 0) / totalW,
  );

  return { x, y, error: rmse };
}

export function useLocalization(active: boolean) {
  const networks    = useStore(s => s.networks);
  const serverAps   = useStore(s => s.serverAps);
  const setPosition = useStore(s => s.setPosition);
  const setLocating = useStore(s => s.setLocating);

  // Smoothed RSSI map: bssid -> smoothed level
  const smoothRssi = useRef<Map<string, number>>(new Map());
  // Smoothed position
  const smoothPos  = useRef<{ x: number; y: number } | null>(null);

  const compute = useCallback(() => {
    if (!active || networks.length === 0 || serverAps.length === 0) return;

    setLocating(true);

    // Step 1: EMA-smooth RSSI for each seen AP
    const apMap = new Map(serverAps.map(a => [a.bssid.toLowerCase(), a]));
    const anchors: Array<{ x: number; y: number; dist: number }> = [];

    for (const net of networks) {
      const key = net.BSSID.toLowerCase();
      const ap  = apMap.get(key);
      if (!ap) continue;

      // EMA on RSSI
      const prev = smoothRssi.current.get(key) ?? net.level;
      const smoothed = prev + EMA_RSSI * (net.level - prev);
      smoothRssi.current.set(key, smoothed);

      const dist = logDistanceDist(smoothed, ap.rssi_ref, ap.path_loss_n);
      anchors.push({ x: ap.x, y: ap.y, dist });
    }

    if (anchors.length === 0) {
      setLocating(false);
      return;
    }

    const raw = multilaterate(anchors);
    if (!raw) { setLocating(false); return; }

    // Step 3: EMA on position
    if (!smoothPos.current) {
      smoothPos.current = { x: raw.x, y: raw.y };
    } else {
      smoothPos.current = {
        x: smoothPos.current.x + EMA_POS * (raw.x - smoothPos.current.x),
        y: smoothPos.current.y + EMA_POS * (raw.y - smoothPos.current.y),
      };
    }

    setPosition({
      x: smoothPos.current.x,
      y: smoothPos.current.y,
      error: raw.error,
      method: 'client-wls',
    });
    setLocating(false);
  }, [active, networks, serverAps, setPosition, setLocating]);

  // Run whenever networks update
  useEffect(() => {
    compute();
  }, [compute]);

  // Reset smooth state when tracking stops
  useEffect(() => {
    if (!active) {
      smoothRssi.current.clear();
      smoothPos.current = null;
    }
  }, [active]);
}
