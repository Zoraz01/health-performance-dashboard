import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import { prettyKey } from '../lib/formatters'

const MUSCLES = [
  'chest', 'shoulders', 'triceps', 'lats', 'upper_back',
  'biceps', 'forearms', 'quadriceps', 'hamstrings', 'glutes',
  'calves', 'abdominals', 'lower_back', 'traps',
]

const SCALE = ['None', 'Mild', 'Noticeable', 'Moderate', 'Significant', 'Severe']

function levelColor(v) {
  if (v === 0) return 'text-slate-400'
  if (v <= 1)  return 'text-emerald-400'
  if (v <= 2)  return 'text-amber-400'
  if (v <= 3)  return 'text-orange-400'
  return 'text-red-400'
}

function levelBg(v) {
  if (v === 0) return 'bg-slate-800/60 text-slate-400'
  if (v <= 1)  return 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20'
  if (v <= 2)  return 'bg-amber-500/10 text-amber-400 ring-1 ring-amber-500/20'
  if (v <= 3)  return 'bg-orange-500/10 text-orange-400 ring-1 ring-orange-500/20'
  return 'bg-red-500/10 text-red-400 ring-1 ring-red-500/20'
}

function MuscleSliders({ soreness, onChange }) {
  return (
    <div className="grid sm:grid-cols-2 gap-x-6 gap-y-4">
      {MUSCLES.map(m => (
        <div key={m}>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-slate-200 text-xs font-medium">{prettyKey(m)}</span>
            <span className={`text-[11px] font-semibold tabular-nums font-mono ${levelColor(soreness[m])}`}>
              {soreness[m]} · {SCALE[soreness[m]]}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={5}
            step={1}
            value={soreness[m]}
            onChange={e => onChange(prev => ({ ...prev, [m]: +e.target.value }))}
            className="soreness-slider w-full h-1.5 rounded-full appearance-none cursor-pointer accent-amber-400"
          />
        </div>
      ))}
    </div>
  )
}

function NoteField({ value, onChange }) {
  return (
    <div className="mt-5">
      <label className="block text-[10.5px] uppercase tracking-widest text-slate-400 font-semibold mb-2">
        Context &amp; Notes
      </label>
      <textarea
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder="e.g. hungover, barely slept, stressed at work, tight hip from yesterday…"
        rows={3}
        className="w-full rounded-xl bg-slate-800 ring-1 ring-slate-500 px-3.5 py-2.5 text-slate-200 text-sm placeholder:text-slate-500 resize-none focus:outline-none focus:ring-2 focus:ring-slate-400 transition"
      />
      <p className="text-[10.5px] text-slate-400 mt-1">This goes directly into tomorrow's Claude analysis.</p>
    </div>
  )
}

function ScaleLegend() {
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] font-mono mb-5">
      {SCALE.map((s, i) => (
        <span key={i} className={levelColor(i)}>{i} — {s}</span>
      ))}
    </div>
  )
}

