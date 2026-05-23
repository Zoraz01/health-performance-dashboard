import { useState, useEffect } from 'react'
import { useTheme } from './ThemeContext'
import { useAuth } from './AuthContext'
import apiFetch from './apiFetch'
import SorenessCheckIn from './components/SorenessCheckIn'
import MuscleMap3D from './components/MuscleMap3D'
import ClaudeCard from './components/ClaudeCard'
import ScoreChart from './components/ScoreChart'
import ActivitySummary from './components/ActivitySummary'
import RecoveryMetrics from './components/RecoveryMetrics'
import WorkoutLog from './components/WorkoutLog'
import RecoveryStatus from './components/RecoveryStatus'
import ActivityCharts from './components/ActivityCharts'
import SleepCard from './components/SleepCard'
import HistoryLog from './components/HistoryLog'
import { SleepTrend, VolumeTrend, AllScoresTrend, ActivityMixTrend } from './components/TrendCards'
import ErrorBoundary from './components/ErrorBoundary'

const TABS = ['Yesterday', 'Trends', 'History']

function SunIcon(p) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <circle cx="8" cy="8" r="2.5"/>
      <path d="M8 1.5V3M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1"/>
    </svg>
  )
}

function MoonIcon(p) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M13.5 9.5A6 6 0 0 1 6.5 2.5a6 6 0 1 0 7 7Z"/>
    </svg>
  )
}

function FitPulseLogo({ className = 'w-4 h-4' }) {
  return (
    <svg viewBox="0 0 16 16" className={className} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="1,8 3.5,8 5,4.5 7,11.5 9,3 11,10.5 12.5,8 15,8" />
    </svg>
  )
}

function CalendarIcon(p) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <rect x="3" y="4.5" width="14" height="12" rx="2" />
      <path d="M3 8.5h14M7 2.5v4M13 2.5v4" />
    </svg>
  )
}

function TrendsIcon(p) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M3 14.5l4-4.5 3.5 2.5 3.5-5L17 11" />
      <path d="M3 17h14" />
    </svg>
  )
}

function HistoryIcon(p) {
  return (
    <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <circle cx="10" cy="10" r="7" />
      <path d="M10 7v3.5l2.5 2" />
    </svg>
  )
}

function LogoutIcon(p) {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" {...p}>
      <path d="M10 8H2M6 5l-3 3 3 3M11 5V4a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h4a2 2 0 0 0 2-2v-1"/>
    </svg>
  )
}

const TAB_ICON = { Yesterday: CalendarIcon, Trends: TrendsIcon, History: HistoryIcon }

