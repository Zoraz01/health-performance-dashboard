import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts'

const HR_FIXTURE = {
  workout_id: 'CB6E7107-492B-4E73-92E6-807F2E95D796',
  workout_name: 'Basketball',
  duration_min: 10.6,
  samples: [
    { ts: '2026-05-08 18:17:50-04:00', hr_avg: 155.8, hr_min: 152, hr_max: 158, calories: 7.7,  steps: null  },
    { ts: '2026-05-08 18:18:50-04:00', hr_avg: 160.4, hr_min: 159, hr_max: 162, calories: 9.1,  steps: null  },
    { ts: '2026-05-08 18:19:50-04:00', hr_avg: 158.5, hr_min: 147, hr_max: 165, calories: 9.3,  steps: null  },
    { ts: '2026-05-08 18:20:50-04:00', hr_avg: 152.8, hr_min: 144, hr_max: 160, calories: 8.4,  steps: null  },
    { ts: '2026-05-08 18:21:50-04:00', hr_avg: 161.7, hr_min: 160, hr_max: 164, calories: 9.2,  steps: null  },
    { ts: '2026-05-08 18:22:50-04:00', hr_avg: 156.4, hr_min: 151, hr_max: 162, calories: 8.9,  steps: null  },
    { ts: '2026-05-08 18:23:50-04:00', hr_avg: 150.3, hr_min: 148, hr_max: 154, calories: 8.4,  steps: null  },
    { ts: '2026-05-08 18:24:50-04:00', hr_avg: 148.7, hr_min: 147, hr_max: 152, calories: 8.2,  steps: 61.4  },
    { ts: '2026-05-08 18:25:50-04:00', hr_avg: 147.1, hr_min: 145, hr_max: 149, calories: 8.1,  steps: 62.6  },
    { ts: '2026-05-08 18:26:50-04:00', hr_avg: 151.4, hr_min: 149, hr_max: 156, calories: 8.5,  steps: 62.6  },
    { ts: '2026-05-08 18:27:50-04:00', hr_avg: 146.3, hr_min: 142, hr_max: 150, calories: 5.0,  steps: 4.3   },
  ],
}

function fmtTime(ts) {
  const match = ts.match(/(\d{2}:\d{2}):\d{2}/)
  return match ? match[1] : ts
}

const AXIS = {
  stroke: '#334155',
  tick: { fill: '#64748b', fontSize: 10 },
  tickLine: false,
  axisLine: false,
}

function HRTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2 text-xs shadow-xl min-w-[150px]">
      <div className="text-slate-400 font-mono mb-1">{d.time}</div>
      <div className="text-indigo-300 font-semibold">{d.hr_avg.toFixed(0)} bpm avg</div>
      <div className="text-slate-500 text-[10px]">Range {d.hr_min}–{d.hr_max}</div>
    </div>
  )
}

function SimpleTooltip({ active, payload, unit, color }) {
  if (!active || !payload?.length) return null
  const v = payload[0].value
  return (
    <div className="rounded-lg bg-slate-950/95 ring-1 ring-slate-700 px-3 py-2 text-xs shadow-xl">
      <div style={{ color }}>{v != null ? v.toFixed(1) : '—'} {unit}</div>
    </div>
  )
}

export default function WorkoutHRChart({ fixture = null, loading = false }) {
  const raw = fixture ?? HR_FIXTURE

  if (loading) {
    return (
      <div className="space-y-3 animate-pulse">
        <div className="h-28 bg-slate-800 rounded-lg" />
        <div className="h-16 bg-slate-800 rounded-lg" />
        <div className="h-14 bg-slate-800 rounded-lg" />
      </div>
    )
  }

  if (!raw?.samples?.length) {
    return <div className="py-4 text-center text-slate-500 text-sm">No HR data recorded.</div>
  }

  const data = raw.samples.map(s => ({
    ...s,
    time: fmtTime(s.ts),
    steps_bar: s.steps ?? 0,
  }))

  const hasSteps = data.some(d => d.steps != null)

  return (
    <div className="space-y-3">
      {/* HR lines (avg + min/max dashed) */}
      <div>
        <div className="text-[9px] uppercase tracking-widest text-slate-500 font-mono mb-1">Heart Rate · bpm</div>
        <div style={{ width: '100%', height: 100 }}>
          <ResponsiveContainer>
            <LineChart data={data} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#1e293b" />
              <XAxis dataKey="time" {...AXIS} interval="preserveStartEnd" />
              <YAxis domain={['auto', 'auto']} {...AXIS} />
              <Tooltip content={<HRTooltip />} cursor={{ stroke: '#475569', strokeWidth: 1 }} />
              <Line type="monotone" dataKey="hr_min" stroke="#6366f1" strokeWidth={1} strokeDasharray="3 3" dot={false} strokeOpacity={0.45} />
              <Line type="monotone" dataKey="hr_max" stroke="#6366f1" strokeWidth={1} strokeDasharray="3 3" dot={false} strokeOpacity={0.45} />
              <Line type="monotone" dataKey="hr_avg" stroke="#818cf8" strokeWidth={2} dot={false} activeDot={{ r: 3, fill: '#818cf8' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Calories */}
      <div>
        <div className="text-[9px] uppercase tracking-widest text-slate-500 font-mono mb-1">Calories · kcal/min</div>
        <div style={{ width: '100%', height: 64 }}>
          <ResponsiveContainer>
            <BarChart data={data} margin={{ top: 2, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#1e293b" />
              <XAxis dataKey="time" {...AXIS} interval="preserveStartEnd" />
              <YAxis {...AXIS} />
              <Tooltip content={<SimpleTooltip unit="kcal" color="#fbbf24" />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
              <Bar dataKey="calories" fill="#fbbf24" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Step cadence (only rendered if data has any steps) */}
      {hasSteps && (
        <div>
          <div className="text-[9px] uppercase tracking-widest text-slate-500 font-mono mb-1">Step Cadence · steps/min</div>
          <div style={{ width: '100%', height: 56 }}>
            <ResponsiveContainer>
              <BarChart data={data} margin={{ top: 2, right: 8, left: -24, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#1e293b" />
                <XAxis dataKey="time" {...AXIS} interval="preserveStartEnd" />
                <YAxis {...AXIS} />
                <Tooltip content={<SimpleTooltip unit="steps/min" color="#34d399" />} cursor={{ fill: 'rgba(148,163,184,0.06)' }} />
                <Bar dataKey="steps_bar" radius={[2, 2, 0, 0]}>
                  {data.map((d, i) => (
                    <Cell key={i} fill={d.steps == null ? '#1e293b' : '#34d399'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
