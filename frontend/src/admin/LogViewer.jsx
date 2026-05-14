import { useState, useEffect, useRef, useCallback } from 'react'
import apiFetch from '../apiFetch'

const LEVEL_STYLE = {
  ERROR:   'text-red-400',
  WARNING: 'text-amber-400',
  WARN:    'text-amber-400',
  INFO:    'text-slate-400',
  DEBUG:   'text-slate-600',
}

const LINE_COUNTS = [100, 300, 500, 1000, 2000]

function parseLine(line) {
  // ISO timestamp prefix: "2026-05-13 21:08:14,748 [INFO] ..."
  const tsMatch  = line.match(/^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,.\d]*)/)
  const lvlMatch = line.match(/\[(ERROR|WARNING|WARN|INFO|DEBUG)\]/)
  return {
    ts:    tsMatch  ? tsMatch[1]  : null,
    level: lvlMatch ? lvlMatch[1] : null,
    body:  line,
  }
}

function LogLine({ entry }) {
  const { ts, level, body } = parseLine(entry.line)
  const lvlClass = level ? (LEVEL_STYLE[level] ?? 'text-slate-400') : 'text-slate-500'

  // Split into timestamp + rest for visual emphasis
  const rest = ts ? body.slice(ts.length) : body

  return (
    <div className="flex gap-2 py-[3px] hover:bg-slate-800/40 px-2 rounded group leading-5">
      <span className="text-slate-600 font-mono text-[11px] shrink-0 mt-px select-none w-[156px] truncate">
        {ts ?? ''}
      </span>
      <span className={`font-mono text-[11px] break-all ${lvlClass}`}>
        {ts ? rest : body}
      </span>
      <span className={`ml-auto shrink-0 text-[9px] font-mono opacity-0 group-hover:opacity-100 transition-opacity ${
        entry.stream === 'stderr' ? 'text-slate-600' : 'text-slate-700'
      }`}>
        {entry.stream}
      </span>
    </div>
  )
}

