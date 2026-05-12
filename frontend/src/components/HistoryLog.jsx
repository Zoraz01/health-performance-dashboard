import { useState, useEffect, useMemo } from 'react'
import apiFetch from '../apiFetch'

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

function fmtMonthYear(iso) {
  const [y, m] = iso.split('-')
  return new Date(+y, +m - 1, 1).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

function daysInMonth(year, month)   { return new Date(year, month, 0).getDate() }
function firstDayOfWeek(year, month) { return new Date(year, month - 1, 1).getDay() }
function isoToComponents(iso) {
  const [y, m, d] = iso.split('-').map(Number)
  return { y, m, d }
}
function fmtMin(min) {
  if (min == null) return null
  const h = Math.floor(min / 60), m = Math.round(min % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

// ── small atoms ───────────────────────────────────────────────────────────────

function ScoreBadge({ score }) {
  if (score == null) return null
  const cls = score >= 8 ? 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25'
            : score >= 5 ? 'bg-amber-500/15 text-amber-400 ring-amber-500/25'
            :               'bg-red-500/15 text-red-400 ring-red-500/25'
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold tabular-nums ring-1 ${cls}`}>
      {score}
    </span>
  )
}

function ScoreDot({ score }) {
  if (score == null) return <span className="w-1.5 h-1.5 rounded-full bg-slate-700 inline-block" />
  const bg = score >= 8 ? 'bg-emerald-400' : score >= 5 ? 'bg-amber-400' : 'bg-red-400'
  return <span className={`w-1.5 h-1.5 rounded-full ${bg} inline-block`} />
}

function ChevronIcon({ open }) {
  return (
    <svg viewBox="0 0 12 12" className={`w-3 h-3 text-slate-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 4l4 4 4-4" />
    </svg>
  )
}

// ── Detail section layout helpers ─────────────────────────────────────────────

function DetailSection({ title, children }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-[0.18em] text-slate-600 font-semibold mb-2">{title}</div>
      {children}
    </div>
  )
}

function StatGrid({ children }) {
  return <div className="grid grid-cols-3 sm:grid-cols-4 gap-x-4 gap-y-3">{children}</div>
}

function StatCell({ label, value, unit }) {
  if (value == null) return null
  return (
    <div>
      <div className="text-[9.5px] uppercase tracking-wider text-slate-500 font-mono">{label}</div>
      <div className="text-slate-200 text-[13px] font-semibold tabular-nums mt-0.5">
        {value}<span className="text-slate-600 text-[10px] font-normal ml-0.5">{unit}</span>
      </div>
    </div>
  )
}

function ScoreBar({ label, value, color }) {
  if (value == null) return null
  const pct = (value / 10) * 100
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="text-[10px] text-slate-500 w-20 shrink-0">{label}</div>
      <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="text-[10px] tabular-nums font-semibold w-5 text-right" style={{ color }}>{value}</div>
    </div>
  )
}

function SleepBar({ deep, rem, core, awake }) {
  const total = (deep ?? 0) + (rem ?? 0) + (core ?? 0) + (awake ?? 0)
  if (!total) return null
  const pct = (v) => `${((v / total) * 100).toFixed(1)}%`
  return (
    <div className="flex rounded overflow-hidden h-2 w-full">
      {deep  > 0 && <div style={{ width: pct(deep),  background: '#818cf8' }} />}
      {rem   > 0 && <div style={{ width: pct(rem),   background: '#a78bfa' }} />}
      {core  > 0 && <div style={{ width: pct(core),  background: '#38bdf8' }} />}
      {awake > 0 && <div style={{ width: pct(awake), background: '#fbbf24' }} />}
    </div>
  )
}

// ── Expanded day detail ───────────────────────────────────────────────────────

