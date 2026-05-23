import { useState, useRef, useEffect, useCallback } from 'react'
import apiFetch from '../apiFetch'
import { formatDate, prettyKey } from '../lib/formatters'
import { scoreColor } from '../lib/scoreColors'

const SCORE_LABELS = {
  overall:          'Overall',
  training_quality: 'Training',
  recovery:         'Recovery',
  volume_balance:   'Balance',
  consistency:      'Consistency',
}

const SCORE_TIPS = {
  overall:          'Composite score across all four dimensions. A rough daily readiness index.',
  training_quality: 'Quality of your workout — intensity, volume relative to baseline, and effort consistency across sets. On rest days this score is excluded from the composite; the overall reflects recovery and consistency only.',
  recovery:         'How recovered your body is based on HRV and resting HR vs. your 30-day averages. Low HRV or elevated HR pulls this down.',
  volume_balance:   'How evenly training volume is distributed across muscle groups. Chronic neglect of push/pull or upper/lower balance lowers this.',
  consistency:      'Regularity of training and sleep over the past 7 days. Missing sessions or erratic sleep patterns reduce this score.',
}

const FATIGUE_STYLE = {
  recovered: 'bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30',
  working: 'bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30',
  fatigued: 'bg-orange-500/20 text-orange-300 ring-1 ring-orange-500/40',
  overtrained: 'bg-red-900/40 text-red-300 ring-1 ring-red-500/50',
}

function InfoIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 12 12" className={className} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round">
      <circle cx="6" cy="6" r="5" />
      <line x1="6" y1="5.5" x2="6" y2="8.5" />
      <circle cx="6" cy="3.5" r="0.5" fill="currentColor" stroke="none" />
    </svg>
  )
}

