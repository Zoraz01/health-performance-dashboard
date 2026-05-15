import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { shortDate } from '../lib/formatters'
import { useChartColors } from '../lib/chartColors'

const TABS = [
  { key: 'steps',           label: 'Steps',      unit: '',     color: '#38bdf8', fmt: v => Math.round(v).toLocaleString() },
  { key: 'active_calories', label: 'Calories',   unit: 'kcal', color: '#fb923c', fmt: v => `${Math.round(v)}` },
  { key: 'hrv_ms',          label: 'HRV',        unit: 'ms',   color: '#a78bfa', fmt: v => v.toFixed(1) },
  { key: 'resting_hr',      label: 'Resting HR', unit: 'bpm',  color: '#f43f5e', fmt: v => Math.round(v).toString() },
  { key: 'body_weight_lbs', label: 'Weight',     unit: 'lbs',  color: '#34d399', fmt: v => v.toFixed(1) },
]

function ChartTooltip({ active, payload, tab }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2 text-xs shadow-xl">
      <div className="text-slate-400 mb-1 font-mono">{shortDate(d.date)}</div>
      <div className="font-semibold" style={{ color: tab.color }}>
        {tab.fmt(d[tab.key])} <span className="font-normal text-slate-500">{tab.unit}</span>
      </div>
    </div>
  )
}

export default function ActivityCharts({ history: historyProp }) {
  const c = useChartColors()
  const [fetched, setFetched] = useState(null)
  const [activeKey, setActiveKey] = useState(TABS[0].key)

  useEffect(() => {
    apiFetch('/api/activity?days=7')
      .then(r => r.ok ? r.json() : [])
      .then(data => setFetched(Array.isArray(data) && data.length ? data : []))
      .catch(() => setFetched([]))
  }, [])

  const isLoading = fetched === null
  const history   = fetched ?? historyProp ?? []
  const tab = TABS.find(t => t.key === activeKey)

  const latest = history[history.length - 1]?.[activeKey]
  const prev   = history[history.length - 2]?.[activeKey]
  const delta  = latest != null && prev != null ? latest - prev : null

  return (
    <section className="rounded-2xl bg-slate-900/60 ring-1 ring-slate-800 p-5 sm:p-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h3 className="text-slate-200 text-sm font-semibold">Activity Trends</h3>
          <p className="text-slate-500 text-[11px] mt-0.5 uppercase tracking-wider">7-day window · {history.length} days with data</p>
        </div>
        {latest != null && (
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-widest text-slate-500">{tab.label}</div>
            <div className="text-base font-semibold tabular-nums" style={{ color: tab.color }}>
              {tab.fmt(latest)} <span className="text-slate-500 text-xs font-normal">{tab.unit}</span>
            </div>
            {delta != null && (
              <div className={`text-[10px] font-mono ${delta >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {delta >= 0 ? '+' : ''}{tab.fmt(delta)} vs prev
              </div>
            )}
          </div>
        )}
      </div>

      <div className="overflow-x-auto scrollbar-hide mb-5">
        <div className="inline-flex bg-slate-950/60 ring-1 ring-slate-800 rounded-lg p-0.5 gap-0.5">
          {TABS.map(t => (
            <button
              key={t.key}
              onClick={() => setActiveKey(t.key)}
              className={
                'px-3 py-1 rounded-md text-[10.5px] font-semibold transition-colors whitespace-nowrap ' +
                (activeKey === t.key ? 'bg-slate-800 text-slate-100' : 'text-slate-500 hover:text-slate-300')
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center" style={{ height: 200 }}>
          <div className="text-slate-700 text-[10px] font-mono uppercase tracking-widest animate-pulse">Loading…</div>
        </div>
      ) : !history.length ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-800 text-center gap-1.5" style={{ height: 200 }}>
          <div className="text-[9.5px] font-mono uppercase tracking-widest text-slate-600">No data yet</div>
          <div className="text-slate-700 text-[11px]">Data will appear here as it accumulates</div>
        </div>
      ) : (
        <div style={{ width: '100%', height: 200 }}>
          <ResponsiveContainer>
            <LineChart data={history} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke={c.grid} />
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
                domain={['auto', 'auto']}
                stroke={c.axis}
                tick={{ fill: c.tick, fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <Tooltip
                content={(props) => <ChartTooltip {...props} tab={tab} />}
                cursor={{ stroke: '#334155', strokeWidth: 1 }}
              />
              <Line
                key={activeKey}
                type="monotone"
                dataKey={activeKey}
                stroke={tab.color}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: tab.color, stroke: c.bg, strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  )
}