function DayDetail({ day, record, loadingRecord }) {
  const analysis = record?.analysis
  const scores   = day.scores

  const hasActivity = [day.steps, day.active_calories, day.exercise_minutes,
                       day.stand_hours, day.distance_mi, day.flights_climbed].some(v => v != null)
  const hasRecovery = [day.hrv_ms, day.resting_hr, day.cardio_recovery, day.walking_hr_avg].some(v => v != null)
  const hasSleep    = day.sleep_total_min != null
  const hasWorkouts = day.workouts?.length > 0
  const hasScores   = scores && Object.values(scores).some(v => v != null)

  const sleepTotal = day.sleep_total_min
  const sleepDeep  = day.sleep_deep_min  ?? 0
  const sleepRem   = day.sleep_rem_min   ?? 0
  const sleepAwake = day.sleep_awake_min ?? 0
  const sleepCore  = sleepTotal ? Math.max(0, sleepTotal - sleepDeep - sleepRem - sleepAwake) : 0

  const SCORE_ROWS = [
    { key: 'overall',     label: 'Overall',     color: '#e2e8f0' },
    { key: 'training',    label: 'Training',    color: '#fbbf24' },
    { key: 'recovery',    label: 'Recovery',    color: '#34d399' },
    { key: 'balance',     label: 'Balance',     color: '#38bdf8' },
    { key: 'consistency', label: 'Consistency', color: '#a78bfa' },
  ]

  return (
    <div className="border-t border-slate-800 px-4 py-4 space-y-5 bg-slate-950/40">

      {/* Scores */}
      {hasScores && (
        <DetailSection title="Scores">
          <div className="space-y-2">
            {SCORE_ROWS.map(({ key, label, color }) => (
              <ScoreBar key={key} label={label} value={scores[key]} color={color} />
            ))}
          </div>
        </DetailSection>
      )}

      {/* Activity */}
      {hasActivity && (
        <DetailSection title="Activity">
          <StatGrid>
            <StatCell label="Steps"    value={day.steps != null ? Math.round(day.steps).toLocaleString() : null} unit="" />
            <StatCell label="Calories" value={day.active_calories != null ? Math.round(day.active_calories) : null} unit="kcal" />
            <StatCell label="Exercise" value={day.exercise_minutes != null ? Math.round(day.exercise_minutes) : null} unit="min" />
            <StatCell label="Stand"    value={day.stand_hours} unit="hrs" />
            <StatCell label="Distance" value={day.distance_mi != null ? day.distance_mi.toFixed(1) : null} unit="mi" />
            <StatCell label="Flights"  value={day.flights_climbed != null ? Math.round(day.flights_climbed) : null} unit="" />
            <StatCell label="Weight"   value={day.body_weight_lbs != null ? day.body_weight_lbs.toFixed(1) : null} unit="lbs" />
          </StatGrid>
        </DetailSection>
      )}

      {/* Recovery */}
      {hasRecovery && (
        <DetailSection title="Recovery">
          <StatGrid>
            <StatCell label="HRV"        value={day.hrv_ms != null ? day.hrv_ms.toFixed(1) : null}            unit="ms" />
            <StatCell label="Resting HR" value={day.resting_hr}                                                unit="bpm" />
            <StatCell label="Cardio Rec" value={day.cardio_recovery != null ? day.cardio_recovery.toFixed(1) : null} unit="bpm" />
            <StatCell label="Walking HR" value={day.walking_hr_avg != null ? Math.round(day.walking_hr_avg) : null} unit="bpm" />
          </StatGrid>
        </DetailSection>
      )}

      {/* Sleep */}
      {hasSleep && (
        <DetailSection title="Sleep">
          <div className="space-y-2">
            <SleepBar deep={sleepDeep} rem={sleepRem} core={sleepCore} awake={sleepAwake} />
            <div className="flex gap-4 flex-wrap">
              <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
                <span className="w-1.5 h-1.5 rounded-sm bg-indigo-400 inline-block" />
                Deep {fmtMin(sleepDeep)}
              </span>
              <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
                <span className="w-1.5 h-1.5 rounded-sm bg-violet-400 inline-block" />
                REM {fmtMin(sleepRem)}
              </span>
              <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
                <span className="w-1.5 h-1.5 rounded-sm bg-sky-400 inline-block" />
                Core {fmtMin(sleepCore)}
              </span>
              <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
                <span className="w-1.5 h-1.5 rounded-sm bg-amber-400 inline-block" />
                Awake {fmtMin(sleepAwake)}
              </span>
              <span className="text-[10.5px] text-slate-500 font-semibold">
                Total {fmtMin(sleepTotal)}
              </span>
            </div>
          </div>
        </DetailSection>
      )}

      {/* Workouts */}
      {hasWorkouts && (
        <DetailSection title="Workouts">
          <div className="space-y-2">
            {day.workouts.map((w, i) => {
              const name = w.title ?? w.name ?? 'Workout'
              const vol  = w.total_volume_kg ? `${Math.round(w.total_volume_kg).toLocaleString()} kg` : null
              const muscles = w.primary_muscle_groups ?? w.muscle_groups ?? []
              return (
                <div key={i} className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-slate-300 text-[12px] font-medium">{name}</div>
                    {muscles.length > 0 && (
                      <div className="flex gap-1 flex-wrap mt-0.5">
                        {muscles.slice(0, 4).map(m => (
                          <span key={m} className="text-[9.5px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 font-mono capitalize">
                            {m.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  {vol && <span className="text-slate-500 text-[11px] tabular-nums shrink-0">{vol}</span>}
                </div>
              )
            })}
          </div>
        </DetailSection>
      )}

      {/* Claude analysis */}
      {loadingRecord ? (
        <div className="text-[10px] text-slate-700 font-mono animate-pulse">Loading analysis…</div>
      ) : analysis?.summary ? (
        <DetailSection title="AI Analysis">
          <p className="text-slate-400 text-[12px] leading-relaxed">{analysis.summary}</p>
        </DetailSection>
      ) : null}
    </div>
  )
}

// ── Expandable day row (recent list) ─────────────────────────────────────────

function ExpandableDay({ day }) {
  const [open, setOpen]               = useState(false)
  const [record, setRecord]           = useState(null)
  const [loadingRecord, setLoadingRecord] = useState(false)
  const [fetched, setFetched]         = useState(false)

  const toggle = () => {
    if (!open && !fetched) {
      setFetched(true)
      setLoadingRecord(true)
      apiFetch(`/api/record/${day.date}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => setRecord(data))
        .catch(() => {})
        .finally(() => setLoadingRecord(false))
    }
    setOpen(o => !o)
  }

  const workoutNames = (day.workouts || []).map(w => w.title ?? w.name).filter(Boolean)

  return (
    <div className={`rounded-xl ring-1 transition-all duration-200 overflow-hidden ${open ? 'ring-slate-600 bg-slate-900' : 'ring-slate-800 bg-slate-900/60 hover:ring-slate-700'}`}>
      <button
        onClick={toggle}
        className="w-full px-4 py-3 flex items-center gap-3 text-left"
      >
        {/* Date */}
        <div className="shrink-0 w-[90px]">
          <div className="text-slate-300 text-[12px] font-semibold">{fmtDate(day.date)}</div>
          <div className="text-slate-600 text-[10px] font-mono mt-0.5">{day.date}</div>
        </div>

        {/* Inline stats */}
        <div className="flex-1 flex gap-4 min-w-0 flex-wrap">
          {day.steps != null && (
            <div className="min-w-0">
              <div className="text-[9.5px] uppercase tracking-wider text-slate-500 font-mono">Steps</div>
              <div className="text-slate-300 text-[12px] font-semibold tabular-nums">{Math.round(day.steps).toLocaleString()}</div>
            </div>
          )}
          {day.hrv_ms != null && (
            <div>
              <div className="text-[9.5px] uppercase tracking-wider text-slate-500 font-mono">HRV</div>
              <div className="text-slate-300 text-[12px] font-semibold tabular-nums">{day.hrv_ms.toFixed(1)}<span className="text-slate-600 text-[10px] ml-0.5">ms</span></div>
            </div>
          )}
          {day.active_calories != null && (
            <div>
              <div className="text-[9.5px] uppercase tracking-wider text-slate-500 font-mono">Cal</div>
              <div className="text-slate-300 text-[12px] font-semibold tabular-nums">{Math.round(day.active_calories)}</div>
            </div>
          )}
          {workoutNames.length > 0 && (
            <div className="min-w-0">
              <div className="text-[9.5px] uppercase tracking-wider text-slate-500 font-mono">Workout</div>
              <div className="text-slate-400 text-[11px] truncate max-w-[120px]">{workoutNames.join(', ')}</div>
            </div>
          )}
        </div>

        {/* Score + chevron */}
        <div className="flex items-center gap-2 shrink-0">
          <ScoreBadge score={day.score} />
          <ChevronIcon open={open} />
        </div>
      </button>

      {open && (
        <DayDetail day={day} record={record} loadingRecord={loadingRecord} />
      )}
    </div>
  )
}

// ── Calendar grid (older months) ─────────────────────────────────────────────

function MonthCalendar({ year, month, dayMap, onDayClick, selectedDate }) {
  const totalDays = daysInMonth(year, month)
  const startDow  = firstDayOfWeek(year, month)
  const cells     = []

  for (let i = 0; i < startDow; i++) cells.push(null)
  for (let d = 1; d <= totalDays; d++) cells.push(d)

  return (
    <div className="mt-4">
      <div className="grid grid-cols-7 mb-1">
        {['Su','Mo','Tu','We','Th','Fr','Sa'].map(d => (
          <div key={d} className="text-center text-[9px] text-slate-600 font-mono uppercase">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-y-1">
        {cells.map((day, i) => {
          if (!day) return <div key={`empty-${i}`} />
          const iso  = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`
          const data = dayMap[iso]
          const isSelected = iso === selectedDate

          return (
            <button
              key={iso}
              onClick={() => data && onDayClick(iso)}
              disabled={!data}
              className={`flex flex-col items-center py-1.5 rounded-lg transition-colors ${
                isSelected ? 'bg-slate-700'
                : data ? 'hover:bg-slate-800 cursor-pointer'
                : 'opacity-25 cursor-default'
              }`}
            >
              <span className="text-[11px] text-slate-400 font-mono">{day}</span>
              <ScoreDot score={data?.score} />
            </button>
          )
        })}
      </div>
    </div>
  )
}

function MonthSection({ monthKey, days }) {
  const [expanded, setExpanded]     = useState(false)
  const [selectedDate, setSelected] = useState(null)
  const [record, setRecord]         = useState(null)
  const [loadingRecord, setLoadingRecord] = useState(false)
  const [fetchedDate, setFetchedDate] = useState(null)

  const { y, m } = isoToComponents(monthKey + '-01')

  const dayMap = useMemo(
    () => Object.fromEntries(days.map(d => [d.date, d])),
    [days]
  )

  const handleDayClick = (iso) => {
    if (iso === selectedDate) {
      setSelected(null)
      return
    }
    setSelected(iso)
    if (iso !== fetchedDate) {
      setFetchedDate(iso)
      setRecord(null)
      setLoadingRecord(true)
      apiFetch(`/api/record/${iso}`)
        .then(r => r.ok ? r.json() : null)
        .then(data => setRecord(data))
        .catch(() => {})
        .finally(() => setLoadingRecord(false))
    }
  }

  const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null

  const avgSteps  = avg(days.filter(d => d.steps != null).map(d => d.steps))
  const avgHrv    = avg(days.filter(d => d.hrv_ms != null).map(d => d.hrv_ms))
  const avgScore  = avg(days.filter(d => d.score != null).map(d => d.score))
  const workouts  = days.reduce((n, d) => n + (d.workouts?.length || 0), 0)

  const selectedDay = selectedDate ? dayMap[selectedDate] : null

  return (
    <div className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 overflow-hidden">
      {/* Month header */}
      <button
        className="w-full px-5 py-4 flex items-center gap-4 hover:bg-slate-800/40 transition-colors text-left"
        onClick={() => setExpanded(e => !e)}
      >
        <div className="flex-1">
          <div className="text-slate-200 text-sm font-semibold">{fmtMonthYear(monthKey + '-01')}</div>
          <div className="flex gap-3 mt-1.5 flex-wrap">
            {avgSteps != null && <span className="text-slate-500 text-[11px] font-mono">{Math.round(avgSteps).toLocaleString()} avg steps</span>}
            {avgHrv   != null && <span className="text-slate-500 text-[11px] font-mono">{avgHrv.toFixed(1)} ms avg HRV</span>}
            {workouts > 0     && <span className="text-slate-500 text-[11px] font-mono">{workouts} workouts</span>}
            <span className="text-slate-600 text-[11px] font-mono">{days.length} days logged</span>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {avgScore != null && (
            <span className={`text-[11px] font-bold tabular-nums px-2 py-0.5 rounded ring-1 ${
              avgScore >= 8 ? 'bg-emerald-500/15 text-emerald-400 ring-emerald-500/25'
            : avgScore >= 5 ? 'bg-amber-500/15  text-amber-400  ring-amber-500/25'
            :                  'bg-red-500/15    text-red-400    ring-red-500/25'
            }`}>
              {avgScore.toFixed(1)} avg
            </span>
          )}
          <ChevronIcon open={expanded} />
        </div>
      </button>

      {/* Calendar + inline detail */}
      {expanded && (
        <div className="border-t border-slate-800 px-5 pb-5">
          <MonthCalendar year={y} month={m} dayMap={dayMap} onDayClick={handleDayClick} selectedDate={selectedDate} />
          {selectedDay && (
            <div className="mt-3 rounded-xl ring-1 ring-slate-700 overflow-hidden">
              {/* Mini header for the selected day */}
              <div className="px-4 py-2.5 flex items-center justify-between bg-slate-800/60">
                <div>
                  <span className="text-slate-200 text-[12px] font-semibold">{fmtDate(selectedDay.date)}</span>
                  <span className="text-slate-600 text-[10px] font-mono ml-2">{selectedDay.date}</span>
                </div>
                <div className="flex items-center gap-2">
                  <ScoreBadge score={selectedDay.score} />
                  <button
                    onClick={() => setSelected(null)}
                    className="w-5 h-5 rounded-full bg-slate-700 hover:bg-slate-600 grid place-items-center transition-colors"
                  >
                    <svg viewBox="0 0 12 12" className="w-2.5 h-2.5 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                      <path d="M2 2l8 8M10 2l-8 8" />
                    </svg>
                  </button>
                </div>
              </div>
              <DayDetail day={selectedDay} record={record} loadingRecord={loadingRecord} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────

const DAYS_RECENT = 30

export default function HistoryLog() {
  const [days, setDays]     = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const to   = new Date()
    const from = new Date(to)
    from.setDate(from.getDate() - 364)
    const toStr   = to.toISOString().slice(0, 10)
    const fromStr = from.toISOString().slice(0, 10)

    Promise.all([
      apiFetch(`/api/snapshots?from=${fromStr}&to=${toStr}`).then(r => r.ok ? r.json() : []),
      apiFetch('/api/scores?days=365').then(r => r.ok ? r.json() : []),
    ])
      .then(([snapshots, scores]) => {
        const scoreMap = Object.fromEntries(scores.map(s => [s.date, {
          overall:     s.overall,
          training:    s.training_quality,
          recovery:    s.recovery,
          balance:     s.volume_balance,
          consistency: s.consistency,
        }]))

        const merged = snapshots
          .filter(s => s.steps != null || s.workouts?.length)
          .map(s => ({
            date:             s.date,
            // activity
            steps:            s.steps,
            active_calories:  s.active_calories,
            exercise_minutes: s.exercise_minutes,
            stand_hours:      s.stand_hours,
            distance_mi:      s.distance_mi,
            flights_climbed:  s.flights_climbed,
            // recovery
            hrv_ms:           s.hrv_ms,
            resting_hr:       s.resting_hr,
            cardio_recovery:  s.cardio_recovery,
            walking_hr_avg:   s.walking_hr_avg,
            // body
            body_weight_lbs:  s.body_weight_kg != null
              ? +(s.body_weight_kg * 2.20462).toFixed(1)
              : null,
            // sleep
            sleep_total_min:  s.sleep_total_min,
            sleep_deep_min:   s.sleep_deep_min,
            sleep_rem_min:    s.sleep_rem_min,
            sleep_awake_min:  s.sleep_awake_min,
            // training
            muscle_volume:    s.muscle_volume,
            recovery_status:  s.recovery_status,
            workouts:         s.workouts ?? [],
            // scores
            score:            scoreMap[s.date]?.overall ?? null,
            scores:           scoreMap[s.date] ?? null,
          }))
          .sort((a, b) => b.date.localeCompare(a.date))

        setDays(merged)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const { recent, byMonth } = useMemo(() => {
    if (!days.length) return { recent: [], byMonth: {} }

    const cutoff = (() => {
      const d = new Date(days[0].date + 'T00:00:00')
      d.setDate(d.getDate() - DAYS_RECENT)
      return d.toISOString().slice(0, 10)
    })()

    const recent   = days.filter(d => d.date > cutoff)
    const archived = days.filter(d => d.date <= cutoff)

    const byMonth = {}
    for (const day of archived) {
      const key = day.date.slice(0, 7)
      if (!byMonth[key]) byMonth[key] = []
      byMonth[key].push(day)
    }

    return { recent, byMonth }
  }, [days])

  const monthKeys = Object.keys(byMonth).sort((a, b) => b.localeCompare(a))

  if (loading) {
    return (
      <section className="space-y-2 animate-pulse">
        {[1,2,3,4,5].map(i => (
          <div key={i} className="h-16 rounded-xl bg-slate-900/60 ring-1 ring-slate-800" />
        ))}
      </section>
    )
  }

  if (!days.length) {
    return (
      <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 px-5 py-10 text-center">
        <p className="text-slate-500 text-sm">No history yet — data will appear once Apple Health starts syncing.</p>
      </section>
    )
  }

  return (
    <section className="space-y-6">
      {recent.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-baseline justify-between px-1 mb-3">
            <h3 className="text-slate-200 text-sm font-semibold">Last 30 days</h3>
            <span className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">{recent.length} days logged</span>
          </div>
          {recent.map(day => (
            <ExpandableDay key={day.date} day={day} />
          ))}
        </div>
      )}

      {monthKeys.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-baseline justify-between px-1 mb-1">
            <h3 className="text-slate-200 text-sm font-semibold">Earlier</h3>
            <span className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">{monthKeys.length} months</span>
          </div>
          {monthKeys.map(key => (
            <MonthSection key={key} monthKey={key} days={byMonth[key]} />
          ))}
        </div>
      )}
    </section>
  )
}