function CheckedInView({ logged, date, onClose }) {
  const soreness = logged.soreness ?? logged
  const note     = logged.note ?? null
  const nonZero  = Object.entries(soreness).filter(([, v]) => v > 0)
  const allClear = nonZero.length === 0

  return (
    <div className="p-5 sm:p-6">
      <div className="flex items-center gap-3 mb-5">
        <div className="w-9 h-9 rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/25 grid place-items-center shrink-0">
          <svg viewBox="0 0 14 14" className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2.5 7.5l3 3 6-6" />
          </svg>
        </div>
        <div>
          <div className="text-slate-200 text-sm font-semibold">Logged for today</div>
          <div className="text-slate-400 text-[11px] mt-0.5 uppercase tracking-wider font-mono">{date}</div>
        </div>
      </div>

      {allClear ? (
        <p className="text-slate-400 text-[13px]">No soreness reported — everything feeling good today.</p>
      ) : (
        <>
          <div className="text-[10.5px] uppercase tracking-widest text-slate-400 font-semibold mb-3">Soreness</div>
          <div className="flex flex-wrap gap-2">
            {nonZero.map(([muscle, val]) => (
              <span key={muscle} className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11.5px] font-medium ${levelBg(val)}`}>
                {prettyKey(muscle)}
                <span className="font-mono font-bold">{val}</span>
              </span>
            ))}
          </div>
        </>
      )}

      {note && (
        <div className="mt-4 pt-4 border-t border-slate-800">
          <div className="text-[10.5px] uppercase tracking-widest text-slate-500 font-semibold mb-1.5">Notes</div>
          <p className="text-slate-300 text-[13px] leading-relaxed">{note}</p>
        </div>
      )}

      <p className="text-slate-500 text-[11px] mt-4 font-mono uppercase tracking-wider">
        Come back tomorrow to log again
      </p>

      {onClose && (
        <button
          onClick={onClose}
          className="mt-5 w-full py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 text-sm font-semibold transition-colors"
        >
          Done
        </button>
      )}
    </div>
  )
}

export default function SorenessCheckIn({ inline = false, forceOpen = false, onClose }) {
  const [submitted, setSubmitted]   = useState(null)
  const [loading, setLoading]       = useState(true)
  const [open, setOpen]             = useState(false)
  const [today, setToday]           = useState('')
  const [soreness, setSoreness]     = useState(() =>
    Object.fromEntries(MUSCLES.map(m => [m, 0]))
  )
  const [note, setNote]         = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)

  useEffect(() => {
    apiFetch('/api/checkin/today')
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data?.date) setToday(data.date)
        if (data?.checked_in) {
          setSubmitted({ soreness: data.soreness, note: data.note })
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const isOpen     = open || forceOpen
  const closeModal = () => { setOpen(false); onClose?.() }

  const handleSubmit = async () => {
    if (!today || submitting) return
    setSubmitting(true)
    setSubmitError(null)
    const payload = { date: today, soreness, note: note.trim() }
    try {
      const r = await apiFetch('/api/checkin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) {
        const body = await r.json().catch(() => ({}))
        setSubmitError(body.detail ?? 'Failed to save. Please try again.')
        return
      }
      setSubmitted({ soreness, note: note.trim() })
      closeModal()
    } catch {
      setSubmitError('Failed to save. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  // Inline / Check-in tab
  if (inline) {
    if (loading) return (
      <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6 animate-pulse">
        <div className="h-3 w-40 bg-slate-800 rounded mb-2" />
        <div className="h-2 w-24 bg-slate-800/60 rounded" />
      </section>
    )
    if (submitted) return (
      <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800">
        <CheckedInView logged={submitted} date={today || '—'} />
      </section>
    )
    return (
      <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6">
        <div className="flex items-baseline justify-between mb-4">
          <div>
            <h3 className="text-slate-200 text-sm font-semibold">Daily Soreness Check-in</h3>
            <p className="text-slate-400 text-[11px] mt-0.5 uppercase tracking-wider">Rate 0–5 per muscle group</p>
          </div>
        </div>
        <ScaleLegend />
        <MuscleSliders soreness={soreness} onChange={setSoreness} />
        <NoteField value={note} onChange={setNote} />
        {submitError && (
          <p className="mt-3 text-red-400 text-[12px]">{submitError}</p>
        )}
        <button
          onClick={handleSubmit}
          className="mt-6 w-full py-2.5 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-100 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          disabled={!today || submitting}
        >
          {submitting ? 'Saving…' : 'Submit Check-in'}
        </button>
      </section>
    )
  }

  // Banner mode — hide once checked in (modal still accessible via forceOpen)
  return (
    <>
      {!loading && !submitted && (
        <div className="checkin-banner px-5 py-2.5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <span className="checkin-banner-dot w-1.5 h-1.5 rounded-full shrink-0 animate-pulse" />
            <span className="checkin-banner-text text-sm font-medium">Rate your muscle soreness for today</span>
          </div>
          <button
            onClick={() => setOpen(true)}
            className="checkin-banner-btn px-3 py-1 rounded-lg text-xs font-semibold shrink-0"
          >
            Check in
          </button>
        </div>
      )}

      {isOpen && (
        <div className={`fixed inset-0 z-50 flex justify-center p-4 ${
          submitted ? 'items-center' : 'items-end sm:items-center'
        }`}>
          <div className="absolute inset-0 bg-slate-950/75 backdrop-blur-sm" onClick={closeModal} />
          <div className={`relative z-10 w-full max-w-lg flex flex-col bg-slate-900 ring-1 ring-slate-700 shadow-2xl ${
            submitted
              ? 'rounded-2xl'
              : 'max-h-[85vh] rounded-t-2xl sm:rounded-2xl'
          }`}>
            {/* Header — hidden when submitted (Done button replaces it) */}
            {!submitted && (
              <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800 shrink-0">
                <div>
                  <h2 className="text-slate-100 text-sm font-semibold">Daily Soreness Check-in</h2>
                  <p className="text-slate-500 text-[10.5px] mt-0.5 uppercase tracking-wider">Rate 0–5 per muscle group</p>
                </div>
                <button onClick={closeModal} className="w-10 h-10 rounded-full bg-slate-800 hover:bg-slate-700 grid place-items-center transition-colors">
                  <svg viewBox="0 0 12 12" className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                    <path d="M2 2l8 8M10 2l-8 8" />
                  </svg>
                </button>
              </div>
            )}

            <div className={`${
              submitted ? '' : 'flex-1 min-h-0 overflow-y-auto'
            } px-5 py-4 pb-6`} style={submitted ? undefined : { WebkitOverflowScrolling: 'touch' }}>
              {loading ? (
                <div className="space-y-4 animate-pulse py-2">
                  {[48, 64, 48, 64, 48].map((w, i) => (
                    <div key={i} className="h-2.5 bg-slate-800 rounded" style={{ width: `${w}%` }} />
                  ))}
                </div>
              ) : submitted ? (
                <CheckedInView logged={submitted} date={today} onClose={closeModal} />
              ) : (
                <>
                  <ScaleLegend />
                  <MuscleSliders soreness={soreness} onChange={setSoreness} />
                  <NoteField value={note} onChange={setNote} />
                  {submitError && (
                    <p className="mt-3 text-red-400 text-[12px]">{submitError}</p>
                  )}
                  <button
                    onClick={handleSubmit}
                    disabled={!today || submitting}
                    className="mt-6 w-full py-3 rounded-xl bg-slate-700 hover:bg-slate-600 text-slate-100 text-sm font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {submitting ? 'Saving…' : 'Submit Check-in'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
