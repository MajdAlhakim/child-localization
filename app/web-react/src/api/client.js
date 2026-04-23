const API_KEY  = '580a92b1cad8ad81b7ae90c23fb222443d9c87aac4ce4a7728a3f9e99e3e4990';
const API_BASE = '';

function getActiveFpId() {
  // Read from localStorage to avoid circular store imports
  return localStorage.getItem('trakn_active_fp') || null;
}

export async function apiFetch(method, path, body, isFormData) {
  const headers = { 'X-API-Key': API_KEY };
  const fpId = getActiveFpId();
  if (fpId) headers['X-Floor-Plan-Id'] = fpId;
  if (!isFormData && body) headers['Content-Type'] = 'application/json';

  const res = await fetch(API_BASE + path, {
    method,
    headers,
    body: isFormData ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = '';
    try { detail = await res.text(); } catch (_) {}
    throw new Error(`Server ${res.status}${detail ? ': ' + detail : ''}`);
  }
  return res;
}

export async function apiJSON(method, path, body) {
  const res = await apiFetch(method, path, body);
  return res.json();
}

// Venue endpoints
export const venueApi = {
  list:   ()         => apiJSON('GET',    '/api/v1/venues'),
  create: (name)     => apiJSON('POST',   '/api/v1/venues', { name, description: '' }),
  get:    (id)       => apiJSON('GET',    `/api/v1/venues/${id}`),
  delete: (id)       => apiJSON('DELETE', `/api/v1/venues/${id}`),
};

// Floor plan endpoints
export const floorPlanApi = {
  create:     (venueId, formData)        => apiFetch('POST', `/api/v1/venues/${venueId}/floor-plans`, formData, true),
  createMeta: (venueId, name, floorNum) => {
    const fd = new FormData();
    fd.append('name', name);
    fd.append('floor_number', String(floorNum));
    return apiFetch('POST', `/api/v1/venues/${venueId}/floor-plans`, fd, true);
  },
  getImage: (fpId)           => apiFetch('GET',  `/api/v1/floor-plans/${fpId}/image`),
  putImage: (fpId, formData) => apiFetch('POST', `/api/v1/floor-plans/${fpId}/image`, formData, true),
  getGrid:  (fpId)           => apiJSON('GET',   `/api/v1/floor-plans/${fpId}/grid`),
  getAPs:   (fpId)           => apiJSON('GET',   `/api/v1/floor-plans/${fpId}/aps`),
  delete:   (fpId)           => apiJSON('DELETE', `/api/v1/floor-plans/${fpId}`),
};

// Legacy venue endpoints (use X-Floor-Plan-Id header routing)
export const legacyApi = {
  getAPs:           ()       => apiJSON('GET',  '/api/v1/venue/aps'),
  saveGrid:         (body)   => apiJSON('POST', '/api/v1/venue/grid-points', body),
  computeRadioMap:  ()       => apiJSON('POST', '/api/v1/venue/radio-map/compute'),
  radioMapStatus:   (taskId) => apiJSON('GET',  `/api/v1/venue/radio-map/status/${taskId}`),
  getRadioMap:      ()       => apiJSON('GET',  '/api/v1/venue/radio-map'),
};

export async function checkHealth() {
  const res = await fetch('/health');
  if (!res.ok) throw new Error('health check failed');
}
