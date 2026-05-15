/**
 * Trend cards for the Trends tab — all wired to live API endpoints.
 * Shows a loading skeleton while fetching and an empty state until data accumulates.
 *
 * Exports:
 *   SleepTrend       — nightly sleep stage breakdown  → /api/snapshots
 *   VolumeTrend      — per-session training volume     → /api/snapshots
 *   AllScoresTrend   — all 5 score dimensions          → /api/scores
 *   ActivityMixTrend — exercise minutes + stand hours  → /api/snapshots
 */

import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import {
  BarChart, Bar, LineChart, Line,
  ComposedChart,
  XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, Cell,
} from 'recharts'
import { shortDate } from '../lib/formatters'
import { useChartColors } from '../lib/chartColors'
import { SCORE_DIMENSION_ROWS } from '../lib/scoreColors'

// ── Shared empty / loading states ─────────────────────────────────────────────

function EmptyChart({ height = 180 }) {
  return (
    <div
      style={{ height }}
      className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 text-center gap-1.5"
    >
      <div className="text-[9.5px] font-mono uppercase tracking-widest text-slate-600">No data yet</div>
      <div className="text-slate-700 text-[11px]">Data will appear here as it accumulates</div>
    </div>
  )
}

function LoadingChart({ height = 180 }) {
  return (
    <div style={{ height }} className="flex items-center justify-center">
      <div className="text-slate-700 text-[10px] font-mono uppercase tracking-widest animate-pulse">Loading…</div>
    </div>
  )
}

// ── Card shell ────────────────────────────────────────────────────────────────

function CardShell({ title, sub, children, note }) {
  return (
    <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6">
      <div className="flex items-start justify-between mb-5">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">{title}</h3>
          <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">{sub}</p>
        </div>
        {note && (
          <span className="text-[9.5px] font-mono text-slate-600 uppercase tracking-wider px-2 py-0.5 rounded bg-slate-800/60 shrink-0">
            {note}
          </span>
        )}
      </div>
      {children}
    </section>
  )
}

// ── Live data hooks ───────────────────────────────────────────────────────────
// null  = fetch in flight
// []    = fetch completed, no data
// [...] = has rows

function dateRange(days) {
  const to   = new Date()
  const from = new Date(Date.now() - days * 86_400_000)
  return {
    from: from.toISOString().slice(0, 10),
    to:   to.toISOString().slice(0, 10),
  }
}

function useSnapshots(days = 30) {
  const [data, setData] = useState(null)
  useEffect(() => {
    const { from, to } = dateRange(days)
    apiFetch(`/api/snapshots?from=${from}&to=${to}`)
      .then(r => r.ok ? r.json() : [])
      .then(rows => setData(rows))
      .catch(() => setData([]))
  }, [days])
  return data
}

function useScores(days = 30) {
  const [data, setData] = useState(null)
  useEffect(() => {
    apiFetch(`/api/scores?days=${days}`)
      .then(r => r.ok ? r.json() : [])
      .then(rows => setData(rows))
      .catch(() => setData([]))
  }, [days])
  return data
}

// ── Sleep Breakdown ───────────────────────────────────────────────────────────

function SleepTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const total = d.deep + d.rem + d.core + d.awake
  const fmt = m => `${Math.floor(m / 60)}h ${m % 60}m`
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2.5 text-xs shadow-xl space-y-1">
      <div className="text-slate-400 font-mono mb-1">{shortDate(d.date)}</div>
      <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-indigo-400 inline-block" /> <span className="text-slate-300">Deep {fmt(d.deep)}</span></div>
      <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-violet-400 inline-block" /> <span className="text-slate-300">REM {fmt(d.rem)}</span></div>
      <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-sky-400 inline-block" />    <span className="text-slate-300">Core {fmt(d.core)}</span></div>
      <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-amber-400 inline-block" /> <span className="text-slate-300">Awake {fmt(d.awake)}</span></div>
      <div className="border-t border-slate-700 pt-1 mt-1 text-slate-400">Total {fmt(total)}</div>
    </div>
  )
}

