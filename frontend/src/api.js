const J = (r) => r.json()
const post = (url, body) =>
  fetch(url, {
    method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).then(J)

export const api = {
  watches: () => fetch('/api/watches').then(J),
  createWatch: (b) => post('/api/watches', b),
  updateWatch: (id, b) =>
    fetch(`/api/watches/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    }).then(J),
  deleteWatch: (id) => fetch(`/api/watches/${id}`, { method: 'DELETE' }).then(J),

  config: () => fetch('/api/config').then(J),
  saveConfig: (b) =>
    fetch('/api/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(b),
    }).then(J),

  recommendations: (status = 'new') => fetch(`/api/recommendations?status=${status}`).then(J),
  approve: (id) => post(`/api/recommendations/${id}/approve`),
  reject: (id) => post(`/api/recommendations/${id}/reject`),
  mute: (id, days) => post(`/api/recommendations/${id}/mute?days=${days}`),

  favorites: () => fetch('/api/favorites').then(J),
  stats: () => fetch('/api/stats').then(J),
  events: () => fetch('/api/events').then(J),
  testEmail: () => post('/api/test-email'),
  loginStart: () => post('/api/login/start'),
  loginStatus: () => fetch('/api/login/status').then(J),
  logout: () => post('/api/login/logout'),
  run: (watch) => post('/api/run' + (watch ? `?watch=${encodeURIComponent(watch)}` : '')),
  status: () => fetch('/api/status').then(J),
}
