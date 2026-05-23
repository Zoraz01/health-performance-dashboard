import { useMemo } from 'react'

const VW      = 600
const LABEL_W = 44
const CHART_W = VW - LABEL_W
const ROW_H   = 40
const MARKER_H = 18
const AXIS_H  = 20

const STAGE_ORDER = ['awake', 'rem', 'core', 'deep']
const STAGE_CFG = {
  awake: { label: 'Awake', fill: '#fbbf24', bg: 'rgba(251,191,36,0.08)'  },
  rem:   { label: 'REM',   fill: '#a78bfa', bg: 'rgba(167,139,250,0.08)' },
  core:  { label: 'Core',  fill: '#38bdf8', bg: 'rgba(56,189,248,0.08)'  },
  deep:  { label: 'Deep',  fill: '#818cf8', bg: 'rgba(129,140,248,0.08)' },
}

const SOURCE_LABEL = {
  ring:         'RingConn',
  watch:        'Apple Watch',
  'watch+ring': 'Watch + Ring',
}

function fmt(mins) {
  if (mins == null) return '—'
  const h = Math.floor(mins / 60)
  const m = Math.round(mins % 60)
  return `${h}h ${m}m`
}

function fmtTime(iso) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
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

function SourceBadge({ source }) {
  const label = SOURCE_LABEL[source] ?? 'Apple Health'
  return <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">{label}</p>
}

function Hypnogram({ stages: stagesJson, hr: hrJson }) {
  const segments = useMemo(() => {
    try { return JSON.parse(stagesJson) } catch { return [] }
  }, [stagesJson])

  const hrPoints = useMemo(() => {
    try { return JSON.parse(hrJson) } catch { return [] }
  }, [hrJson])

  const presentStages = useMemo(
    () => STAGE_ORDER.filter(s => segments.some(seg => seg.stage === s)),
    [segments]
  )

  const { chartStart, chartEnd, totalMs } = useMemo(() => {
    if (!segments.length) return { chartStart: 0, chartEnd: 1, totalMs: 1 }
    const sleepStart = new Date(segments[0].start).getTime()
    const sleepEnd   = new Date(segments[segments.length - 1].end).getTime()
    const chartStart = sleepStart - 30 * 60 * 1000
    const chartEnd   = sleepEnd   + 30 * 60 * 1000
    return { chartStart, chartEnd, totalMs: chartEnd - chartStart }
  }, [segments])

  const toX = (ms) => LABEL_W + ((ms - chartStart) / totalMs) * CHART_W

  const chartAreaH = presentStages.length * ROW_H
  const svgH = MARKER_H + chartAreaH + AXIS_H

  const hourMarks = useMemo(() => {
    const marks = []
    const first = new Date(chartStart)
    first.setMinutes(0, 0, 0)
    if (first.getTime() <= chartStart) first.setHours(first.getHours() + 1)
    let t = first.getTime()
    while (t < chartEnd) { marks.push(t); t += 3600000 }
    return marks
  }, [chartStart, chartEnd])

  const hrBounds = useMemo(() => {
    if (!hrPoints.length) return null
    const hrs = hrPoints.map(p => p.hr)
    const hrMin = Math.min(...hrs) - 2
    const hrMax = Math.max(...hrs) + 2
    return { hrMin, hrMax, hrMid: Math.round((hrMin + hrMax) / 2) }
  }, [hrPoints])

  const hrLine = useMemo(() => {
    if (!hrPoints.length || !hrBounds) return ''
    const { hrMin, hrMax } = hrBounds
    return hrPoints.map(p => {
      const x = toX(new Date(p.t).getTime())
      const y = MARKER_H + ((hrMax - p.hr) / (hrMax - hrMin)) * chartAreaH
      return `${x},${y}`
    }).join(' ')
  }, [hrPoints, hrBounds, chartStart, totalMs, chartAreaH])

  if (!segments.length) return null

  const sleepStartMs = new Date(segments[0].start).getTime()
  const sleepEndMs   = new Date(segments[segments.length - 1].end).getTime()
  const sleepStartX  = toX(sleepStartMs)
  const sleepEndX    = toX(sleepEndMs)

  return (
    <svg viewBox={`0 0 ${VW} ${svgH}`} width="100%" style={{ display: 'block', overflow: 'visible' }}>
      {/* Row backgrounds */}
      {presentStages.map((stage, i) => (
        <rect
          key={`bg-${stage}`}
          x={LABEL_W} y={MARKER_H + i * ROW_H}
          width={CHART_W} height={ROW_H}
          fill={STAGE_CFG[stage].bg}
        />
      ))}

      {/* Row dividers */}
      {presentStages.slice(1).map((_, i) => (
        <line
          key={`div-${i}`}
          x1={LABEL_W} y1={MARKER_H + (i + 1) * ROW_H}
          x2={VW}      y2={MARKER_H + (i + 1) * ROW_H}
          stroke="#1e293b" strokeWidth={0.5}
        />
      ))}

      {/* Stage labels */}
      {presentStages.map((stage, i) => (
        <text
          key={`lbl-${stage}`}
          x={LABEL_W - 6} y={MARKER_H + i * ROW_H + ROW_H / 2 + 4}
          textAnchor="end" fontSize="11" fill="#64748b" fontFamily="ui-monospace,monospace"
        >
          {STAGE_CFG[stage].label}
        </text>
      ))}

      {/* Segment blocks */}
      {segments.map((seg, idx) => {
        const stageIdx = presentStages.indexOf(seg.stage)
        if (stageIdx === -1) return null
        const x = toX(new Date(seg.start).getTime())
        const w = Math.max(
          ((new Date(seg.end).getTime() - new Date(seg.start).getTime()) / totalMs) * CHART_W,
          2
        )
        return (
          <rect
            key={idx}
            x={x} y={MARKER_H + stageIdx * ROW_H + 3}
            width={w} height={ROW_H - 6} rx={3}
            fill={STAGE_CFG[seg.stage].fill}
          />
        )
      })}

      {/* Dashed vertical markers at sleep start/end */}
      <line
        x1={sleepStartX} y1={MARKER_H} x2={sleepStartX} y2={MARKER_H + chartAreaH}
        stroke="#94a3b8" strokeWidth={1} strokeDasharray="3,2" opacity={0.4}
      />
      <line
        x1={sleepEndX} y1={MARKER_H} x2={sleepEndX} y2={MARKER_H + chartAreaH}
        stroke="#94a3b8" strokeWidth={1} strokeDasharray="3,2" opacity={0.4}
      />

      {/* Sleep start/end time labels in MARKER_H strip */}
      <text x={sleepStartX} y={MARKER_H - 3} textAnchor="middle" fontSize="9" fill="#94a3b8">
        {fmtTime(segments[0].start)}
      </text>
      <text x={sleepEndX} y={MARKER_H - 3} textAnchor="middle" fontSize="9" fill="#94a3b8">
        {fmtTime(segments[segments.length - 1].end)}
      </text>

      {/* X-axis baseline */}
      <line
        x1={LABEL_W} y1={MARKER_H + chartAreaH}
        x2={VW}      y2={MARKER_H + chartAreaH}
        stroke="#1e293b" strokeWidth={0.5}
      />

      {/* Hour marks + labels */}
      {hourMarks.map(t => {
        const x = toX(t)
        const label = new Date(t).toLocaleTimeString('en-US', { hour: 'numeric', hour12: true })
        return (
          <g key={t}>
            <line
              x1={x} y1={MARKER_H + chartAreaH}
              x2={x} y2={MARKER_H + chartAreaH + 3}
              stroke="#1e293b" strokeWidth={0.5}
            />
            <text
              x={x} y={MARKER_H + chartAreaH + AXIS_H - 2}
              textAnchor="middle" fontSize="8.5" fill="#475569"
            >
              {label}
            </text>
          </g>
        )
      })}

      {/* HR line + scale */}
      {hrLine && hrBounds && (() => {
        const { hrMin, hrMax, hrMid } = hrBounds
        const levels = [
          { bpm: Math.round(hrMax - 2), y: MARKER_H },
          { bpm: hrMid,                  y: MARKER_H + chartAreaH / 2 },
          { bpm: Math.round(hrMin + 2), y: MARKER_H + chartAreaH },
        ]
        return (
          <g>
            {levels.map(({ bpm, y }) => (
              <g key={bpm}>
                <line
                  x1={LABEL_W} y1={y} x2={VW} y2={y}
                  stroke="#fb923c" strokeWidth={0.5} strokeDasharray="2,5" opacity={0.18}
                />
                <text
                  x={VW + 4} y={y + 3.5}
                  textAnchor="start" fontSize="8.5" fill="#fb923c"
                  opacity={0.75} fontFamily="ui-monospace,monospace"
                >
                  {bpm}
                </text>
              </g>
            ))}
            <text
              x={VW + 4} y={MARKER_H - 5}
              textAnchor="start" fontSize="7.5" fill="#fb923c"
              opacity={0.45} fontFamily="ui-monospace,monospace"
            >
              bpm
            </text>
            <polyline
              points={hrLine}
              stroke="#fb923c" strokeWidth={1.5}
              fill="none" strokeLinejoin="round" opacity={0.9}
            />
          </g>
        )
      })()}
    </svg>
  )
}

