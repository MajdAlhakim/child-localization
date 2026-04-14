import { createContext, useContext, useCallback, useRef, useState } from 'react';

const ToastCtx = createContext(null);

let toastId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback((id) => {
    setToasts(t => t.map(x => x.id === id ? { ...x, leaving: true } : x));
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 300);
  }, []);

  const toast = useCallback((msg, type = 'info', duration = 4000) => {
    const id = ++toastId;
    setToasts(t => [...t, { id, msg, type }]);
    setTimeout(() => dismiss(id), duration);
  }, [dismiss]);

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="fixed bottom-5 right-5 flex flex-col gap-2 z-[9999] pointer-events-none">
        {toasts.map(t => (
          <Toast key={t.id} {...t} onDismiss={() => dismiss(t.id)} />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function Toast({ msg, type, leaving, onDismiss }) {
  const base = 'pointer-events-auto flex items-start gap-2 px-3 py-2.5 rounded-lg text-xs font-medium max-w-xs leading-relaxed border backdrop-blur-sm shadow-lg';
  const styles = {
    error:   'bg-[rgba(26,10,10,0.95)] border-red-500/40 text-red-300',
    success: 'bg-[rgba(10,26,15,0.95)] border-green-500/40 text-green-300',
    info:    'bg-[rgba(11,16,25,0.95)] border-[#1e2e42] text-[#526a85]',
  };
  const icons = { error: '⚠', success: '✓', info: '●' };
  const iconColors = { error: 'text-red-500', success: 'text-green-500', info: 'text-[#7c3aed]' };

  return (
    <div
      className={`${base} ${styles[type] || styles.info} ${leaving ? 'opacity-0 translate-x-4 transition-all duration-300' : 'animate-toast-in'}`}
      onClick={onDismiss}
    >
      <span className={`flex-shrink-0 ${iconColors[type] || iconColors.info} text-sm leading-none mt-0.5`}>
        {icons[type] || icons.info}
      </span>
      {msg}
    </div>
  );
}

export function useToast() {
  return useContext(ToastCtx);
}