export default function LogViewer() {
  const [logs, setLogs]           = useState([])
  const [lines, setLines]         = useState(300)
  const [filter, setFilter]       = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const [lastFetched, setLastFetched] = useState(null)
  const [error, setError]         = useState(null)
  const fetchingRef = useRef(false)
  const bottomRef   = useRef(null)
  const containerRef = useRef(null)

  const fetchLogs = useCallback(() => {
    if (fetchingRef.current) return
    fetchingRef.current = true
    apiFetch(`/api/admin/logs?lines=${lines}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        setLogs(data)
        setLastFetched(new Date())
        setError(null)
      })
      .catch(err => setError(`Failed to load logs (${err})`))
      .finally(() => { fetchingRef.current = false })
  }, [lines])

  // Initial fetch + poll every 5s
  useEffect(() => {
    fetchLogs()
    const id = setInterval(fetchLogs, 5000)
    return () => clearInterval(id)
  }, [fetchLogs])

  // Auto-scroll to bottom
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const filtered = filter
    ? logs.filter(e => e.line.toLowerCase().includes(filter.toLowerCase()))
    : logs

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Header */}
      <div className="sticky top-0 z-20 border-b border-slate-800/60 backdrop-blur-md bg-slate-950/90">
        <div className="max-w-7xl mx-auto px-5 h-14 flex items-center gap-4">
          <div className="flex items-center gap-2 shrink-0">
            <div
              className="w-6 h-6 rounded-md grid place-items-center"
              style={{ background: 'linear-gradient(135deg, #e09a5e 0%, #b8662e 100%)' }}
            >
              <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="#1d1106" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="1,8 3.5,8 5,4.5 7,11.5 9,3 11,10.5 12.5,8 15,8" />
              </svg>
            </div>
            <span className="text-[13px] font-semibold text-slate-100">FitPulse</span>
            <span className="text-slate-700 text-sm">/</span>
            <span className="text-[12px] font-mono text-slate-400">admin</span>
            <span className="text-slate-700 text-sm">/</span>
            <span className="text-[12px] font-mono text-slate-300">logs</span>
          </div>

          {/* Live indicator */}
          <div className="flex items-center gap-1.5 ml-1">
            <span className={`w-1.5 h-1.5 rounded-full ${lastFetched ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400 animate-pulse'}`} />
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
              {lastFetched ? `Updated ${lastFetched.toLocaleTimeString()}` : 'Connecting…'}
            </span>
          </div>

          <div className="flex-1" />

          {/* Filter */}
          <input
            type="text"
            value={filter}
            onChange={e => setFilter(e.target.value)}
            placeholder="Filter logs…"
            className="h-7 px-3 rounded-lg bg-slate-900 ring-1 ring-slate-700 text-slate-200 text-[11px] font-mono placeholder:text-slate-600 focus:outline-none focus:ring-slate-500 w-48 transition"
          />

          {/* Lines selector */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="text-[10px] text-slate-600 font-mono uppercase tracking-wider">Lines</span>
            <div className="flex gap-0.5 bg-slate-900 ring-1 ring-slate-800 rounded-lg p-0.5">
              {LINE_COUNTS.map(n => (
                <button
                  key={n}
                  onClick={() => setLines(n)}
                  className={`px-2 py-1 rounded-md text-[10px] font-mono transition-colors ${
                    lines === n ? 'bg-slate-800 text-slate-200' : 'text-slate-600 hover:text-slate-300'
                  }`}
                >
                  {n >= 1000 ? `${n/1000}k` : n}
                </button>
              ))}
            </div>
          </div>

          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(a => !a)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono uppercase tracking-wider transition-colors ${
              autoScroll
                ? 'bg-emerald-500/10 text-emerald-400 ring-1 ring-emerald-500/20'
                : 'bg-slate-900 text-slate-500 ring-1 ring-slate-800 hover:text-slate-300'
            }`}
          >
            <svg viewBox="0 0 12 12" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M6 1v10M3 8l3 3 3-3" />
            </svg>
            Auto-scroll
          </button>

          {/* Refresh */}
          <button
            onClick={fetchLogs}
            className="w-7 h-7 rounded-lg bg-slate-900 ring-1 ring-slate-800 grid place-items-center text-slate-500 hover:text-slate-200 transition-colors"
            title="Refresh now"
          >
            <svg viewBox="0 0 12 12" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M10 4a4.5 4.5 0 1 0 .5 3M10 1v3H7" />
            </svg>
          </button>

          {/* Back */}
          <a
            href="/"
            className="w-7 h-7 rounded-lg bg-slate-900 ring-1 ring-slate-800 grid place-items-center text-slate-500 hover:text-slate-200 transition-colors"
            title="Back to dashboard"
          >
            <svg viewBox="0 0 12 12" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M7 2L3 6l4 4" />
            </svg>
          </a>
        </div>
      </div>

      {/* Log panel */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-5 py-4">
        {error ? (
          <div className="rounded-xl bg-red-500/10 ring-1 ring-red-500/20 px-4 py-3 text-red-400 text-sm font-mono">
            {error}
          </div>
        ) : (
          <div
            ref={containerRef}
            className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 overflow-hidden"
          >
            {/* Stats bar */}
            <div className="flex items-center gap-4 px-4 py-2 border-b border-slate-800/60">
              <span className="text-[10px] font-mono text-slate-600 uppercase tracking-wider">
                {filtered.length} {filter ? `of ${logs.length}` : ''} lines
              </span>
              {filter && (
                <button onClick={() => setFilter('')} className="text-[10px] font-mono text-slate-600 hover:text-amber-400 transition-colors">
                  × clear filter
                </button>
              )}
              <div className="flex-1" />
              {/* Level legend */}
              {['ERROR','WARNING','INFO','DEBUG'].map(l => (
                <span key={l} className={`text-[9px] font-mono uppercase tracking-wider ${LEVEL_STYLE[l] ?? 'text-slate-600'}`}>{l}</span>
              ))}
            </div>

            {/* Lines */}
            <div className="overflow-y-auto max-h-[calc(100vh-9rem)] py-2">
              {filtered.length === 0 && (
                <div className="px-4 py-8 text-center text-slate-600 text-sm font-mono">
                  {logs.length === 0 ? 'No log entries yet…' : 'No lines match your filter'}
                </div>
              )}
              {filtered.map((entry, i) => (
                <LogLine key={i} entry={entry} />
              ))}
              <div ref={bottomRef} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