export default function App() {
  const [activeTab, setActiveTab]     = useState('Yesterday')
  const [checkInOpen, setCheckInOpen]       = useState(false)
  const [checkInDate, setCheckInDate]       = useState(null)
  const [pendingAnalysis, setPendingAnalysis] = useState(null)
  const { isDark, toggle } = useTheme()
  const { logout } = useAuth()
  const canCheckIn = new Date().getHours() >= 17
  const [snapshotsData,    setSnapshotsData]    = useState(null)
  const [snapshotsLoading, setSnapshotsLoading] = useState(true)
  const [recordData,       setRecordData]       = useState(null)
  const [recordLoading,    setRecordLoading]    = useState(true)
  const [baselinesData,    setBaselinesData]    = useState(null)
  const [baselinesLoading, setBaselinesLoading] = useState(true)
  const [muscleVol30d,       setMuscleVol30d]       = useState(null)
  const [muscleVolBaselines, setMuscleVolBaselines] = useState(null)
  const [muscleHistoryDays,  setMuscleHistoryDays]  = useState(0)
  const [fetchCount, setFetchCount] = useState(0)

  useEffect(() => {
    setSnapshotsLoading(true)
    setRecordLoading(true)
    setBaselinesLoading(true)

    apiFetch('/api/data/snapshots')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setSnapshotsData(d) })
      .catch(() => {})
      .finally(() => setSnapshotsLoading(false))

    apiFetch('/api/data/record')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setRecordData(d) })
      .catch(() => {})
      .finally(() => setRecordLoading(false))

    apiFetch('/api/data/baselines')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setBaselinesData(d) })
      .catch(() => {})
      .finally(() => setBaselinesLoading(false))

    apiFetch('/api/data/muscle-volume')
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setMuscleVol30d(d.muscle_volume)
          setMuscleVolBaselines(d.baselines)
          setMuscleHistoryDays(d.history_days ?? 0)
        }
      })
      .catch(() => {})
  }, [fetchCount])

  const refreshToday = () => setFetchCount(c => c + 1)

  const openPreCheckIn = (date, runFn) => {
    setCheckInDate(date)
    setPendingAnalysis(() => runFn)
    setCheckInOpen(true)
  }

  const handleCheckInClose = () => {
    setCheckInOpen(false)
    setCheckInDate(null)
    if (pendingAnalysis) {
      pendingAnalysis()
      setPendingAnalysis(null)
    }
  }

  const snapshot  = snapshotsData?.snapshot           ?? null
  const ySnap     = snapshotsData?.yesterday_snapshot  ?? null
  const record    = recordData?.record                 ?? null
  const baselines = baselinesData?.baselines           ?? null

  // The UI always shows yesterday's completed data. Use yesterday's snapshot
  // for all activity/recovery/sleep display; fall back to today's if missing.
  const displaySnap = ySnap ?? snapshot

  // "Run Analysis Now" targets yesterday's date.
  const analysisDate = record?.date ?? (() => {
    if (!snapshotsData?.date) return null
    const d = new Date(snapshotsData.date + 'T12:00:00')
    d.setDate(d.getDate() - 1)
    return d.toISOString().slice(0, 10)
  })()

  const activityData = displaySnap ? {
    date:             displaySnap.date,
    steps:            displaySnap.steps,
    active_calories:  displaySnap.active_calories,
    exercise_minutes: displaySnap.exercise_minutes,
    stand_hours:      displaySnap.stand_hours,
    distance_mi:      displaySnap.distance_mi,
    flights_climbed:  displaySnap.flights_climbed,
    hrv_ms:           displaySnap.hrv_ms,
    resting_hr:       displaySnap.resting_hr,
    avg_heart_rate:   displaySnap.avg_heart_rate,
  } : undefined

  const recoveryData = (displaySnap && baselines) ? {
    hrv_ms:               displaySnap.hrv_ms,
    hrv_avg:              baselines.hrv_avg,
    resting_hr:           displaySnap.resting_hr,
    resting_hr_avg:       baselines.resting_hr_avg,
    cardio_recovery:      displaySnap.cardio_recovery,
    cardio_recovery_avg:  baselines.cardio_recovery_avg,
    walking_hr_avg:       displaySnap.walking_hr_avg,
    walking_hr_baseline:  baselines.walking_hr_baseline,
    spo2:                 displaySnap.spo2,
    spo2_avg:             baselines.spo2_avg,
    respiratory_rate:     displaySnap.respiratory_rate,
  } : undefined

  const analysisData = record ? {
    ...record.analysis,
    date:           record.date,
    muscle_fatigue: record.workouts?.muscle_fatigue,
  } : undefined

  const sleepData = displaySnap ? {
    total:  displaySnap.sleep_total_min,
    deep:   displaySnap.sleep_deep_min,
    rem:    displaySnap.sleep_rem_min,
    awake:  displaySnap.sleep_awake_min,
    stages: displaySnap.sleep_stages ?? null,
    source: displaySnap.sleep_source ?? null,
    hr:     displaySnap.sleep_hr     ?? null,
  } : null

  const muscleMapData = displaySnap ? (() => {
    const rs = displaySnap.recovery_status ?? {}
    const mv = muscleVol30d      ?? {}
    const bl = muscleVolBaselines ?? {}
    const muscles = new Set([...Object.keys(rs), ...Object.keys(mv)])
    return Object.fromEntries([...muscles].map(m => [m, {
      recovery_pct:    rs[m]?.recovery_pct ?? 100,
      days:            rs[m]?.days_since_trained ?? 99,
      volume:          mv[m] ?? 0,
      volumeBaseline:  bl[m] ?? null,
    }]))
  })() : undefined

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">

      {/* Mobile top bar */}
      <div className="lg:hidden border-b border-slate-800/60 shadow-[0_4px_16px_rgb(0_0_0/0.35)]">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <div
              className="w-6 h-6 rounded-md grid place-items-center shadow"
              style={{ background: 'linear-gradient(135deg, #e09a5e 0%, #b8662e 100%)', boxShadow: '0 4px 12px -6px rgba(184,102,46,0.55)' }}
            >
              <FitPulseLogo className="w-3.5 h-3.5" style={{ color: '#1d1106' }} />
            </div>
            <span className="text-[13px] font-semibold tracking-tight text-slate-100">FitPulse</span>
          </div>
          <div className="flex items-center gap-1.5">
            {canCheckIn && (
              <button
                onClick={() => setCheckInOpen(true)}
                className="px-2.5 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 text-[11px] font-semibold transition-colors"
              >
                Check In
              </button>
            )}
            <button
              onClick={e => toggle(e.currentTarget)}
              className="w-8 h-8 rounded-lg bg-slate-900 ring-1 ring-slate-800 grid place-items-center text-slate-400 hover:text-slate-200 transition-colors shadow-[inset_0_1px_0_rgb(255_255_255/0.05),0_1px_4px_rgb(0_0_0/0.4)]"
            >
              {isDark ? <SunIcon className="w-4 h-4" /> : <MoonIcon className="w-4 h-4" />}
            </button>
            <button
              onClick={logout}
              className="w-8 h-8 rounded-lg bg-slate-900 ring-1 ring-slate-800 grid place-items-center text-slate-400 hover:text-red-400 transition-colors shadow-[inset_0_1px_0_rgb(255_255_255/0.05),0_1px_4px_rgb(0_0_0/0.4)]"
              title="Sign out"
            >
              <LogoutIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Desktop top nav — centered, tabs in middle */}
      <nav className="hidden lg:block sticky top-0 z-30 border-b border-slate-800/60 backdrop-blur-xl bg-slate-950/85 shadow-[0_4px_24px_rgb(0_0_0/0.45)]">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center">
          {/* Logo — left */}
          <div className="flex items-center gap-2.5 w-52 shrink-0">
            <div
              className="w-7 h-7 rounded-md grid place-items-center"
              style={{ background: 'linear-gradient(135deg, #e09a5e 0%, #b8662e 100%)', boxShadow: '0 6px 18px -8px rgba(184,102,46,0.55)' }}
            >
              <FitPulseLogo className="w-3.5 h-3.5" style={{ color: '#1d1106' }} />
            </div>
            <div className="leading-tight">
              <div className="text-[13px] font-semibold text-slate-100">FitPulse</div>
              <div className="text-[10px] uppercase tracking-widest text-slate-500 -mt-0.5">daily readiness</div>
            </div>
          </div>
          {/* Tabs — center */}
          <div className="flex-1 flex justify-center">
            <div className="flex gap-0.5 bg-slate-900/80 ring-1 ring-slate-800 rounded-lg p-0.5 shadow-[inset_0_1px_0_rgb(255_255_255/0.04),0_2px_8px_rgb(0_0_0/0.35)]">
              {TABS.map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-1.5 rounded-md text-[12px] font-medium transition-colors ${
                    activeTab === tab
                      ? 'bg-slate-800 text-slate-100 shadow-[inset_0_1px_0_rgb(255_255_255/0.08),0_1px_6px_rgb(0_0_0/0.4)]'
                      : 'text-slate-500 hover:text-slate-200'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>
          {/* Check-in + Toggle + Logout — right */}
          <div className="flex items-center justify-end gap-2 w-52 shrink-0">
            {canCheckIn && (
              <button
                onClick={() => setCheckInOpen(true)}
                className="px-2.5 py-1 rounded-lg bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 text-[11px] font-semibold transition-colors"
              >
                Check In
              </button>
            )}
            <button
              onClick={e => toggle(e.currentTarget)}
              className="w-8 h-8 rounded-lg bg-slate-900 ring-1 ring-slate-800 grid place-items-center text-slate-400 hover:text-slate-200 transition-colors shadow-[inset_0_1px_0_rgb(255_255_255/0.05),0_1px_4px_rgb(0_0_0/0.4)]"
              title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {isDark ? <SunIcon className="w-4 h-4" /> : <MoonIcon className="w-4 h-4" />}
            </button>
            <button
              onClick={logout}
              className="w-8 h-8 rounded-lg bg-slate-900 ring-1 ring-slate-800 grid place-items-center text-slate-400 hover:text-red-400 transition-colors shadow-[inset_0_1px_0_rgb(255_255_255/0.05),0_1px_4px_rgb(0_0_0/0.4)]"
              title="Sign out"
            >
              <LogoutIcon className="w-4 h-4" />
            </button>
          </div>
        </div>
      </nav>

      {/* Soreness banner + modal — key resets component when switching between today/yesterday */}
      <SorenessCheckIn
        key={checkInDate || 'today'}
        forceOpen={checkInOpen}
        onClose={handleCheckInClose}
        targetDate={checkInDate}
        showBanner={canCheckIn}
      />

      {/* Main layout — centered max-width container */}
      <main className="flex-1 flex flex-col lg:flex-row lg:min-h-0 max-w-6xl mx-auto w-full">

        {/* Left — Muscle map, sticky on desktop */}
        <aside className="
          w-full
          lg:w-[340px] xl:w-[380px] lg:sticky lg:top-14 lg:self-start lg:h-auto
          border-b border-slate-800/60 lg:border-b-0 lg:border-r lg:border-slate-800/60
          p-4 lg:p-5 shrink-0
        ">
          <ErrorBoundary fallback={
            <div className="rounded-xl p-6 text-center text-sm text-slate-500" style={{ background: 'var(--card)' }}>
              3D muscle map unavailable
            </div>
          }>
            <MuscleMap3D data={muscleMapData} historyDays={muscleHistoryDays} />
          </ErrorBoundary>
        </aside>

        {/* Right — scrollable content */}
        <div className="min-w-0 lg:flex-1 lg:overflow-y-auto lg:min-h-0">
          <div className="max-w-2xl mx-auto px-4 py-6 pb-28 lg:pb-6 space-y-6">

            {activeTab === 'Yesterday' && (
              <ErrorBoundary>
                <ActivitySummary data={snapshotsLoading ? undefined : activityData} loading={snapshotsLoading} />
                <ClaudeCard analysis={recordLoading ? undefined : analysisData} date={analysisDate} onAnalyzed={refreshToday} onPreCheckIn={openPreCheckIn} />
                <RecoveryMetrics data={(snapshotsLoading || baselinesLoading) ? undefined : recoveryData} loading={snapshotsLoading || baselinesLoading} />
                <WorkoutLog sessions={snapshotsLoading ? undefined : (displaySnap?.workouts ?? null)} loading={snapshotsLoading} />
                <RecoveryStatus data={snapshotsLoading ? undefined : (displaySnap?.recovery_status ?? null)} loading={snapshotsLoading} />
                <SleepCard data={sleepData} />
                <ScoreChart />
              </ErrorBoundary>
            )}

            {activeTab === 'Trends' && (
              <ErrorBoundary>
                <ActivityCharts />
                <ScoreChart />
                <AllScoresTrend />
                <SleepTrend />
                <VolumeTrend />
                <ActivityMixTrend />
              </ErrorBoundary>
            )}

            {activeTab === 'History' && (
              <ErrorBoundary>
                <HistoryLog />
              </ErrorBoundary>
            )}

          </div>
        </div>
      </main>

      {/* Mobile bottom nav — fixed so it's always visible */}
      <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-40 border-t border-slate-800/60 bg-slate-950/95 backdrop-blur-xl shadow-[0_-4px_20px_rgb(0_0_0/0.5)]">
        <div className="flex" style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}>
          {TABS.map(tab => {
            const Icon = TAB_ICON[tab]
            const active = activeTab === tab
            return (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`flex-1 flex flex-col items-center justify-center gap-1 py-2.5 relative transition-colors ${
                  active ? 'text-amber-400' : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {active && (
                  <span className="absolute top-0 left-1/4 right-1/4 h-0.5 rounded-b-full bg-amber-400" />
                )}
                <Icon className="w-5 h-5" />
                <span className={`text-[10px] leading-none tracking-wide ${active ? 'font-bold' : 'font-medium'}`}>
                  {tab}
                </span>
              </button>
            )
          })}
        </div>
      </nav>
    </div>
  )
}
