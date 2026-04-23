import { useState } from 'react';
import { Plus, Trash2, ChevronRight, ArrowLeft, MapPin, Layers } from 'lucide-react';

export function FloorPlansDashboard({ venue, onBack, onOpen, onAdd, onDelete }) {
  const [showForm, setShowForm]     = useState(false);
  const [newFloorNum, setNewFloorNum] = useState('');
  const [newFloorName, setNewFloorName] = useState('');
  const [adding, setAdding]         = useState(false);

  const floorPlans = [...(venue?.floor_plans || [])].sort((a, b) => a.floor_number - b.floor_number);

  async function handleAdd() {
    const num = parseInt(newFloorNum, 10);
    if (!num && num !== 0) return;
    const name = newFloorName.trim() || `Floor ${num}`;
    setAdding(true);
    try {
      await onAdd(num, name);
      setNewFloorNum('');
      setNewFloorName('');
      setShowForm(false);
    } catch (_) {
      // error toasted by caller
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div style={{ maxWidth: 860, margin: '0 auto' }}>

        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <button className="icon-btn" onClick={onBack} title="Back to venues">
            <ArrowLeft size={13} />
          </button>
          <div className="flex-1">
            <h1 className="text-xl font-bold" style={{ color: 'var(--text)' }}>{venue?.name}</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Select a floor plan to start mapping, or add a new floor below
            </p>
          </div>
          <button
            className="btn-primary flex items-center gap-1.5"
            style={{ width: 'auto', padding: '7px 16px' }}
            onClick={() => setShowForm(v => !v)}
          >
            <Plus size={13} /> Add Floor
          </button>
        </div>

        {/* Inline add form */}
        {showForm && (
          <div
            className="mb-5 p-4 rounded-lg animate-fade-in-up"
            style={{ background: 'var(--bg2)', border: '1px solid var(--primary)', boxShadow: '0 0 0 1px var(--primary-dim)' }}
          >
            <div className="text-xs font-semibold mb-2" style={{ color: 'var(--primary-b)' }}>New Floor Plan</div>
            <div className="flex gap-2">
              <input
                autoFocus
                type="number"
                min="0"
                className="panel-input"
                placeholder="Floor number (e.g. 1)"
                style={{ width: 170 }}
                value={newFloorNum}
                onChange={e => setNewFloorNum(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') setShowForm(false); }}
              />
              <input
                type="text"
                className="panel-input flex-1"
                placeholder="Name (e.g. Ground Floor)"
                value={newFloorName}
                onChange={e => setNewFloorName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleAdd(); if (e.key === 'Escape') setShowForm(false); }}
              />
              <button
                className="btn-primary"
                style={{ width: 'auto', padding: '5px 16px', marginTop: 0 }}
                disabled={newFloorNum === '' || adding}
                onClick={handleAdd}
              >
                {adding ? <span className="spinner inline-block" /> : 'Create'}
              </button>
              <button
                className="btn-secondary"
                style={{ width: 'auto', padding: '5px 12px', marginTop: 0 }}
                onClick={() => { setShowForm(false); setNewFloorNum(''); setNewFloorName(''); }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Empty state */}
        {floorPlans.length === 0 ? (
          <div className="text-center py-20" style={{ color: 'var(--text-dim)' }}>
            <Layers size={42} className="mx-auto mb-3 opacity-25" />
            <div className="text-sm font-medium">No floor plans yet</div>
            <div className="text-xs mt-1">Click "Add Floor" to create the first floor</div>
          </div>
        ) : (
          <div
            className="grid gap-3"
            style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}
          >
            {floorPlans.map(fp => (
              <FloorPlanCard
                key={fp.id}
                fp={fp}
                onOpen={() => onOpen(fp.id)}
                onDelete={() => onDelete(fp.id, fp.name)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function FloorPlanCard({ fp, onOpen, onDelete }) {
  const [imgError, setImgError] = useState(false);

  return (
    <div
      className="rounded-lg overflow-hidden cursor-pointer transition-all duration-150 group"
      style={{ background: 'var(--bg2)', border: '1px solid var(--border)' }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.boxShadow = '0 0 0 1px var(--primary-dim)'; }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.boxShadow = ''; }}
      onClick={onOpen}
    >
      {/* Thumbnail */}
      <div className="relative h-32 overflow-hidden" style={{ background: 'var(--bg3)' }}>
        {fp.has_image && !imgError ? (
          <img
            src={`/api/v1/floor-plans/${fp.id}/image`}
            alt={fp.name}
            className="w-full h-full object-contain"
            style={{ opacity: 0.75 }}
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center" style={{ color: 'var(--text-dim)' }}>
            <MapPin size={26} className="opacity-25" />
          </div>
        )}

        {/* Floor number badge */}
        <div
          className="absolute top-2 left-2 text-xs font-bold font-mono px-2 py-0.5 rounded"
          style={{ background: 'var(--primary)', color: '#fff' }}
        >
          F{fp.floor_number}
        </div>

        {/* Delete button — appears on hover */}
        <button
          className="icon-btn danger absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
          style={{ width: 22, height: 22 }}
          onClick={e => { e.stopPropagation(); onDelete(); }}
          title="Delete floor plan"
        >
          <Trash2 size={11} />
        </button>
      </div>

      <div className="p-3">
        <div className="font-semibold text-sm mb-1.5" style={{ color: 'var(--text)' }}>{fp.name}</div>
        <div className="flex items-center justify-between">
          <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
            {fp.ap_count || 0} AP{fp.ap_count !== 1 ? 's' : ''}
            {' · '}
            {fp.has_image ? 'image ready' : 'no image yet'}
          </span>
          <span className="text-xs font-medium flex items-center gap-0.5" style={{ color: 'var(--primary-b)' }}>
            Map <ChevronRight size={11} />
          </span>
        </div>
      </div>
    </div>
  );
}
