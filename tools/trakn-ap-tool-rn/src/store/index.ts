import { create } from 'zustand';
import type { ApEntry, GridResponse } from '../api/client';

export interface WifiNetwork {
  BSSID: string;
  SSID:  string;
  level: number;       // RSSI dBm
  frequency: number;
}

interface ApToolStore {
  // Settings
  baseUrl: string;
  apiKey:  string;
  setSettings: (url: string, key: string) => void;

  // Scan
  networks:    WifiNetwork[];
  bestAp:      WifiNetwork | null;
  isScanning:  boolean;
  lastScanTs:  string;
  setNetworks: (nets: WifiNetwork[]) => void;
  setScanning: (v: boolean) => void;

  // Server APs (placed)
  serverAps:    ApEntry[];
  setServerAps: (aps: ApEntry[]) => void;

  // Grid
  grid:    GridResponse | null;
  scalePxPerM: number;
  setGrid: (g: GridResponse) => void;

  // Backend health
  isOnline:  boolean;
  setOnline: (v: boolean) => void;

  // Pending placement (from map tap)
  pendingPlacement: { xMeters: number; yMeters: number } | null;
  setPendingPlacement: (p: { xMeters: number; yMeters: number } | null) => void;
}

export const useStore = create<ApToolStore>((set) => ({
  baseUrl: 'https://trakn.duckdns.org',
  apiKey:  '580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990',
  setSettings: (baseUrl, apiKey) => set({ baseUrl, apiKey }),

  networks:    [],
  bestAp:      null,
  isScanning:  false,
  lastScanTs:  '',
  setNetworks: (networks) => set({
    networks,
    bestAp: networks.length > 0 ? networks.reduce((a, b) => a.level > b.level ? a : b) : null,
  }),
  setScanning: (isScanning) => set({ isScanning }),

  serverAps:    [],
  setServerAps: (serverAps) => set({ serverAps }),

  grid:       null,
  scalePxPerM: 10,
  setGrid:    (grid) => set({ grid, scalePxPerM: grid.scale_px_per_m }),

  isOnline:  false,
  setOnline: (isOnline) => set({ isOnline }),

  pendingPlacement: null,
  setPendingPlacement: (pendingPlacement) => set({ pendingPlacement }),
}));
