const RECOVERY_FIXTURE = {
  lats:       { days_since_trained: 0, recovery_pct: 0   },
  upper_back: { days_since_trained: 0, recovery_pct: 0   },
  biceps:     { days_since_trained: 0, recovery_pct: 0   },
  forearms:   { days_since_trained: 0, recovery_pct: 0   },
  chest:      { days_since_trained: 1, recovery_pct: 33  },
  shoulders:  { days_since_trained: 1, recovery_pct: 33  },
  triceps:    { days_since_trained: 1, recovery_pct: 33  },
  quadriceps: { days_since_trained: 9, recovery_pct: 100 },
  hamstrings: { days_since_trained: 9, recovery_pct: 100 },
  glutes:     { days_since_trained: 9, recovery_pct: 100 },
  calves:     { days_since_trained: 9, recovery_pct: 100 },
  abdominals: { days_since_trained: 4, recovery_pct: 100 },
  lower_back: { days_since_trained: 4, recovery_pct: 100 },
  traps:      { days_since_trained: 4, recovery_pct: 100 },
}

function pretty(key) {
  return key.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
}

function barColor(pct) {
  if (pct <= 33) return 'bg-red-500/70'
  if (pct <= 66) return 'bg-amber-500/70'
  return 'bg-emerald-500/70'
}

function StatusChip({ count, label, theme }) {
  if (!count) return null
  const themes = {
    red:   'bg-red-500/12 text-red-400 ring-red-500/25',
    amber: 'bg-amber-500/12 text-amber-400 ring-amber-500/25',
    green: 'bg-emerald-500/12 text-emerald-400 ring-emerald-500/25',
  }
  return (
    <span className={`px-2 py-0.5 rounded-full text-[9.5px] font-mono ring-1 ${themes[theme]}`}>
      {count} {label}
    </span>
  )
}

function Skeleton() {
  const rows = [80, 55, 65, 90, 45, 70, 60]
  return (
    <section className="animate-pulse">
      <div className="flex items-center justify-between mb-3 px-1 flex-wrap gap-2">
        <div className="h-3.5 w-32 bg-slate-800 rounded" />
        <div className="flex items-center gap-1.5">
          <div className="h-5 w-16 bg-slate-800 rounded-full" />
          <div className="h-5 w-20 bg-slate-800 rounded-full" />
          <div className="h-5 w-12 bg-slate-800 rounded-full" />
        </div>
      </div>
      <div className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 overflow-hidden divide-y divide-slate-800/50">
        {rows.map((w, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-2.5">
            <div className="w-24 shrink-0 space-y-1.5">
              <div className={`h-3 bg-slate-800 rounded`} style={{ width: `${w}%` }} />
              <div className="h-2 w-8 bg-slate-800 rounded" />
            </div>
            <div className="flex-1 h-1.5 rounded-full bg-slate-800" />
            <div className="w-10 flex justify-end shrink-0">
              <div className="h-2.5 w-7 bg-slate-800 rounded" />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function RecoveryStatus({ data, loading }) {
  if (loading || !data) return <Skeleton />
  const entries = Object.entries(data).sort((a, b) => a[1].recovery_pct - b[1].recovery_pct)

  let fatigued = 0, recovering = 0, ready = 0
  entries.forEach(([, v]) => {
    if (v.recovery_pct <= 33) fatigued++
    else if (v.recovery_pct <= 66) recovering++
    else ready++
  })

  return (
    <section>
      <div className="flex items-center justify-between mb-3 px-1 flex-wrap gap-2">
        <h3 className="text-slate-200 text-sm font-semibold">Muscle Recovery</h3>
        <div className="flex items-center gap-1.5">
          <StatusChip count={fatigued}   label="fatigued"   theme="red"   />
          <StatusChip count={recovering} label="recovering" theme="amber" />
          <StatusChip count={ready}      label="ready"      theme="green" />
        </div>
      </div>
      <div className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 overflow-hidden divide-y divide-slate-800/50">
        {entries.map(([muscle, info]) => (
          <div key={muscle} className="flex items-center gap-3 px-4 py-2.5">
            <div className="w-24 shrink-0">
              <div className="text-slate-300 text-xs font-medium">{pretty(muscle)}</div>
              <div className="text-slate-500 text-[10px] font-mono mt-0.5">
                {info.days_since_trained === 0 ? 'today' : `${info.days_since_trained}d ago`}
              </div>
            </div>
            <div className="flex-1 relative h-1.5 rounded-full bg-slate-800">
              <div
                className={`absolute inset-y-0 left-0 rounded-full transition-all duration-700 ${barColor(info.recovery_pct)}`}
                style={{ width: `${Math.max(info.recovery_pct, info.recovery_pct === 0 ? 0 : 3)}%` }}
              />
            </div>
            <div className="w-10 text-right shrink-0">
              <span className="text-[10px] font-mono text-slate-400">{info.recovery_pct}%</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
