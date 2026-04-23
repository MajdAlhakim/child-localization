import { useState } from 'react';
import { Plus, Trash2, ChevronRight, Building2, Layers } from 'lucide-react';

export function VenuesDashboard({ venues, onOpen, onDelete, onCreateVenue }) {
  const [showForm, setShowForm]   = useState(false);
  const [newName, setNewName]     = useState('');
  const [creating, setCreating]   = useState(false);

  async function handleCreate() {
    const n = newName.trim();
    if (!n) return;
    setCreating(true);
    try {
      await onCreateVenue(n);
      setNewName('');
      setShowForm(false);
    } catch (_) {
      // error toasted by caller
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div style={{ maxWidth: 860, margin: '0 auto' }}>

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>Venues</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Select a venue to manage its floor plans
            </p>
          </div>
          <button
            className="btn-primary flex items-center gap-1.5"
            style={{ width: 'auto', padding: '7px 16px' }}
            onClick={() => setShowForm(v => !v)}
          >
            <Plus size={13} /> New Venue
          </button>
        </div>

        {/* Inline create form */}
        {showForm && (
          <div
            className="mb-5 p-4 rounded-lg animate-fade-in-up"
            style={{ background: 'var(--bg2)', border: '1px solid var(--primary)', boxShadow: '0 0 0 1px var(--primary-dim)' }}
          >
            <div className="text-xs font-semibold mb-2" style={{ color: 'var(--primary-b)' }}>New Venue</div>
            <div className="flex gap-2">
              <input
                autoFocus
                type="text"
                className="panel-input flex-1"
                placeholder="e.g. Building H07"
                value={newName}
                onChange={e => setNewName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleCreate(); if (e.key === 'Escape') setShowForm(false); }}
              />
              <button
                className="btn-primary"
                style={{ width: 'auto', padding: '5px 16px', marginTop: 0 }}
                disabled={!newName.trim() || creating}
                onClick={handleCreate}
              >
                {creating ? <span className="spinner inline-block" /> : 'Create'}
              </button>
              <button
                className="btn-secondary"
                style={{ width: 'auto', padding: '5px 12px', marginTop: 0 }}
                onClick={() => { setShowForm(false); setNewName(''); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Empty state */}
        {venues.length === 0 ? (
          <div className="text-center py-20" style={{ color: 'var(--text-dim)' }}>
            <Building2 size={42} className="mx-auto mb-3 opacity-25" />
            <div className="text-sm font-medium">No venues yet</div>
            <div className="text-xs mt-1">Create a venue to start mapping</div>
          </div>
        ) : (
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}
          >
            {venues.map(v => (
              <VenueCard
                key={v.id}
                venue={v}
                onOpen={() => onOpen(v.id)}
                onDelete={() => onDelete(v.id, v.name)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function VenueCard({ venue, onOpen, onDelete }) {
  const fps      = venue.floor_plans || [];
  const totalAps = fps.reduce((s, fp) => s + (fp.ap_count || 0), 0);

  return (
    <div
      className="p-4 rounded-lg cursor-pointer transition-all duration-150 group"
      style={{ background: 'var(--bg2)', border: '1px solid var(--border)' }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.boxShadow = '0 0 0 1px var(--primary-dim)'; }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = ''; }}
      onClick={onOpen}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded flex items-center justify-center flex-shrink-0"
            style={{ background: 'var(--primary-dim)', border: '1px solid var(--primary)' }}
          >
            <Building2 size={14} style={{ color: 'var(--primary-b)' }} />
          </div>
          <div className="font-semibold text-sm" style={{ color: 'var(--text)' }}>{venue.name}</div>
        </div>
        <button
          className="icon-btn danger opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ width: 22, height: 22 }}
          onClick={e => { e.stopPropagation(); onDelete(); }}
          title="Delete venue"
        >
          <Trash2 size={11} />
        </button>
      </div>

      <div className="flex items-center gap-3 text-xs mb-3" style={{ color: 'var(--text-muted)' }}>
        <span className="flex items-center gap-1">
          <Layers size={10} /> {fps.length} floor{fps.length !== 1 ? 's' : ''}
        </span>
        <span>·</span>
        <span>{totalAps} AP{totalAps !== 1 ? 's' : ''}</span>
      </div>

      <div className="flex items-center justify-end">
        <span className="text-xs font-medium flex items-center gap-0.5" style={{ color: 'var(--primary-b)' }}>
          Open <ChevronRight size={12} />
        </span>
      </div>
    </div>
  );
}
