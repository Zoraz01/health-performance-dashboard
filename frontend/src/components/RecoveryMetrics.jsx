
function TrendArrow({ dir, className = '' }) {
  return (
    <svg viewBox="0 0 12 12" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      {dir === 'up' ? (
        <><path d="M3 8L9 4" /><path d="M9 4H5.5" /><path d="M9 4V7" /></>
      ) : (
        <><path d="M3 4L9 8" /><path d="M9 8H5.5" /><path d="M9 8V5" /></>
      )}
    </svg>
  )
}

function deriveStatus({ value, baseline, betterIsHigher, warnPct = 5, badPct = 12 }) {
  const delta = ((value - baseline) / baseline) * 100
  const signedDelta = betterIsHigher ? delta : -delta
  if (signedDelta >= -warnPct) return { status: 'good', delta }
  if (signedDelta >= -badPct) return { status: 'warn', delta }
  return { status: 'bad', delta }
}

const STATUS_THEME = {
  good: {
    valueText: 'text-emerald-300',
    pillBg: 'bg-emerald-500/12 text-emerald-300 ring-emerald-500/30',
    label: 'On baseline',
    dot: 'bg-emerald-400',
  },
  warn: {
    valueText: 'text-amber-300',
    pillBg: 'bg-amber-500/12 text-amber-300 ring-amber-500/30',
    label: 'Below trend',
    dot: 'bg-amber-400',
  },
  bad: {
    valueText: 'text-red-300',
    pillBg: 'bg-red-500/15 text-red-300 ring-red-500/40',
    label: 'Recovery deficit',
    dot: 'bg-red-400',
  },
}

const DOT_GLOW  = { good: 'dot-ok',   warn: 'dot-warn',  bad: 'dot-bad'  }
const PILL_GLOW = { good: 'pill-ok',  warn: 'pill-warn', bad: 'pill-bad' }

function MiniBar({ value, baseline, max, status }) {
  const valuePct = Math.min(100, Math.max(4, (value / max) * 100))
  const basePct = Math.min(100, (baseline / max) * 100)
  const fill = { good: 'bg-emerald-400/80', warn: 'bg-amber-400/80', bad: 'bg-red-400/80' }[status]
  return (
    <div className="relative h-1 w-full bg-slate-800/80 rounded-full mt-3 track-inset">
      <div className={`absolute inset-y-0 left-0 ${fill} rounded-full transition-all duration-700`} style={{ width: `${valuePct}%` }} />
      <div className="absolute -top-1 -bottom-1 w-px bg-slate-500" style={{ left: `${basePct}%` }} title={`30-day avg: ${baseline}`} />
    </div>
  )
}

