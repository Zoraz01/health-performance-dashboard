import { useState, useEffect, useRef } from 'react'
import WorkoutSetLog from './WorkoutSetLog'
import WorkoutHRChart from './WorkoutHRChart'


function fmtDuration(min) {
  const h = Math.floor(min / 60)
  const m = Math.round(min % 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function pretty(key) {
  return key.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
}

function Chevron({ open }) {
  return (
    <svg viewBox="0 0 12 12" className={`w-3 h-3 transition-transform duration-200 ${open ? 'rotate-180' : ''} text-slate-500`} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
      <path d="M2 4l4 4 4-4" />
    </svg>
  )
}

function LoadingRows() {
  return (
    <div className="space-y-2.5 animate-pulse py-2">
      {[60, 80, 55].map((w, i) => (
        <div key={i} className="flex gap-3">
          <div className="h-3 bg-slate-800 rounded w-6" />
          <div className={`h-3 bg-slate-800 rounded`} style={{ width: `${w}%` }} />
          <div className="h-3 bg-slate-800 rounded w-12 ml-auto" />
        </div>
      ))}
    </div>
  )
}

function HevySession({ session }) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail]     = useState(null)
  const loadingRef              = useRef(false)

  useEffect(() => {
    if (!expanded || detail !== null || loadingRef.current) return
    loadingRef.current = true
    fetch(`/api/workout/${session.id}/sets`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        setDetail(data ?? {
          workout_id: session.id,
          exercises: (session.exercises ?? []).map((ex, i) => ({
            exercise_index: i,
            title: ex.title,
            primary_muscle_group: ex.primary_muscle_group,
            sets: (ex.sets ?? []).map((s, j) => ({ set_index: j, type: 'normal', ...s })),
          })),
        })
      })
      .catch(() => {
        setDetail({
          workout_id: session.id,
          exercises: (session.exercises ?? []).map((ex, i) => ({
            exercise_index: i,
            title: ex.title,
            primary_muscle_group: ex.primary_muscle_group,
            sets: (ex.sets ?? []).map((s, j) => ({ set_index: j, type: 'normal', ...s })),
          })),
        })
      })
      .finally(() => { loadingRef.current = false })
  }, [expanded, detail, session])

  const setCount = (session.exercises ?? []).reduce((sum, ex) => sum + (ex.sets?.length ?? 0), 0)
  const topMuscles = [...new Set((session.exercises ?? []).map(e => e.primary_muscle_group))].slice(0, 3)

  return (
    <div className="rounded-xl bg-slate-900/70 ring-1 ring-slate-800 overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-slate-800/40 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="shrink-0 w-8 h-8 rounded-lg bg-slate-800 ring-1 ring-slate-700/60 grid place-items-center">
            <svg viewBox="0 0 16 16" className="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 8h2.5M12.5 8H15M3.5 5v6M12.5 5v6M3.5 8h9M6 6.5V9.5M10 6.5V9.5" />
            </svg>
          </div>
          <div className="min-w-0">
            <div className="text-slate-100 text-[13px] font-semibold">{session.title}</div>
            <div className="text-slate-500 text-[10px] font-mono mt-0.5">
              {fmtDate(session.start_time)} · {fmtDuration(session.duration_min)} · {setCount} sets
              {session.active_calories != null && ` · ${Math.round(session.active_calories)} kcal`}
              {session.avg_heart_rate  != null && ` · avg ${Math.round(session.avg_heart_rate)} bpm`}
              {session.max_heart_rate  != null && ` · max ${Math.round(session.max_heart_rate)} bpm`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {topMuscles.map(m => (
            <span key={m} className="hidden sm:inline px-1.5 py-0.5 rounded text-[9px] bg-slate-800 text-slate-500 uppercase tracking-wider">
              {pretty(m)}
            </span>
          ))}
          <Chevron open={expanded} />
        </div>
      </button>
      {expanded && (
        <div className="border-t border-slate-800/60 px-4 pb-4 pt-3">
          {/* Biometric stats stitched from Apple Health */}
          {(session.active_calories != null || session.avg_heart_rate != null) && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
              {session.duration_min != null && (
                <div className="rounded-lg bg-slate-800/60 ring-1 ring-slate-800 px-3 py-2 text-center">
                  <div className="text-slate-200 text-[13px] font-semibold tabular-nums">{fmtDuration(session.duration_min)}</div>
                  <div className="text-slate-500 text-[9.5px] uppercase tracking-wider mt-0.5">Duration</div>
                </div>
              )}
              {session.active_calories != null && (
                <div className="rounded-lg bg-slate-800/60 ring-1 ring-slate-800 px-3 py-2 text-center">
                  <div className="text-slate-200 text-[13px] font-semibold tabular-nums">{Math.round(session.active_calories)}</div>
                  <div className="text-slate-500 text-[9.5px] uppercase tracking-wider mt-0.5">kcal</div>
                </div>
              )}
              {session.avg_heart_rate != null && (
                <div className="rounded-lg bg-slate-800/60 ring-1 ring-slate-800 px-3 py-2 text-center">
                  <div className="text-slate-200 text-[13px] font-semibold tabular-nums">{Math.round(session.avg_heart_rate)}</div>
                  <div className="text-slate-500 text-[9.5px] uppercase tracking-wider mt-0.5">Avg HR</div>
                </div>
              )}
              {session.max_heart_rate != null && (
                <div className="rounded-lg bg-slate-800/60 ring-1 ring-slate-800 px-3 py-2 text-center">
                  <div className="text-slate-200 text-[13px] font-semibold tabular-nums">{Math.round(session.max_heart_rate)}</div>
                  <div className="text-slate-500 text-[9.5px] uppercase tracking-wider mt-0.5">Max HR</div>
                </div>
              )}
            </div>
          )}
          {loadingRef.current ? <LoadingRows /> : <WorkoutSetLog fixture={detail} />}
        </div>
      )}
    </div>
  )
}

