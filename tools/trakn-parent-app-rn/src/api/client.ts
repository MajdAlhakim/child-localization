import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const DEFAULT_BASE = 'https://trakn.duckdns.org';
const DEFAULT_KEY  = '580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990';

async function getSettings() {
  const [base, key] = await Promise.all([
    AsyncStorage.getItem('baseUrl'),
    AsyncStorage.getItem('apiKey'),
  ]);
  return {
    baseUrl: base || DEFAULT_BASE,
    apiKey:  key  || DEFAULT_KEY,
  };
}

export async function apiGet<T>(path: string): Promise<T> {
  const { baseUrl, apiKey } = await getSettings();
  const res = await axios.get<T>(`${baseUrl}${path}`, {
    headers: { 'X-API-Key': apiKey },
    timeout: 10000,
  });
  return res.data;
}

export async function apiPost<T>(path: string, data?: unknown): Promise<T> {
  const { baseUrl, apiKey } = await getSettings();
  const res = await axios.post<T>(`${baseUrl}${path}`, data, {
    headers: { 'X-API-Key': apiKey, 'Content-Type': 'application/json' },
    timeout: 10000,
  });
  return res.data;
}

export async function getFloorPlanUrl(): Promise<string> {
  const { baseUrl } = await getSettings();
  return `${baseUrl}/api/v1/venue/floor-plan`;
}

export async function checkHealth(): Promise<boolean> {
  try {
    const { baseUrl } = await getSettings();
    await axios.get(`${baseUrl}/health`, { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

// Localization endpoint
export const locApi = {
  locate: (measurements: RssiMeasurement[]) =>
    apiPost<LocateResponse>('/api/v1/locate', { measurements }),
};

// AP + grid (read-only from parent app)
export const apApi = {
  list: () => apiGet<{ access_points: ApEntry[] }>('/api/v1/venue/aps'),
};

export const gridApi = {
  get: () => apiGet<GridResponse>('/api/v1/venue/grid-points'),
};

// Types
export interface ApEntry {
  bssid: string;
  ssid:  string;
  x:     number;
  y:     number;
  rssi_ref:     number;
  path_loss_n:  number;
  ceiling_height: number;
  group_id: string | null;
}

export interface RssiMeasurement {
  bssid: string;
  rssi:  number;
}

export interface LocateResponse {
  x:     number;
  y:     number;
  error: number;       // estimated error in meters
  method: string;
}

export interface GridResponse {
  scale_px_per_m: number;
  grid_spacing_m: number;
  points: { x: number; y: number }[];
}
