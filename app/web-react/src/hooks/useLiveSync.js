import { useEffect, useRef, useCallback } from 'react';
import { legacyApi } from '../api/client';
import { useStore } from '../store';
import { useToast } from './useToast';

export function useLiveSync(enabled) {
  const toast    = useToast();
  const updateAPs = useStore(s => s.updateAPs);
  const setOffline = useStore(s => s.setOffline);
  const intervalRef = useRef(null);

  const sync = useCallback(async () => {
    try {
      const data = await legacyApi.getAPs();
      const newOnes = updateAPs(data.access_points || []);
      setOffline(false);
      newOnes.forEach(b => toast('New AP from Android tool: ' + b, 'info', 3000));
      return { ok: true, ts: new Date().toLocaleTimeString() };
    } catch {
      setOffline(true);
      return { ok: false };
    }
  }, [updateAPs, setOffline, toast]);

  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      return;
    }
    sync(); // immediate
    intervalRef.current = setInterval(sync, 3000);
    return () => { clearInterval(intervalRef.current); intervalRef.current = null; };
  }, [enabled, sync]);

  return { sync };
}
