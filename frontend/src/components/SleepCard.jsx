function fmt(mins) {
  if (mins == null) return '—'
  const h = Math.floor(mins / 60)
  const m = Math.round(mins % 60)
  return `${h}h ${m}m`
}

function SleepStageRow({ label, value, color }) {
  return (
    <div className="flex items-center justify-between py-1.5">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-sm ${color}`} />
        <span className="text-slate-500 text-[11.5px] font-medium">{label}</span>
      </div>
      <span className="text-slate-400 text-[12px] font-mono tabular-nums">{value}</span>
    </div>
  )
}

export default function SleepCard({ data }) {
  const hasData = data?.total != null

  if (!hasData) {
    return (
      <section className="relative rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6 overflow-hidden">
        <div className="opacity-30 pointer-events-none">
          <div className="flex items-baseline justify-between mb-4">
            <div>
              <h3 className="text-slate-200 text-sm font-semibold">Sleep last night</h3>
              <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">Apple Health</p>
            </div>
            <div className="text-right">
              <div className="text-slate-500 text-[10px] uppercase tracking-widest">Total</div>
              <div className="text-slate-400 text-2xl font-semibold tabular-nums">—h —m</div>
            </div>
          </div>
          <div className="relative h-3 rounded-full bg-slate-800/80 overflow-hidden flex">
            <div className="h-full bg-indigo-500/20" style={{ width: '20%' }} />
            <div className="h-full bg-violet-500/20" style={{ width: '25%' }} />
            <div className="h-full bg-sky-500/20" style={{ width: '40%' }} />
            <div className="h-full bg-amber-500/20" style={{ width: '10%' }} />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-0">
            <SleepStageRow label="Deep"  value="—" color="bg-indigo-500/40" />
            <SleepStageRow label="REM"   value="—" color="bg-violet-500/40" />
            <SleepStageRow label="Core"  value="—" color="bg-sky-500/40"    />
            <SleepStageRow label="Awake" value="—" color="bg-amber-500/40"  />
          </div>
        </div>

        <div className="absolute inset-0 grid place-items-center bg-linear-to-b from-slate-900/60 via-slate-900/85 to-slate-900/95">
          <div className="text-center px-6">
            <div className="mx-auto w-10 h-10 rounded-full bg-slate-800 ring-1 ring-slate-700 grid place-items-center mb-3">
              <svg viewBox="0 0 20 20" className="w-5 h-5 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17.5 12A7.5 7.5 0 0 1 8 2.5a7.5 7.5 0 1 0 9.5 9.5Z"/>
              </svg>
            </div>
            <div className="text-slate-300 text-[13px] font-semibold mb-1">No sleep data yet</div>
            <div className="text-slate-500 text-[11.5px] max-w-[260px] leading-relaxed">
              Sleep stages will appear here once Apple Health syncs tonight's data.
            </div>
          </div>
        </div>
      </section>
    )
  }

  const total = data.total
  const deep  = data.deep  ?? 0
  const rem   = data.rem   ?? 0
  const awake = data.awake ?? 0
  const core  = Math.max(0, total - deep - rem - awake)

  const barPct = (mins) => total > 0 ? `${Math.round((mins / total) * 100)}%` : '0%'

  return (
    <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">Sleep last night</h3>
          <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">Apple Health</p>
        </div>
        <div className="text-right">
          <div className="text-slate-500 text-[10px] uppercase tracking-widest">Total</div>
          <div className="text-slate-200 text-2xl font-semibold tabular-nums">{fmt(total)}</div>
        </div>
      </div>

      {/* Stage bar */}
      <div className="relative h-3 rounded-full bg-slate-800/80 overflow-hidden flex">
        <div className="h-full bg-indigo-500" style={{ width: barPct(deep)  }} />
        <div className="h-full bg-violet-500" style={{ width: barPct(rem)   }} />
        <div className="h-full bg-sky-500"    style={{ width: barPct(core)  }} />
        <div className="h-full bg-amber-500"  style={{ width: barPct(awake) }} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-0">
        <SleepStageRow label="Deep"  value={fmt(deep)}  color="bg-indigo-500/70" />
        <SleepStageRow label="REM"   value={fmt(rem)}   color="bg-violet-500/70" />
        <SleepStageRow label="Core"  value={fmt(core)}  color="bg-sky-500/70"    />
        <SleepStageRow label="Awake" value={fmt(awake)} color="bg-amber-500/70"  />
      </div>
    </section>
  )
}