export function SleepTrend() {
  const c = useChartColors()
  const snapshots = useSnapshots()

  const chartData = snapshots
    ?.filter(s => s.sleep_total_min != null)
    .map(s => {
      const total = s.sleep_total_min
      const deep  = s.sleep_deep_min  ?? 0
      const rem   = s.sleep_rem_min   ?? 0
      const awake = s.sleep_awake_min ?? 0
      const core  = Math.max(0, total - deep - rem - awake)
      return { date: s.date, deep, rem, core, awake, total }
    }) ?? null

  const avgTotal = chartData?.length
    ? Math.round(chartData.reduce((s, d) => s + d.total, 0) / chartData.length)
    : null
  const fmtH = m => `${Math.floor(m / 60)}h ${m % 60}m`

  return (
    <CardShell title="Sleep Breakdown" sub="30-night stage analysis" note="/api/snapshots">
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-3 flex-wrap">
          {[
            { label: 'Deep',  color: 'bg-indigo-400' },
            { label: 'REM',   color: 'bg-violet-400' },
            { label: 'Core',  color: 'bg-sky-400'    },
            { label: 'Awake', color: 'bg-amber-400'  },
          ].map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
              <span className={`w-2 h-2 rounded-sm ${color}`} />{label}
            </span>
          ))}
        </div>
        {avgTotal != null && (
          <div className="text-right shrink-0">
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Avg</div>
            <div className="text-slate-200 text-sm font-semibold tabular-nums">{fmtH(avgTotal)}</div>
          </div>
        )}
      </div>

      {snapshots === null ? (
        <LoadingChart />
      ) : !chartData?.length ? (
        <EmptyChart />
      ) : (
        <div style={{ width: '100%', height: 180 }}>
          <ResponsiveContainer>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }} barCategoryGap="18%">
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={{ stroke: c.grid }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis tickFormatter={m => `${Math.round(m / 60)}h`} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={false} width={28} />
              <Tooltip content={<SleepTooltip />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
              <Bar dataKey="deep"  stackId="s" fill="#818cf8" radius={[0,0,0,0]} />
              <Bar dataKey="rem"   stackId="s" fill="#a78bfa" />
              <Bar dataKey="core"  stackId="s" fill="#38bdf8" />
              <Bar dataKey="awake" stackId="s" fill="#fbbf24" radius={[3,3,0,0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </CardShell>
  )
}

// ── Training Volume ───────────────────────────────────────────────────────────

function VolumeTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2 text-xs shadow-xl">
      <div className="text-slate-400 font-mono mb-1">{shortDate(d.date)}</div>
      <div className="text-amber-300 font-semibold">{d.name}</div>
      <div className="text-slate-300 mt-0.5">{Math.round(d.volume).toLocaleString()} <span className="text-slate-500">kg</span></div>
    </div>
  )
}

function volColor(v) {
  if (v >= 5000) return '#34d399'
  if (v >= 4000) return '#fbbf24'
  return '#fb923c'
}

