export function scoreColor(score) {
  if (score >= 8) return {
    bar:   'bg-emerald-400',
    text:  'text-emerald-300',
    badge: 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25',
    dot:   'bg-emerald-400',
    hex:   '#34d399',
  }
  if (score >= 5) return {
    bar:   'bg-amber-400',
    text:  'text-amber-300',
    badge: 'bg-amber-500/15 text-amber-400 ring-amber-500/25',
    dot:   'bg-amber-400',
    hex:   '#fbbf24',
  }
  return {
    bar:   'bg-red-400',
    text:  'text-red-300',
    badge: 'bg-red-500/15 text-red-400 ring-red-500/25',
    dot:   'bg-red-400',
    hex:   '#f87171',
  }
}

export const SCORE_DIMENSION_ROWS = [
  { key: 'overall',     label: 'Overall',     color: '#e2e8f0' },
  { key: 'training',    label: 'Training',    color: '#fbbf24' },
  { key: 'recovery',    label: 'Recovery',    color: '#34d399' },
  { key: 'balance',     label: 'Balance',     color: '#38bdf8' },
  { key: 'consistency', label: 'Consistency', color: '#a78bfa' },
]