function ScoreBar({ label, score, tip, wide }) {
  const [open, setOpen] = useState(false)
  const { bar, text } = scoreColor(score)
  const pct = Math.max(4, (score / 10) * 100)
  return (
    <div className={wide ? 'col-span-2' : ''}>
      <div className="flex items-center justify-between mb-1.5 gap-1">
        <div className="flex items-center gap-1 relative">
          <span className="text-[11px] uppercase tracking-[0.14em] text-slate-400 font-medium">
            {label}
          </span>
          {tip && (
            <button
              onClick={() => setOpen(o => !o)}
              onMouseEnter={() => setOpen(true)}
              onMouseLeave={() => setOpen(false)}
              onFocus={() => setOpen(true)}
              onBlur={() => setOpen(false)}
              className="text-slate-600 hover:text-slate-400 transition-colors shrink-0 p-3 -m-3"
              tabIndex={0}
              aria-label={`What is ${label}?`}
            >
              <InfoIcon className="w-3 h-3" />
            </button>
          )}
          {open && tip && (
            <div className="absolute left-0 top-5 z-30 w-56 rounded-lg bg-slate-900 ring-1 ring-slate-700/80 px-3 py-2 pointer-events-none card-lg">
              <p className="text-[11px] text-slate-300 leading-relaxed">{tip}</p>
            </div>
          )}
        </div>
        <span className={`text-sm font-semibold tabular-nums ${text} shrink-0`}>
          {score}
          <span className="text-slate-500 text-xs font-normal">/10</span>
        </span>
      </div>
      <div className="h-1.5 w-full bg-slate-800/80 rounded-full overflow-hidden track-inset">
        <div
          className={`h-full ${bar} rounded-full transition-all duration-700 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function WarningIcon({ className = '' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 1.5L14.5 13.5H1.5L8 1.5Z" strokeLinejoin="round" />
      <line x1="8" y1="6" x2="8" y2="9.5" strokeLinecap="round" />
      <circle cx="8" cy="11.5" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  )
}

function ClaudeMark() {
  return (
    <div
      className="relative w-7 h-7 shrink-0"
      style={{ filter: 'drop-shadow(0 0 8px rgba(238,172,60,0.45))' }}
    >
      <div className="absolute inset-0 rounded-md bg-linear-to-br from-amber-300/90 to-orange-500/80" />
      <div className="absolute inset-0 grid place-items-center">
        <svg viewBox="0 0 16 16" className="w-4 h-4 text-slate-950" fill="currentColor">
          <path d="M8 1 L9.4 6.6 L15 8 L9.4 9.4 L8 15 L6.6 9.4 L1 8 L6.6 6.6 Z" />
        </svg>
      </div>
    </div>
  )
}

export default function ClaudeCard({ analysis, date, onAnalyzed, onPreCheckIn }) {
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState(null)
  const [localAnalysis, setLocalAnalysis] = useState(null)
  const pollRef = useRef(null)
  const deadlineRef = useRef(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  useEffect(() => stopPolling, [stopPolling])

  const startPolling = useCallback(() => {
    if (pollRef.current) return
    deadlineRef.current = Date.now() + 5 * 60 * 1000 // 5 min max

    pollRef.current = setInterval(async () => {
      if (Date.now() > deadlineRef.current) {
        stopPolling()
        setAnalyzing(false)
        setAnalyzeError('Analysis is taking longer than expected — it may still complete. Refresh to check.')
        return
      }
      try {
        const r = await apiFetch('/api/data/record', { cache: 'no-store' })
        if (!r.ok) return
        const data = await r.json()
        const rec = data.record
        if (rec?.analysis?.scores?.overall != null) {
          stopPolling()
          setLocalAnalysis({
            ...rec.analysis,
            date: rec.date,
            muscle_fatigue: rec.workouts?.muscle_fatigue,
          })
          setAnalyzing(false)
          onAnalyzed?.()
        }
      } catch {
        // network blip — keep polling
      }
    }, 3000)
  }, [stopPolling, onAnalyzed])

  const runAnalysis = async () => {
    setAnalyzing(true)
    setAnalyzeError(null)
    try {
      const r = await apiFetch(`/api/analyze/${date}`, { method: 'POST' })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        // 5xx / gateway errors — analysis may still run on the backend; poll for it
        if (r.status >= 500) {
          startPolling()
          return
        }
        throw new Error(body.detail ?? `Server error ${r.status}`)
      }
      const data = await r.json()
      if (data.analysis) {
        // Sync path: analysis returned immediately in the response
        setLocalAnalysis({ ...data.analysis, date: data.date })
        setAnalyzing(false)
        onAnalyzed?.()
      } else {
        // Async path: backend queued it — poll until it appears
        startPolling()
      }
    } catch {
      // Network error (Cloudflare dropped, etc.) — analysis may still run; poll
      startPolling()
    }
  }

  const handleAnalyzeClick = async () => {
    if (!date || analyzing) return
    try {
      const r = await apiFetch(`/api/checkin/today?date=${date}`)
      const data = r.ok ? await r.json() : null
      if (!data?.checked_in && onPreCheckIn) {
        onPreCheckIn(date, runAnalysis)
        return
      }
    } catch {
      // check-in fetch failed — proceed with analysis anyway
    }
    runAnalysis()
  }

  const effectiveAnalysis = localAnalysis || analysis

  if (!effectiveAnalysis || effectiveAnalysis.scores?.overall == null) {
    return (
      <section
        aria-busy="true"
        className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-6 sm:p-7 card-lg"
        style={{ minHeight: 540 }}
      >
        <div className="flex items-center gap-3 mb-6">
          <div className="w-7 h-7 rounded-md bg-slate-800/80" />
          <div className="space-y-2">
            <div className="h-3 w-28 bg-slate-800/80 rounded" />
            <div className="h-2 w-20 bg-slate-800/60 rounded" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-x-5 gap-y-4 mb-6">
          <div className="col-span-2">
            <div className="h-2 w-16 bg-slate-800/60 rounded mb-2" />
            <div className="h-1.5 w-full bg-slate-800/80 rounded-full" />
          </div>
          {[0, 1, 2, 3].map((i) => (
            <div key={i}>
              <div className="h-2 w-14 bg-slate-800/60 rounded mb-2" />
              <div className="h-1.5 w-full bg-slate-800/80 rounded-full" />
            </div>
          ))}
        </div>
        <div className="rounded-lg border border-dashed border-slate-700/70 bg-slate-900/40 px-5 py-8 text-center">
          <p className="text-slate-400 text-sm leading-relaxed max-w-sm mx-auto">
            Yesterday's debrief runs at <span className="text-slate-200 font-medium">3am</span> — after
            the final Hevy sync and Apple Health data is complete.
          </p>
          <p className="text-slate-600 text-xs mt-3 font-mono uppercase tracking-wider">
            no analysis yet · runs nightly at 3am
          </p>
          <div className="mt-5 flex flex-col items-center gap-2">
            <button
              onClick={handleAnalyzeClick}
              disabled={analyzing || !date}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 text-[12px] font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {analyzing ? (
                <>
                  <span className="w-3 h-3 rounded-full border-2 border-amber-300/30 border-t-amber-300 animate-spin" />
                  {pollRef.current ? 'Waiting for analysis…' : 'Starting…'}
                </>
              ) : (
                'Run Analysis Now'
              )}
            </button>
            {analyzeError && (
              <p className="text-red-400 text-[11px] max-w-xs text-center">{analyzeError}</p>
            )}
          </div>
        </div>
      </section>
    )
  }

  const s = effectiveAnalysis.scores
  const fatigueOrder = ['fatigued', 'working', 'recovered', 'overtrained']
  const muscles = Object.entries(effectiveAnalysis.muscle_fatigue || {}).sort(
    (a, b) => fatigueOrder.indexOf(a[1]) - fatigueOrder.indexOf(b[1])
  )

  return (
    <section className="rounded-2xl bg-linear-to-b from-slate-900/90 to-slate-900/60 ring-1 ring-slate-800 p-6 sm:p-7 card-lg">
      <header className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <ClaudeMark />
          <div className="leading-tight">
            <div className="text-[11px] uppercase tracking-[0.18em] text-amber-300/80 font-semibold">
              Daily Debrief
            </div>
            <div className="text-slate-200 text-base font-medium">
              {formatDate(effectiveAnalysis.date || date)}
            </div>
          </div>
        </div>
        <div className="hidden sm:flex items-center gap-2 text-[10px] uppercase tracking-widest text-slate-500 font-mono">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          {effectiveAnalysis.date && effectiveAnalysis.date !== date
            ? `for ${formatDate(effectiveAnalysis.date)}`
            : 'updated nightly'}
        </div>
      </header>

      <div className="grid grid-cols-2 gap-x-6 gap-y-5 mb-7">
        <ScoreBar label={SCORE_LABELS.overall}          score={s.overall}          tip={SCORE_TIPS.overall}          wide />
        <ScoreBar label={SCORE_LABELS.training_quality} score={s.training_quality} tip={SCORE_TIPS.training_quality} />
        <ScoreBar label={SCORE_LABELS.recovery}         score={s.recovery}         tip={SCORE_TIPS.recovery}         />
        <ScoreBar label={SCORE_LABELS.volume_balance}   score={s.volume_balance}   tip={SCORE_TIPS.volume_balance}   />
        <ScoreBar label={SCORE_LABELS.consistency}      score={s.consistency}      tip={SCORE_TIPS.consistency}      />
      </div>

      <p className="text-[13.5px] leading-relaxed text-slate-300 mb-6">
        {effectiveAnalysis.summary}
      </p>

      {effectiveAnalysis.critique && effectiveAnalysis.critique.length > 0 && (
        <div className="mb-6">
          <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500 font-semibold mb-3">
            Watch list
          </div>
          <ul className="space-y-2">
            {effectiveAnalysis.critique.map((c, i) => (
              <li key={i} className="flex items-start gap-2.5 text-[13px] text-slate-300 leading-relaxed">
                <WarningIcon className="w-3.5 h-3.5 mt-1 text-amber-400 shrink-0" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {effectiveAnalysis.callout && (
        <blockquote className="relative rounded-lg bg-amber-500/6 border-l-2 border-amber-400 pl-4 pr-4 py-3.5 mb-6">
          <p className="text-[14px] leading-relaxed text-slate-100 font-medium">
            {effectiveAnalysis.callout}
          </p>
        </blockquote>
      )}

      {muscles.length > 0 && (
        <div>
          <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500 font-semibold mb-3">
            Muscle fatigue
          </div>
          <div className="flex flex-wrap gap-1.5">
            {muscles.map(([name, state]) => (
              <span
                key={name}
                title={state}
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium capitalize whitespace-nowrap ${
                  FATIGUE_STYLE[state] || FATIGUE_STYLE.recovered
                }`}
              >
                <span className="w-1 h-1 rounded-full bg-current opacity-80" />
                {prettyKey(name)}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
