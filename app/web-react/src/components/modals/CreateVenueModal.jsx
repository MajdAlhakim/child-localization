import { useRef, useState } from 'react';
import { X } from 'lucide-react';

export function CreateVenueModal({ open, onClose, onCreate }) {
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const inputRef = useRef(null);

  if (!open) return null;

  async function handleCreate() {
    const n = name.trim();
    if (!n) return;
    setLoading(true);
    try {
      await onCreate(n);
      setName('');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="animate-scale-in w-80 p-6 rounded-lg shadow-2xl"
        style={{ background: 'var(--bg2)', border: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="text-sm font-bold" style={{ color: 'var(--text)' }}>New Venue</div>
          <button
            onClick={onClose}
            className="icon-btn" style={{ width: 22, height: 22 }}
          >
            <X size={12} />
          </button>
        </div>

        <input
          ref={inputRef}
          autoFocus
          type="text"
          className="panel-input mb-4"
          placeholder="Venue name (e.g. Building A, Floor 2)"
          value={name}
          onChange={e => setName(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter') handleCreate();
            if (e.key === 'Escape') onClose();
          }}
        />

        <div className="flex gap-2 justify-end">
          <button
            className="btn-secondary"
            style={{ width: 'auto', padding: '6px 16px', marginTop: 0 }}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="btn-primary"
            style={{ width: 'auto', padding: '6px 16px' }}
            disabled={!name.trim() || loading}
            onClick={handleCreate}
          >
            {loading ? <><span className="spinner inline-block mr-1" /> Creating…</> : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}
