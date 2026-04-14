import { useState, useCallback, useRef } from 'react';

export interface ToastMsg { id: number; msg: string; type: 'success' | 'error' | 'info'; }

let _id = 0;

export function useToastState() {
  const [toasts, setToasts] = useState<ToastMsg[]>([]);

  const toast = useCallback((msg: string, type: ToastMsg['type'] = 'info', ms = 3000) => {
    const id = ++_id;
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), ms);
  }, []);

  return { toasts, toast };
}
