import { useState, useEffect, useRef, useCallback } from 'react'
import apiFetch from '../apiFetch'
import { useTheme } from '../ThemeContext'

const LEVEL_STYLE = {
  ERROR:   'text-red-400',
  WARNING: 'text-amber-400',
  WARN:    'text-amber-400',
  INFO:    'text-sky-400',
  DEBUG:   'text-slate-500',
}

const LINE_COUNTS = [100, 300, 500, 1000, 2000]

function parseLine(line) {
  // ISO timestamp: "2026-05-13 21:08:14,748 [INFO] ..."
  const tsMatch  = line.match(/^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})[,.\d]*/)
  const lvlMatch = line.match(/\[(ERROR|WARNING|WARN|INFO|DEBUG)\]/)
  const fullTs   = tsMatch ? `${tsMatch[1]} ${tsMatch[2]}` : null
  const shortTs  = tsMatch ? tsMatch[2] : null
  const rawLen   = tsMatch ? tsMatch[0].length : 0
  return {
    fullTs,
    shortTs,
    level: lvlMatch ? lvlMatch[1] : null,
    body:  rawLen > 0 ? line.slice(rawLen).trimStart() : line,
  }
}

function LogLine({ entry, isDark }) {
  const { fullTs, shortTs, level, body } = parseLine(entry.line)
  const lvlClass   = level ? (LEVEL_STYLE[level] ?? 'text-slate-400') : 'text-slate-500'
  const hoverBg    = isDark ? 'hover:bg-slate-800/40' : 'hover:bg-slate-100'
  const tsColor    = isDark ? 'text-slate-400' : 'text-slate-500'
  const tsDash     = isDark ? 'text-slate-700' : 'text-slate-300'
  const divider    = isDark ? 'border-slate-800' : 'border-slate-200'
  const streamCls  = entry.stream === 'stderr'
    ? (isDark ? 'text-slate-600' : 'text-slate-400')
    : (isDark ? 'text-slate-700' : 'text-slate-300')

  return (
    <div className={`flex gap-0 py-[3px] ${hoverBg} rounded group leading-5 min-w-0`}>
      {/* Timestamp column */}
      <div
        className={`shrink-0 w-[76px] flex items-start pr-3 border-r ${divider} mr-3`}
        title={fullTs ?? ''}
      >
        {shortTs ? (
          <span className={`${tsColor} font-mono text-[11px] tabular-nums select-none`}>
            {shortTs}
          </span>
        ) : (
          <span className={`${tsDash} font-mono text-[11px] select-none`}>—</span>
        )}
      </div>

      {/* Body */}
      <span className={`font-mono text-[11px] break-all flex-1 min-w-0 ${lvlClass}`}>
        {body}
      </span>

      {/* Stream badge on hover */}
      <span className={`ml-2 shrink-0 text-[9px] font-mono opacity-0 group-hover:opacity-100 transition-opacity mt-px ${streamCls}`}>
        {entry.stream}
      </span>
    </div>
  )
}

