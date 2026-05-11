import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts'
import { useTheme } from '../ThemeContext'

const SCORE_HISTORY_FIXTURE = [
  { date: '2026-04-08', overall: 6, training_quality: 7, recovery: 6, volume_balance: 5, consistency: 6 },
  { date: '2026-04-09', overall: 7, training_quality: 8, recovery: 7, volume_balance: 6, consistency: 7 },
  { date: '2026-04-11', overall: 5, training_quality: 6, recovery: 4, volume_balance: 5, consistency: 6 },
  { date: '2026-04-13', overall: 8, training_quality: 9, recovery: 8, volume_balance: 7, consistency: 8 },
  { date: '2026-04-14', overall: 6, training_quality: 6, recovery: 5, volume_balance: 6, consistency: 7 },
  { date: '2026-04-16', overall: 7, training_quality: 8, recovery: 7, volume_balance: 6, consistency: 7 },
  { date: '2026-04-18', overall: 9, training_quality: 9, recovery: 9, volume_balance: 8, consistency: 9 },
  { date: '2026-04-19', overall: 7, training_quality: 7, recovery: 6, volume_balance: 7, consistency: 8 },
  { date: '2026-04-21', overall: 6, training_quality: 7, recovery: 5, volume_balance: 5, consistency: 7 },
  { date: '2026-04-23', overall: 8, training_quality: 8, recovery: 8, volume_balance: 7, consistency: 8 },
  { date: '2026-04-25', overall: 7, training_quality: 8, recovery: 6, volume_balance: 7, consistency: 8 },
  { date: '2026-04-27', overall: 5, training_quality: 6, recovery: 4, volume_balance: 6, consistency: 6 },
  { date: '2026-04-28', overall: 8, training_quality: 9, recovery: 7, volume_balance: 8, consistency: 9 },
  { date: '2026-04-30', overall: 6, training_quality: 7, recovery: 5, volume_balance: 5, consistency: 7 },
  { date: '2026-05-02', overall: 8, training_quality: 9, recovery: 8, volume_balance: 7, consistency: 8 },
  { date: '2026-05-03', overall: 7, training_quality: 8, recovery: 5, volume_balance: 6, consistency: 8 },
]

const SCORE_ROWS = [
  { key: 'overall',          label: 'Overall'     },
  { key: 'training_quality', label: 'Training'    },
  { key: 'recovery',         label: 'Recovery'    },
  { key: 'volume_balance',   label: 'Balance'     },
  { key: 'consistency',      label: 'Consistency' },
]

function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' })
}

function fullDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
}

function barColor(score) {
  if (score >= 8) return '#34d399'
  if (score >= 5) return '#fbbf24'
  return '#f87171'
}

function ScoreTooltip({ active, payload }) {
  if (!active || !payload || !payload.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 shadow-xl px-3.5 py-3 text-xs min-w-[180px]">
      <div className="text-slate-300 font-medium mb-2 text-[12px]">{fullDate(d.date)}</div>
      <div className="space-y-1.5">
        {SCORE_ROWS.map((row) => {
          const v = d[row.key]
          return (
            <div key={row.key} className="flex items-center justify-between gap-4">
              <span className="text-slate-400">{row.label}</span>
              <span className="flex items-center gap-2">
                <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: barColor(v) }} />
                <span className="text-slate-100 tabular-nums font-semibold">{v}</span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const CHART_COLORS = {
  dark:  { axis: 'rgb(84,122,132)',  tick: 'rgb(84,122,132)',  grid: 'rgb(20,50,60)',   ref: 'rgb(56,92,102)'  },
  light: { axis: 'rgb(118,102,82)', tick: 'rgb(118,102,82)', grid: 'rgb(178,160,136)', ref: 'rgb(118,102,82)' },
}

export default function ScoreChart({ history: historyProp }) {
  const { isDark } = useTheme()
  const c = isDark ? CHART_COLORS.dark : CHART_COLORS.light
  const [fetched, setFetched] = useState(null)

  useEffect(() => {
    apiFetch('/api/scores?days=30')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (Array.isArray(data) && data.length) setFetched(data) })
      .catch(() => {})
  }, [])

  const history = fetched ?? historyProp ?? SCORE_HISTORY_FIXTURE
  const avg = history.reduce((sum, d) => sum + d.overall, 0) / Math.max(1, history.length)

  return (
    <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">30-Day Score Trend</h3>
          <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">
            Overall daily score · {history.length} days
          </p>
        </div>
        <div className="text-right">
          <div className="text-slate-500 text-[10px] uppercase tracking-widest">Avg</div>
          <div className="text-slate-200 text-lg font-semibold tabular-nums">{avg.toFixed(1)}</div>
        </div>
      </div>

      <div style={{ width: '100%', height: 200 }}>
        <ResponsiveContainer>
          <BarChart data={history} margin={{ top: 8, right: 8, left: -20, bottom: 0 }} barCategoryGap="20%">
            <XAxis
              dataKey="date"
              tickFormatter={shortDate}
              stroke={c.axis}
              tick={{ fill: c.tick, fontSize: 10 }}
              tickLine={false}
              axisLine={{ stroke: c.grid }}
              interval="preserveStartEnd"
              minTickGap={20}
            />
            <YAxis
              domain={[0, 10]}
              ticks={[0, 5, 10]}
              stroke={c.axis}
              tick={{ fill: c.tick, fontSize: 10 }}
              tickLine={false}
              axisLine={false}
              width={32}
            />
            <ReferenceLine y={avg} stroke={c.ref} strokeDasharray="3 3" strokeWidth={1} />
            <Tooltip cursor={{ fill: 'rgba(148,163,184,0.06)' }} content={<ScoreTooltip />} />
            <Bar dataKey="overall" radius={[3, 3, 0, 0]}>
              {history.map((d, i) => (
                <Cell key={i} fill={barColor(d.overall)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="flex items-center justify-end gap-4 mt-3 text-[10px] uppercase tracking-wider text-slate-500">
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-emerald-400" />≥8</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-amber-400" />5–7</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-red-400" />≤4</span>
      </div>
    </section>
  )
}
