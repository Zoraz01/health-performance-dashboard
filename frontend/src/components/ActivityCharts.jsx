import { useState, useEffect } from 'react'
import apiFetch from '../apiFetch'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'
import { useTheme } from '../ThemeContext'

const ACTIVITY_FIXTURE = [
  { date: '2026-05-04', steps: 4800,  active_calories: 220, hrv_ms: 27.1, body_weight_lbs: 135.4, resting_hr: 68, cardio_recovery: 18.4 },
  { date: '2026-05-05', steps: 9100,  active_calories: 490, hrv_ms: 33.8, body_weight_lbs: 135.1, resting_hr: 60, cardio_recovery: 23.9 },
  { date: '2026-05-06', steps: 6400,  active_calories: 340, hrv_ms: 35.0, body_weight_lbs: 135.0, resting_hr: 62, cardio_recovery: 22.6 },
  { date: '2026-05-07', steps: 13200, active_calories: 720, hrv_ms: 44.6, body_weight_lbs: 135.0, resting_hr: 55, cardio_recovery: 26.2 },
  { date: '2026-05-08', steps: 7100,  active_calories: 350, hrv_ms: 37.2, body_weight_lbs: 134.9, resting_hr: 59, cardio_recovery: 23.5 },
  { date: '2026-05-09', steps: 7366,  active_calories: 381, hrv_ms: 31.4, body_weight_lbs: 135.0, resting_hr: 63, cardio_recovery: 21.7 },
  { date: '2026-05-10', steps: 5200,  active_calories: 260, hrv_ms: 28.9, body_weight_lbs: 135.2, resting_hr: 67, cardio_recovery: 18.9 },
]

const TABS = [
  { key: 'steps',           label: 'Steps',      unit: '',     color: '#38bdf8', fmt: v => Math.round(v).toLocaleString() },
  { key: 'active_calories', label: 'Calories',   unit: 'kcal', color: '#fb923c', fmt: v => `${Math.round(v)}` },
  { key: 'hrv_ms',          label: 'HRV',        unit: 'ms',   color: '#a78bfa', fmt: v => v.toFixed(1) },
  { key: 'resting_hr',      label: 'Resting HR', unit: 'bpm',  color: '#f43f5e', fmt: v => Math.round(v).toString() },
  { key: 'cardio_recovery', label: 'Recovery',   unit: 'bpm',  color: '#2dd4bf', fmt: v => v.toFixed(1) },
  { key: 'body_weight_lbs', label: 'Weight',     unit: 'lbs',  color: '#34d399', fmt: v => v.toFixed(1) },
]

function shortDate(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' })
}

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

const CHART_COLORS = {
  dark:  { axis: 'rgb(84,122,132)',  tick: 'rgb(84,122,132)',  grid: 'rgb(20,50,60)',    bg: 'rgb(6,24,29)'   },
  light: { axis: 'rgb(118,102,82)', tick: 'rgb(118,102,82)', grid: 'rgb(178,160,136)', bg: 'rgb(252,247,238)' },
}

export default function ActivityCharts({ history: historyProp }) {
  const { isDark } = useTheme()
  const c = isDark ? CHART_COLORS.dark : CHART_COLORS.light
  const [fetched, setFetched] = useState(null)
  const [activeKey, setActiveKey] = useState(TABS[0].key)

  useEffect(() => {
    apiFetch('/api/activity?days=7')
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (Array.isArray(data) && data.length) setFetched(data) })
      .catch(() => {})
  }, [])

  const history = fetched ?? historyProp ?? ACTIVITY_FIXTURE
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
    </section>
  )
}