export default function LogViewer() {
  const { isDark, toggle }            = useTheme()
  const [logs, setLogs]               = useState([])
  const [lines, setLines]             = useState(300)
  const [filter, setFilter]           = useState('')
  const [autoScroll, setAutoScroll]   = useState(true)
  const [lastFetched, setLastFetched] = useState(null)
  const [error, setError]             = useState(null)
  const fetchingRef  = useRef(false)
  const bottomRef    = useRef(null)
  const containerRef = useRef(null)
  const toggleBtnRef = useRef(null)

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

  useEffect(() => {
    fetchLogs()
    const id = setInterval(fetchLogs, 5000)
    return () => clearInterval(id)
  }, [fetchLogs])

  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const filtered = filter
    ? logs.filter(e => e.line.toLowerCase().includes(filter.toLowerCase()))
    : logs

  // Theme-derived classes
  const bg         = isDark ? 'bg-slate-950'       : 'bg-slate-100'
  const text       = isDark ? 'text-slate-100'      : 'text-slate-900'
  const headerBg   = isDark ? 'bg-slate-950/90'     : 'bg-white/90'
  const border     = isDark ? 'border-slate-800/60' : 'border-slate-200'
  const panelBg    = isDark ? 'bg-slate-900/60'     : 'bg-white'
  const panelRing  = isDark ? 'ring-slate-800'      : 'ring-slate-200'
  const inputCls   = isDark
    ? 'bg-slate-900 ring-slate-700 text-slate-200 placeholder:text-slate-600'
    : 'bg-white ring-slate-300 text-slate-800 placeholder:text-slate-400'
  const btnBase    = isDark
    ? 'bg-slate-900 ring-slate-800 text-slate-500 hover:text-slate-200'
    : 'bg-white ring-slate-200 text-slate-400 hover:text-slate-700'
  const linesSel   = isDark ? 'bg-slate-900 ring-slate-800' : 'bg-white ring-slate-200'
  const linesOn    = isDark ? 'bg-slate-800 text-slate-200' : 'bg-slate-100 text-slate-800'
  const linesOff   = isDark ? 'text-slate-600 hover:text-slate-300' : 'text-slate-400 hover:text-slate-600'
  const dimText    = isDark ? 'text-slate-600' : 'text-slate-400'
  const subText    = isDark ? 'text-slate-500' : 'text-slate-400'
  const slash      = isDark ? 'text-slate-700' : 'text-slate-300'

  return (
    <div className={`min-h-screen ${bg} ${text} flex flex-col`}>

      {/* ── Header ── */}
      <div className={`sticky top-0 z-20 border-b ${border} backdrop-blur-md ${headerBg}`}>
        <div className="max-w-7xl mx-auto px-5 h-14 flex items-center gap-3">

          {/* Breadcrumb */}
          <div className="flex items-center gap-2 shrink-0">
            <div
              className="w-6 h-6 rounded-md grid place-items-center shrink-0"
              style={{ background: 'linear-gradient(135deg, #e09a5e 0%, #b8662e 100%)' }}
            >
              <svg viewBox="0 0 16 16" className="w-3.5 h-3.5" fill="none" stroke="#1d1106" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="1,8 3.5,8 5,4.5 7,11.5 9,3 11,10.5 12.5,8 15,8" />
              </svg>
            </div>
            <span className={`text-[13px] font-semibold ${text}`}>FitPulse</span>
            <span className={`text-sm ${slash}`}>/</span>
            <span className={`text-[12px] font-mono ${subText}`}>admin</span>
            <span className={`text-sm ${slash}`}>/</span>
            <span className={`text-[12px] font-mono ${isDark ? 'text-slate-300' : 'text-slate-700'}`}>logs</span>
          </div>

          {/* Live indicator */}
          <div className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${lastFetched ? 'bg-emerald-400' : 'bg-amber-400'}`} />
            <span className={`text-[10px] font-mono ${subText} uppercase tracking-wider`}>
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
            className={`h-7 px-3 rounded-lg ring-1 text-[11px] font-mono focus:outline-none w-44 transition ${inputCls}`}
          />

          {/* Lines selector */}
          <div className="flex items-center gap-1.5 shrink-0">
            <span className={`text-[10px] ${dimText} font-mono uppercase tracking-wider`}>Lines</span>
            <div className={`flex gap-0.5 ${linesSel} ring-1 rounded-lg p-0.5`}>
              {LINE_COUNTS.map(n => (
                <button
                  key={n}
                  onClick={() => setLines(n)}
                  className={`px-2 py-1 rounded-md text-[10px] font-mono transition-colors ${lines === n ? linesOn : linesOff}`}
                >
                  {n >= 1000 ? `${n/1000}k` : n}
                </button>
              ))}
            </div>
          </div>

          {/* Auto-scroll */}
          <button
            onClick={() => setAutoScroll(a => !a)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-mono uppercase tracking-wider ring-1 transition-colors ${
              autoScroll
                ? 'bg-emerald-500/10 text-emerald-400 ring-emerald-500/20'
                : `${btnBase}`
            }`}
          >
            <svg viewBox="0 0 12 12" className="w-2.5 h-2.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M6 1v10M3 8l3 3 3-3" />
            </svg>
            Scroll
          </button>

          {/* Theme toggle — sun (dark mode) / moon (light mode) */}
          <button
            ref={toggleBtnRef}
            onClick={() => toggle(toggleBtnRef.current)}
            className={`w-7 h-7 rounded-lg ring-1 grid place-items-center transition-colors ${btnBase}`}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {isDark ? (
              <svg viewBox="0 0 12 12" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <circle cx="6" cy="6" r="2.2" />
                <path d="M6 1v1M6 10v1M1 6h1M10 6h1M2.5 2.5l.7.7M8.8 8.8l.7.7M2.5 9.5l.7-.7M8.8 3.2l.7-.7" />
              </svg>
            ) : (
              <svg viewBox="0 0 12 12" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M10 6.5A4.5 4.5 0 0 1 5.5 2a4.5 4.5 0 1 0 4.5 4.5z" />
              </svg>
            )}
          </button>

          {/* Refresh */}
          <button
            onClick={fetchLogs}
            className={`w-7 h-7 rounded-lg ring-1 grid place-items-center transition-colors ${btnBase}`}
            title="Refresh now"
          >
            <svg viewBox="0 0 12 12" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M10 4a4.5 4.5 0 1 0 .5 3M10 1v3H7" />
            </svg>
          </button>

          {/* Back to dashboard */}
          <a
            href="/"
            className={`w-7 h-7 rounded-lg ring-1 grid place-items-center transition-colors ${btnBase}`}
            title="Back to dashboard"
          >
            <svg viewBox="0 0 12 12" className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
              <path d="M7 2L3 6l4 4" />
            </svg>
          </a>
        </div>
      </div>

      {/* ── Log panel ── */}
      <div className="flex-1 max-w-7xl mx-auto w-full px-5 py-4">
        {error ? (
          <div className="rounded-xl bg-red-500/10 ring-1 ring-red-500/20 px-4 py-3 text-red-400 text-sm font-mono">
            {error}
          </div>
        ) : (
          <div ref={containerRef} className={`rounded-2xl ${panelBg} ring-1 ${panelRing} overflow-hidden`}>

            {/* Stats bar */}
            <div className={`flex items-center gap-4 px-4 py-2 border-b ${border}`}>
              <span className={`text-[10px] font-mono ${dimText} uppercase tracking-wider`}>
                {filtered.length}{filter ? ` of ${logs.length}` : ''} lines
              </span>
              {filter && (
                <button onClick={() => setFilter('')} className={`text-[10px] font-mono ${dimText} hover:text-amber-400 transition-colors`}>
                  × clear
                </button>
              )}
              <div className="flex-1" />
              {['ERROR', 'WARNING', 'INFO', 'DEBUG'].map(l => (
                <span key={l} className={`text-[9px] font-mono uppercase tracking-wider ${LEVEL_STYLE[l] ?? dimText}`}>{l}</span>
              ))}
            </div>

            {/* Log lines */}
            <div className="overflow-y-auto max-h-[calc(100vh-9rem)] py-2 px-2">
              {filtered.length === 0 && (
                <div className={`px-4 py-8 text-center ${dimText} text-sm font-mono`}>
                  {logs.length === 0 ? 'No log entries yet…' : 'No lines match your filter'}
                </div>
              )}
              {filtered.map((entry, i) => (
                <LogLine key={i} entry={entry} isDark={isDark} />
              ))}
              <div ref={bottomRef} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
