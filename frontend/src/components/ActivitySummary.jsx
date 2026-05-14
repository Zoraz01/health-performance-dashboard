
const Icon = {
  Steps: (p) => (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M6 4c-1 1.5-1 3.5 0 5 .8 1.2 2 1.5 2.5.8.6-.8.3-2.2-.5-3.6C7.2 4.6 6.7 4 6 4Z"/>
      <path d="M5 12c-.8.5-1 1.6-.4 2.5.6.9 1.7 1.1 2.4.5"/>
      <path d="M13 5c1 1.5 1 3.5 0 5-.8 1.2-2 1.5-2.5.8-.6-.8-.3-2.2.5-3.6.8-1.6 1.3-2.2 2-2.2Z"/>
      <path d="M14 13c.8.5 1 1.6.4 2.5-.6.9-1.7 1.1-2.4.5"/>
    </svg>
  ),
  Flame: (p) => (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M10 17c-3 0-5-2-5-4.5 0-2 1.5-3 2-4.5.5 1 1.5 1.5 2 1 0-2-1-3 0-5 1.5 1 4 3 4 6 0 .8-.3 1.5-.7 2 .9-.3 1.7-1 2.2-1.7 0 3.5-1.5 6.7-4.5 6.7Z"/>
    </svg>
  ),
  Clock: (p) => (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <circle cx="10" cy="10" r="6.5"/><path d="M10 6.5V10l2.5 1.5"/>
    </svg>
  ),
  Stand: (p) => (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <circle cx="10" cy="4" r="1.5"/><path d="M10 7v6"/><path d="M7 9.5l3-1.5 3 1.5"/><path d="M8 17l2-4 2 4"/>
    </svg>
  ),
  Route: (p) => (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M5 4h6a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h6"/><circle cx="5" cy="4" r="1.2"/><circle cx="15" cy="16" r="1.2"/>
    </svg>
  ),
  Stairs: (p) => (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M3 16h4v-3h4v-3h4V7h2"/>
    </svg>
  ),
}

function Metric({ icon: I, value, sub, label, accent = 'text-slate-400' }) {
  return (
    <div className="as-metric flex items-start gap-2 px-2 py-3 min-w-0">
      <div className={`mt-1 shrink-0 ${accent}`}><I className="w-[18px] h-[18px]" /></div>
      <div className="leading-tight min-w-0">
        <div className="as-value text-slate-100 text-lg font-semibold tabular-nums tracking-tight truncate">
          {value}
          {sub && <span className="text-slate-500 text-sm font-normal ml-1">{sub}</span>}
        </div>
        <div className="as-label text-[9.5px] uppercase tracking-[0.1em] text-slate-500 font-medium mt-1 leading-tight">
          {label}
        </div>
      </div>
    </div>
  )
}

function Skeleton() {
  return (
    <section className="as-root rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 overflow-hidden animate-pulse">
      {/* Header skeleton */}
      <div className="px-4 sm:px-5 pt-4 pb-3 flex items-end justify-between flex-wrap gap-x-4 gap-y-2 border-b border-slate-800/60">
        <div className="space-y-2">
          <div className="h-2.5 w-16 bg-slate-800 rounded" />
          <div className="h-7 w-40 bg-slate-800 rounded" />
        </div>
        <div className="flex items-center gap-5">
          <div className="space-y-1.5 text-right">
            <div className="h-2 w-8 bg-slate-800 rounded ml-auto" />
            <div className="h-5 w-16 bg-slate-800 rounded" />
          </div>
          <div className="space-y-1.5 text-right">
            <div className="h-2 w-14 bg-slate-800 rounded ml-auto" />
            <div className="h-5 w-16 bg-slate-800 rounded" />
          </div>
        </div>
      </div>
      {/* Metric tiles skeleton */}
      <div className="as-strip grid gap-y-1 px-1 py-1">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="flex items-start gap-2 px-2 py-3">
            <div className="mt-1 w-[18px] h-[18px] bg-slate-800 rounded shrink-0" />
            <div className="space-y-2 flex-1">
              <div className="h-5 w-14 bg-slate-800 rounded" />
              <div className="h-2 w-10 bg-slate-800 rounded" />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function ActivitySummary({ data, loading }) {
  if (loading || !data) return <Skeleton />
  const dateStr = new Date(data.date + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'short', day: 'numeric',
  })
  const items = [
    { icon: Icon.Steps,  value: Math.round(data.steps ?? 0).toLocaleString(), label: 'Steps',        accent: 'text-sky-400'     },
    { icon: Icon.Flame,  value: Math.round(data.active_calories ?? 0),        label: 'Active kcal',  accent: 'text-orange-400'  },
    { icon: Icon.Clock,  value: data.exercise_minutes != null ? Math.round(data.exercise_minutes) : '—', label: 'Exercise min', accent: 'text-emerald-400' },
    { icon: Icon.Stand,  value: data.stand_hours != null ? Math.round(data.stand_hours) : '—', sub: `/ ${data.stand_goal ?? 12}`, label: 'Stand hrs', accent: 'text-cyan-400' },
    { icon: Icon.Route,  value: data.distance_mi != null ? data.distance_mi.toFixed(1) : '—', label: 'Distance mi', accent: 'text-violet-400' },
    { icon: Icon.Stairs, value: data.flights_climbed != null ? Math.round(data.flights_climbed) : '—', label: 'Flights', accent: 'text-amber-400' },
  ]

  return (
    <section className="as-root rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 overflow-hidden">
      <div className="px-4 sm:px-5 pt-4 pb-3 flex items-end justify-between flex-wrap gap-x-4 gap-y-2 border-b border-slate-800/60">
        <div className="min-w-0">
          <div className="text-[10.5px] uppercase tracking-[0.18em] text-slate-500 font-medium">Yesterday</div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-slate-100 mt-0.5 tracking-tight">{dateStr}</h1>
        </div>
        <div className="flex items-center gap-4 sm:gap-5">
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest text-slate-500">HRV</div>
            <div className="text-amber-300 text-base font-semibold tabular-nums">
              {data.hrv_ms != null ? data.hrv_ms.toFixed(1) : '—'} <span className="text-slate-500 text-xs">ms</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Resting HR</div>
            <div className="text-amber-300 text-base font-semibold tabular-nums">
              {data.resting_hr ?? '—'} <span className="text-slate-500 text-xs">bpm</span>
            </div>
          </div>
        </div>
      </div>
      <div className="as-strip grid gap-y-1 px-1 py-1">
        {items.map((m, i) => <Metric key={i} {...m} />)}
      </div>
    </section>
  )
}