function RecoveryCard({ name, value, unit, baseline, betterIsHigher, max, format = (v) => v }) {
  if (value == null || baseline == null) return null
  const { status, delta } = deriveStatus({ value, baseline, betterIsHigher })
  const theme = STATUS_THEME[status]
  const deltaSign = delta >= 0 ? '+' : ''
  const arrowDir = delta >= 0 ? 'up' : 'down'
  return (
    <div className={`rounded-xl bg-slate-900/70 ring-1 ring-slate-800 p-3 sm:p-4 card card-interactive`}>
      <div className="flex items-start justify-between gap-1.5 mb-2.5">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-[0.14em] text-slate-500 font-semibold truncate">{name}</div>
          <div className="text-slate-400 text-[9.5px] mt-0.5 font-mono">avg {format(baseline)}{unit && ` ${unit}`}</div>
        </div>
        <span className={`inline-flex items-center gap-0.5 rounded-full ring-1 px-1.5 py-0.5 text-[9.5px] font-medium shrink-0 ${theme.pillBg} ${PILL_GLOW[status]}`}>
          <TrendArrow dir={arrowDir} className="w-2 h-2" />
          {deltaSign}{delta.toFixed(1)}%
        </span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className={`text-2xl font-semibold tabular-nums tracking-tight ${theme.valueText}`}>{format(value)}</span>
        <span className="text-slate-500 text-[10px] font-medium">{unit}</span>
      </div>
      <MiniBar value={value} baseline={baseline} max={max} status={status} />
      <div className="flex items-center gap-1 mt-2.5">
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${theme.dot} ${DOT_GLOW[status]}`} />
        <span className="text-[10px] text-slate-400 truncate">{theme.label}</span>
      </div>
    </div>
  )
}

const CARDS = [
  { name: 'HRV',        valueKey: 'hrv_ms',        baseKey: 'hrv_avg',             unit: 'ms',  betterIsHigher: true,  max: 60,  format: v => v.toFixed(1) },
  { name: 'Resting HR', valueKey: 'resting_hr',    baseKey: 'resting_hr_avg',      unit: 'bpm', betterIsHigher: false, max: 120, format: v => Math.round(v) },
  { name: 'Walking HR', valueKey: 'walking_hr_avg', baseKey: 'walking_hr_baseline', unit: 'bpm', betterIsHigher: false, max: 140, format: v => Math.round(v) },
]

const RHR_SOURCE_LABEL = {
  ring_official: 'RingConn',
  ring_computed:  'RingConn (est.)',
  watch:          'Apple Watch',
}

function HrvUnavailableCard() {
  return (
    <div className="rounded-xl bg-slate-900/40 ring-1 ring-slate-800/60 p-3 sm:p-4 flex flex-col justify-between">
      <div className="text-[10px] uppercase tracking-[0.14em] text-slate-600 font-semibold">HRV</div>
      <div className="flex flex-col items-start gap-1 mt-2">
        <span className="text-slate-600 text-lg font-semibold">—</span>
        <span className="text-[9.5px] text-slate-600 font-mono leading-tight">Apple Watch required</span>
      </div>
    </div>
  )
}

function spo2Color(pct) {
  if (pct == null)  return { text: 'text-slate-300', dot: 'bg-slate-500', label: '' }
  if (pct < 90)     return { text: 'text-red-300',   dot: 'bg-red-400',   label: 'Low — seek care' }
  if (pct < 95)     return { text: 'text-amber-300', dot: 'bg-amber-400', label: 'Below normal' }
  return              { text: 'text-emerald-300', dot: 'bg-emerald-400', label: 'Normal' }
}

function InlineStatRow({ label, value, unit, color, dot, statusLabel, source }) {
  return (
    <div className="rounded-xl bg-slate-900/70 ring-1 ring-slate-800 p-4 sm:p-5 flex items-center justify-between gap-4 card">
      <div>
        <div className="text-[10.5px] uppercase tracking-[0.16em] text-slate-500 font-semibold">{label}</div>
        {source && <div className="text-slate-600 text-[9.5px] font-mono mt-0.5">{source}</div>}
      </div>
      <div className="text-right">
        <div className="flex items-baseline gap-1 justify-end">
          <span className={`text-2xl font-semibold tabular-nums tracking-tight ${color}`}>{value}</span>
          <span className="text-slate-500 text-xs font-medium">{unit}</span>
        </div>
        {statusLabel && (
          <div className="flex items-center gap-1 justify-end mt-1">
            <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
            <span className="text-[10px] text-slate-400">{statusLabel}</span>
          </div>
        )}
      </div>
    </div>
  )
}

function Skeleton() {
  return (
    <section className="animate-pulse">
      <div className="flex items-baseline justify-between mb-3 px-1">
        <div className="h-3.5 w-32 bg-slate-800 rounded" />
        <div className="h-2.5 w-24 bg-slate-800 rounded" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="rounded-xl bg-slate-900/70 ring-1 ring-slate-800 p-3">
            <div className="flex items-start justify-between gap-2 mb-3">
              <div className="space-y-1.5">
                <div className="h-2.5 w-16 bg-slate-800 rounded" />
                <div className="h-2 w-20 bg-slate-800 rounded" />
              </div>
              <div className="h-5 w-14 bg-slate-800 rounded-full" />
            </div>
            <div className="h-8 w-20 bg-slate-800 rounded" />
            <div className="h-1 w-full bg-slate-800 rounded-full mt-3" />
            <div className="flex items-center gap-1.5 mt-3">
              <div className="w-1.5 h-1.5 rounded-full bg-slate-800" />
              <div className="h-2.5 w-16 bg-slate-800 rounded" />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function RecoveryMetrics({ data, loading }) {
  if (loading || !data) return <Skeleton />
  const missing = CARDS.filter(c => data[c.valueKey] == null || data[c.baseKey] == null)
    .map(c => c.name)
  const hasAny = missing.length < CARDS.length

  return (
    <section>
      <div className="flex items-baseline justify-between mb-3 px-1">
        <h3 className="text-slate-200 text-sm font-semibold">Recovery signals</h3>
        <span className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">vs 30-day baseline</span>
      </div>

      {hasAny ? (
        <>
          <div className="grid grid-cols-3 gap-2">
            {CARDS.map(c => {
              const value = data[c.valueKey]
              const baseline = data[c.baseKey]
              // HRV slot: show unavailable card when Watch isn't worn but ring data is present
              if (c.valueKey === 'hrv_ms' && value == null && (data.spo2 != null || data.resting_hr != null)) {
                return <HrvUnavailableCard key={c.name} />
              }
              // Resting HR: pass source label as subtitle via name
              if (c.valueKey === 'resting_hr') {
                const sourceLabel = RHR_SOURCE_LABEL[data.resting_hr_source]
                return (
                  <RecoveryCard
                    key={c.name}
                    name={sourceLabel ? `Resting HR · ${sourceLabel}` : c.name}
                    value={value}
                    baseline={baseline}
                    unit={c.unit}
                    betterIsHigher={c.betterIsHigher}
                    max={c.max}
                    format={c.format}
                  />
                )
              }
              return (
                <RecoveryCard
                  key={c.name}
                  name={c.name}
                  value={value}
                  baseline={baseline}
                  unit={c.unit}
                  betterIsHigher={c.betterIsHigher}
                  max={c.max}
                  format={c.format}
                />
              )
            })}
          </div>

          {(data.spo2 != null || data.respiratory_rate != null) && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
              {data.spo2 != null && (() => {
                const { text, dot, label } = spo2Color(data.spo2)
                return (
                  <InlineStatRow
                    label="Blood Oxygen"
                    value={data.spo2.toFixed(1)}
                    unit="%"
                    color={text}
                    dot={dot}
                    statusLabel={label}
                    source={data.spo2_avg != null ? `30-day avg ${data.spo2_avg.toFixed(1)}%` : 'RingConn'}
                  />
                )
              })()}
              {data.respiratory_rate != null && (
                <InlineStatRow
                  label="Respiratory Rate"
                  value={Math.round(data.respiratory_rate)}
                  unit="br/min"
                  color="text-slate-300"
                  dot="bg-slate-500"
                  statusLabel={data.respiratory_rate < 12 ? 'Low' : data.respiratory_rate > 20 ? 'Elevated' : 'Normal'}
                  source="Apple Watch"
                />
              )}
            </div>
          )}

          {missing.length > 0 && (
            <p className="text-[11px] text-slate-600 font-mono mt-2 px-1">
              Waiting on Apple Health sync for: {missing.join(', ')}
            </p>
          )}
        </>
      ) : (
        <div className="rounded-xl bg-slate-900/60 ring-1 ring-slate-800 px-5 py-6 text-center">
          <p className="text-slate-400 text-sm">Waiting for Apple Health to sync biometric data.</p>
          <p className="text-slate-600 text-[11px] font-mono mt-1">
            HRV, resting HR, and walking HR come via the 4-hour webhook.
            No 30-day minimum needed — baselines compute from whatever data exists.
          </p>
        </div>
      )}
    </section>
  )
}
