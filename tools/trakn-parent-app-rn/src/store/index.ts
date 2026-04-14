import { create } from 'zustand';
import type { ApEntry, GridResponse, LocateResponse } from '../api/client';

export interface WifiNetwork {
  BSSID: string;
  SSID:  string;
  level: number;
  frequency: number;
}

interface ParentStore {
  // Settings
  baseUrl: string;
  apiKey:  string;
  setSettings: (url: string, key: string) => void;

  // Connectivity
  isOnline: boolean;
  setOnline: (v: boolean) => void;

  // Scan
  networks:    WifiNetwork[];
  isScanning:  boolean;
  setNetworks: (nets: WifiNetwork[]) => void;
  setScanning: (v: boolean) => void;

  // Server data
  serverAps:    ApEntry[];
  grid:         GridResponse | null;
  scalePxPerM:  number;
  setServerAps: (aps: ApEntry[]) => void;
  setGrid:      (g: GridResponse) => void;

  // Localization
  position:      LocateResponse | null;
  isLocating:    boolean;
  locateError:   string | null;
  setPosition:   (p: LocateResponse | null) => void;
  setLocating:   (v: boolean) => void;
  setLocateError:(e: string | null) => void;

  // UI
  trackingActive: boolean;
  setTracking:   (v: boolean) => void;
}

export const useStore = create<ParentStore>((set) => ({
  baseUrl: 'https://trakn.duckdns.org',
  apiKey:  '580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990',
  setSettings: (baseUrl, apiKey) => set({ baseUrl, apiKey }),

  isOnline:  false,
  setOnline: (isOnline) => set({ isOnline }),

  networks:    [],
  isScanning:  false,
  setNetworks: (networks) => set({ networks }),
  setScanning: (isScanning) => set({ isScanning }),

  serverAps:    [],
  grid:         null,
  scalePxPerM:  10,
  setServerAps: (serverAps) => set({ serverAps }),
  setGrid:      (grid) => set({ grid, scalePxPerM: grid.scale_px_per_m }),

  position:      null,
  isLocating:    false,
  locateError:   null,
  setPosition:   (position) => set({ position }),
  setLocating:   (isLocating) => set({ isLocating }),
  setLocateError: (locateError) => set({ locateError }),

  trackingActive: false,
  setTracking:   (trackingActive) => set({ trackingActive }),
}));
