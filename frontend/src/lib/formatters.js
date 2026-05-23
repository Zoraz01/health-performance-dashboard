export function prettyKey(key) {
  return key.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
}

export function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' })
}

export function fmtDate(iso) {
  if (!iso) return ''
  // Apple Health format "YYYY-MM-DD HH:MM:SS ±HHMM" has spaces; normalize to ISO 8601
  const normalized = iso.replace(' ', 'T').replace(' ', '')
  const d = new Date(normalized)
  if (isNaN(d)) return ''
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
}

export function fmtDuration(min) {
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

export function fmtMin(min) {
  if (min == null) return null
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}