export default function SleepCard({ data }) {
  const hasData = data?.total != null

  if (!hasData) {
    return (
      <section className="relative rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6 overflow-hidden card-lg">
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
            <div className="h-full bg-sky-500/20"    style={{ width: '40%' }} />
            <div className="h-full bg-amber-500/20"  style={{ width: '10%' }} />
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

  const hasStages = !!data.stages

  const barPct = (mins) => total > 0 ? `${Math.round((mins / total) * 100)}%` : '0%'

  return (
    <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6 card-lg">
      <div className="flex items-baseline justify-between mb-1">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">Sleep last night</h3>
          <SourceBadge source={data.source} />
        </div>
        <div className="text-right">
          <div className="text-slate-500 text-[10px] uppercase tracking-widest">Total</div>
          <div className="text-slate-200 text-2xl font-semibold tabular-nums">{fmt(total)}</div>
        </div>
      </div>

      {hasStages ? (
        <div className="mt-3">
          <Hypnogram stages={data.stages} hr={data.hr} />
        </div>
      ) : (
        <div className="mt-4 relative h-3 rounded-full bg-slate-800/80 overflow-hidden flex">
          <div className="h-full bg-indigo-500" style={{ width: barPct(deep)  }} />
          <div className="h-full bg-violet-500" style={{ width: barPct(rem)   }} />
          <div className="h-full bg-sky-500"    style={{ width: barPct(core)  }} />
          <div className="h-full bg-amber-500"  style={{ width: barPct(awake) }} />
        </div>
      )}

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-0">
        <SleepStageRow label="Deep"  value={fmt(deep)}  color="bg-indigo-500/70" />
        <SleepStageRow label="REM"   value={fmt(rem)}   color="bg-violet-500/70" />
        <SleepStageRow label="Core"  value={fmt(core)}  color="bg-sky-500/70"    />
        <SleepStageRow label="Awake" value={fmt(awake)} color="bg-amber-500/70"  />
      </div>
    </section>
  )
}
