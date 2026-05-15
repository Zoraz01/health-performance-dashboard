import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts'
import { shortDate } from '../lib/formatters'
import { useChartColors } from '../lib/chartColors'
import { scoreColor } from '../lib/scoreColors'

const SCORE_ROWS = [
  { key: 'overall',          label: 'Overall'     },
  { key: 'training_quality', label: 'Training'    },
  { key: 'recovery',         label: 'Recovery'    },
  { key: 'volume_balance',   label: 'Balance'     },
  { key: 'consistency',      label: 'Consistency' },
]

function fullDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })
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
                <span className="inline-block w-1.5 h-1.5 rounded-full" style={{ backgroundColor: scoreColor(v).hex }} />
                <span className="text-slate-100 tabular-nums font-semibold">{v}</span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function ScoreChart({ history: historyProp }) {
  const c = useChartColors()
  const [fetched, setFetched] = useState(null)

  useEffect(() => {
    apiFetch('/api/scores?days=30')
      .then(r => r.ok ? r.json() : [])
      .then(data => setFetched(Array.isArray(data) && data.length ? data : []))
      .catch(() => setFetched([]))
  }, [])

  const isLoading = fetched === null
  const history   = fetched ?? historyProp ?? []
  const avg = history.length
    ? history.reduce((sum, d) => sum + d.overall, 0) / history.length
    : 0

  return (
    <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">30-Day Score Trend</h3>
          <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">
            Overall daily score · {history.length} days
          </p>
        </div>
        {history.length > 0 && (
          <div className="text-right">
            <div className="text-slate-500 text-[10px] uppercase tracking-widest">Avg</div>
            <div className="text-slate-200 text-lg font-semibold tabular-nums">{avg.toFixed(1)}</div>
          </div>
        )}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center" style={{ height: 200 }}>
          <div className="text-slate-700 text-[10px] font-mono uppercase tracking-widest animate-pulse">Loading…</div>
        </div>
      ) : !history.length ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 text-center gap-1.5" style={{ height: 200 }}>
          <div className="text-[9.5px] font-mono uppercase tracking-widest text-slate-600">No data yet</div>
          <div className="text-slate-700 text-[11px]">Scores appear after your first nightly analysis</div>
        </div>
      ) : (
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
                  <Cell key={i} fill={scoreColor(d.overall).hex} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="flex items-center justify-end gap-4 mt-3 text-[10px] uppercase tracking-wider text-slate-500">
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-emerald-400" />≥8</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-amber-400" />5–7</span>
        <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-sm bg-red-400" />≤4</span>
      </div>
    </section>
  )
}