export function VolumeTrend() {
  const c = useChartColors()
  const snapshots = useSnapshots()

  const chartData = snapshots
    ?.filter(s => s.muscle_volume && Object.keys(s.muscle_volume).length > 0)
    .map(s => ({
      date:   s.date,
      volume: Math.round(Object.values(s.muscle_volume).reduce((a, v) => a + v, 0)),
      name:   s.workouts?.[0]?.title ?? 'Workout',
    })) ?? null

  const max = chartData?.length ? Math.max(...chartData.map(d => d.volume)) : 0
  const avg = chartData?.length
    ? Math.round(chartData.reduce((s, d) => s + d.volume, 0) / chartData.length)
    : null

  return (
    <CardShell
      title="Training Volume"
      sub={chartData?.length ? `${chartData.length} session${chartData.length !== 1 ? 's' : ''} · hevy` : 'hevy workouts'}
      note="/api/snapshots"
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-3">
          {[['bg-emerald-400', '≥5000 kg'], ['bg-amber-400', '4–5k'], ['bg-orange-400', '< 4k']].map(([bg, l]) => (
            <span key={l} className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
              <span className={`w-2 h-2 rounded-sm ${bg}`} />{l}
            </span>
          ))}
        </div>
        {avg != null && (
          <div className="text-right shrink-0">
            <div className="text-[10px] uppercase tracking-widest text-slate-500">Avg</div>
            <div className="text-slate-200 text-sm font-semibold tabular-nums">
              {avg.toLocaleString()} <span className="text-slate-500 text-xs font-normal">kg</span>
            </div>
          </div>
        )}
      </div>

      {snapshots === null ? (
        <LoadingChart />
      ) : !chartData?.length ? (
        <EmptyChart />
      ) : (
        <div style={{ width: '100%', height: 180 }}>
          <ResponsiveContainer>
            <BarChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }} barCategoryGap="25%">
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={{ stroke: c.grid }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis tickFormatter={v => `${Math.round(v / 1000)}k`} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={false} width={28} domain={[0, Math.ceil(max / 1000) * 1000]} />
              <Tooltip content={<VolumeTooltip />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
              <Bar dataKey="volume" radius={[3, 3, 0, 0]}>
                {chartData.map((d, i) => <Cell key={i} fill={volColor(d.volume)} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </CardShell>
  )
}

// ── Score Breakdown ───────────────────────────────────────────────────────────

const SCORE_LINES = SCORE_DIMENSION_ROWS

function ScoreTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2.5 text-xs shadow-xl space-y-1.5">
      <div className="text-slate-400 font-mono mb-1">{shortDate(d.date)}</div>
      {SCORE_LINES.map(({ key, label, color }) => (
        <div key={key} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5" style={{ color }}>
            <span className="w-1.5 h-1.5 rounded-full bg-current" />{label}
          </span>
          <span className="text-slate-100 tabular-nums font-semibold">{d[key]}</span>
        </div>
      ))}
    </div>
  )
}

export function AllScoresTrend() {
  const c = useChartColors()
  const liveScores = useScores()

  // API returns training_quality / volume_balance; chart keys are training / balance
  const chartData = liveScores?.map(d => ({
    date:        d.date,
    overall:     d.overall,
    training:    d.training_quality,
    recovery:    d.recovery,
    balance:     d.volume_balance,
    consistency: d.consistency,
  })) ?? null

  return (
    <CardShell title="Score Breakdown" sub="All dimensions · 30 days" note="/api/scores">
      <div className="flex flex-wrap gap-3 mb-4">
        {SCORE_LINES.map(({ key, label, color }) => (
          <span key={key} className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
            <span className="w-2 h-1.5 rounded-sm inline-block" style={{ background: color }} />{label}
          </span>
        ))}
      </div>

      {liveScores === null ? (
        <LoadingChart height={200} />
      ) : !chartData?.length ? (
        <EmptyChart height={200} />
      ) : (
        <div style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={{ stroke: c.grid }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis domain={[0, 10]} ticks={[0, 5, 10]} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={false} width={24} />
              <Tooltip content={<ScoreTooltip />} cursor={{ stroke: c.axis, strokeWidth: 1 }} />
              {SCORE_LINES.map(({ key, color }) => (
                <Line key={key} type="monotone" dataKey={key} stroke={color}
                  strokeWidth={key === 'overall' ? 2.5 : 1.5}
                  dot={false} activeDot={{ r: 3, fill: color, stroke: c.bg, strokeWidth: 2 }}
                  opacity={key === 'overall' ? 1 : 0.7}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </CardShell>
  )
}

// ── Active Time ───────────────────────────────────────────────────────────────

function MixTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2.5 text-xs shadow-xl space-y-1">
      <div className="text-slate-400 font-mono mb-1">{shortDate(d.date)}</div>
      <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-sm bg-sky-400 inline-block" />
        <span className="text-slate-300">{d.exercise_min} <span className="text-slate-500">active min</span></span></div>
      <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" />
        <span className="text-slate-300">{d.stand_hrs} <span className="text-slate-500">stand hrs</span></span></div>
    </div>
  )
}

export function ActivityMixTrend() {
  const c = useChartColors()
  const snapshots = useSnapshots()

  const chartData = snapshots
    ?.filter(s => s.exercise_minutes != null || s.stand_hours != null)
    .map(s => ({
      date:         s.date,
      exercise_min: Math.round(s.exercise_minutes ?? 0),
      stand_hrs:    s.stand_hours ?? 0,
    })) ?? null

  const avgMin = chartData?.length
    ? Math.round(chartData.reduce((s, d) => s + d.exercise_min, 0) / chartData.length)
    : null
  const avgHrs = chartData?.length
    ? (chartData.reduce((s, d) => s + d.stand_hrs, 0) / chartData.length).toFixed(1)
    : null

  return (
    <CardShell title="Active Time" sub="Exercise minutes · stand hours" note="/api/snapshots">
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-4">
          <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
            <span className="w-2 h-2 rounded-sm bg-sky-400" />Exercise min
          </span>
          <span className="flex items-center gap-1.5 text-[10.5px] text-slate-400">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />Stand hrs
          </span>
        </div>
        {avgMin != null && (
          <div className="flex gap-4 shrink-0 text-right">
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Avg min</div>
              <div className="text-slate-200 text-sm font-semibold tabular-nums">{avgMin}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500">Avg hrs</div>
              <div className="text-slate-200 text-sm font-semibold tabular-nums">{avgHrs}</div>
            </div>
          </div>
        )}
      </div>

      {snapshots === null ? (
        <LoadingChart />
      ) : !chartData?.length ? (
        <EmptyChart />
      ) : (
        <div style={{ width: '100%', height: 180 }}>
          <ResponsiveContainer>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.grid} />
              <XAxis dataKey="date" tickFormatter={shortDate} stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={{ stroke: c.grid }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis yAxisId="min" stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false} axisLine={false} width={28} />
              <YAxis yAxisId="hrs" orientation="right" domain={[0, 16]} ticks={[0, 8, 16]}
                stroke={c.axis} tick={{ fill: c.tick, fontSize: 10 }} tickLine={false} axisLine={false} width={24} />
              <Tooltip content={<MixTooltip />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
              <Bar yAxisId="min" dataKey="exercise_min" fill="#38bdf8" fillOpacity={0.7} radius={[3, 3, 0, 0]} barCategoryGap="20%" />
              <Line yAxisId="hrs" type="monotone" dataKey="stand_hrs" stroke="#34d399" strokeWidth={2}
                dot={false} activeDot={{ r: 3, fill: '#34d399', stroke: c.bg, strokeWidth: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </CardShell>
  )
}
