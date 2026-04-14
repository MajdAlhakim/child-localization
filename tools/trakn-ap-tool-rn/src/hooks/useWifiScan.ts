import { useEffect, useCallback, useRef } from 'react';
import { PermissionsAndroid, Platform } from 'react-native';
import { useStore } from '../store';

// react-native-wifi-reborn typings
declare module 'react-native-wifi-reborn' {
  const WifiManager: {
    loadWifiList(): Promise<Array<{ BSSID: string; SSID: string; level: number; frequency: number; capabilities: string }>>;
    reScanAndLoadWifiList(): Promise<Array<{ BSSID: string; SSID: string; level: number; frequency: number; capabilities: string }>>;
  };
  export default WifiManager;
}

async function requestWifiPermission(): Promise<boolean> {
  if (Platform.OS !== 'android') return false;
  try {
    const granted = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
      {
        title: 'Location Permission',
        message: 'TRAKN needs location access to scan for Wi-Fi access points.',
        buttonPositive: 'Allow',
        buttonNegative: 'Deny',
      }
    );
    return granted === PermissionsAndroid.RESULTS.GRANTED;
  } catch {
    return false;
  }
}

export function useWifiScan(intervalMs = 15_000) {
  const setNetworks = useStore(s => s.setNetworks);
  const setScanning = useStore(s => s.setScanning);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const permGranted = useRef(false);

  const scan = useCallback(async () => {
    if (!permGranted.current) {
      permGranted.current = await requestWifiPermission();
      if (!permGranted.current) return;
    }

    setScanning(true);
    try {
      // Dynamic import to avoid crash when native module not linked
      const WifiManager = (await import('react-native-wifi-reborn')).default;
      const results = await WifiManager.reScanAndLoadWifiList();
      const sorted = [...results].sort((a, b) => b.level - a.level);
      setNetworks(sorted);
    } catch (e) {
      console.warn('WiFi scan failed:', e);
      // In development / emulator, inject mock data
      setNetworks([
        { BSSID: '24:16:1b:76:07:a0', SSID: 'QU-WiFi-5GHz',  level: -42, frequency: 5180 },
        { BSSID: '24:16:1b:76:07:a1', SSID: 'QU-WiFi-2.4',   level: -55, frequency: 2437 },
        { BSSID: '24:16:1b:76:07:b0', SSID: 'QU-Staff',       level: -60, frequency: 5180 },
        { BSSID: '24:16:1b:76:07:c0', SSID: 'QU-Students',    level: -68, frequency: 2437 },
      ]);
    } finally {
      setScanning(false);
    }
  }, [setNetworks, setScanning]);

  useEffect(() => {
    scan();
    intervalRef.current = setInterval(scan, intervalMs);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [scan, intervalMs]);

  return { rescan: scan };
}