function AppleSession({ session }) {
  const [expanded, setExpanded] = useState(false)
  const [hrData, setHrData]     = useState(null)
  const hrLoadingRef            = useRef(false)

  useEffect(() => {
    if (!expanded || hrData !== null || hrLoadingRef.current) return
    hrLoadingRef.current = true
    fetch(`/api/workout/${session.id}/hr`)
      .then(r => r.ok ? r.json() : { workout_id: session.id, samples: [] })
      .catch(() => ({ workout_id: session.id, samples: [] }))
      .then(data => setHrData(data))
      .finally(() => { hrLoadingRef.current = false })
  }, [expanded, hrData, session])

  const name = session.name ?? 'Workout'

  const stats = [
    { label: 'Duration',  value: fmtDuration(session.duration_min) },
    { label: 'Calories',  value: session.active_calories != null ? `${Math.round(session.active_calories)} kcal` : '—' },
    { label: 'Avg HR',    value: session.avg_heart_rate != null   ? `${Math.round(session.avg_heart_rate)} bpm`  : '—' },
    { label: 'Max HR',    value: session.max_heart_rate != null   ? `${Math.round(session.max_heart_rate)} bpm`  : '—' },
    { label: 'Distance',  value: session.distance_mi != null      ? `${session.distance_mi.toFixed(1)} mi` : '—' },
  ]

  return (
    <div className="rounded-xl bg-slate-900/70 ring-1 ring-slate-800 overflow-hidden">
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-slate-800/40 transition-colors"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="shrink-0 w-8 h-8 rounded-lg bg-slate-800 ring-1 ring-slate-700/60 grid place-items-center">
            <svg viewBox="0 0 16 16" className="w-4 h-4 text-red-400" fill="currentColor">
              <path d="M8 13.7C7.6 13.3 2 9 2 5.5A3.5 3.5 0 0 1 8 3a3.5 3.5 0 0 1 6 2.5C14 9 8.4 13.3 8 13.7Z"/>
            </svg>
          </div>
          <div className="min-w-0">
            <div className="text-slate-100 text-[13px] font-semibold">{name}</div>
            <div className="text-slate-500 text-[10px] font-mono mt-0.5">
              {fmtDate(session.start ?? session.start_time)} · {fmtDuration(session.duration_min)}
              {session.active_calories != null && ` · ${session.active_calories} kcal`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-[9px] uppercase tracking-wider text-slate-600 font-mono">Apple Health</span>
          <Chevron open={expanded} />
        </div>
      </button>
      {expanded && (
        <div className="border-t border-slate-800/60 px-4 pb-4 pt-3">
          {hrLoading ? (
            <div className="space-y-2 animate-pulse">
              <div className="h-24 bg-slate-800 rounded" />
              <div className="h-14 bg-slate-800 rounded" />
            </div>
          ) : hrData?.samples?.length > 0 ? (
            <WorkoutHRChart fixture={hrData} />
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
              {stats.map(({ label, value }) => (
                <div key={label} className="rounded-lg bg-slate-800/60 ring-1 ring-slate-800 px-3 py-2 text-center">
                  <div className="text-slate-200 text-[13px] font-semibold tabular-nums">{value}</div>
                  <div className="text-slate-500 text-[9.5px] uppercase tracking-wider mt-0.5">{label}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Skeleton() {
  return (
    <section className="animate-pulse">
      <div className="flex items-baseline justify-between mb-3 px-1">
        <div className="h-3.5 w-20 bg-slate-800 rounded" />
        <div className="h-2.5 w-16 bg-slate-800 rounded" />
      </div>
      <div className="space-y-2.5">
        {[...Array(2)].map((_, i) => (
          <div key={i} className="rounded-xl bg-slate-900/70 ring-1 ring-slate-800 overflow-hidden">
            <div className="flex items-center justify-between gap-3 px-4 py-3.5">
              <div className="flex items-center gap-3 min-w-0">
                <div className="shrink-0 w-8 h-8 rounded-lg bg-slate-800 ring-1 ring-slate-700/60" />
                <div className="space-y-1.5">
                  <div className="h-3 w-28 bg-slate-800 rounded" />
                  <div className="h-2 w-40 bg-slate-800 rounded" />
                </div>
              </div>
              <div className="w-3 h-3 rounded bg-slate-800 shrink-0" />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function WorkoutLog({ sessions, loading }) {
  if (loading) return <Skeleton />
  // null means loaded but no workouts → rest day
  // undefined (pre-load) already handled by loading flag above
  if (!sessions?.length) {
    return (
      <section>
        <h3 className="text-slate-200 text-sm font-semibold mb-3 px-1">Workouts</h3>
        <div className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 px-4 py-6 text-center text-slate-500 text-sm">
          Rest day
        </div>
      </section>
    )
  }

  const sorted = [...sessions].sort((a, b) => {
    const ta = new Date(a.start_time ?? a.start ?? 0).getTime()
    const tb = new Date(b.start_time ?? b.start ?? 0).getTime()
    return tb - ta
  })

  return (
    <section>
      <div className="flex items-baseline justify-between mb-3 px-1">
        <h3 className="text-slate-200 text-sm font-semibold">Workouts</h3>
        <span className="text-[10px] uppercase tracking-widest text-slate-500 font-mono">
          {sorted.length} session{sorted.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="space-y-2.5">
        {sorted.map((s, i) =>
          s.source === 'hevy'
            ? <HevySession key={s.id ?? i} session={s} />
            : <AppleSession key={s.id ?? i} session={s} />
        )}
      </div>
    </section>
  )
}
