import { useState } from 'react'
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

const TABS = ['Today', 'History', 'Check-in']

export default function App() {
  const [activeTab, setActiveTab] = useState('Today')

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col">

      {/* Desktop top nav */}
      <nav className="hidden lg:flex items-center justify-between px-6 py-3 border-b border-slate-700/50">
        <span className="text-sm font-semibold tracking-wide text-slate-300">Health Dashboard</span>
        <div className="flex gap-1">
          {TABS.map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-slate-700 text-white'
                  : 'text-slate-400 hover:text-white hover:bg-slate-800'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </nav>

      {/* Soreness check-in banner */}
      <SorenessCheckIn />

      {/* Main content */}
      <main className="flex-1 flex flex-col lg:flex-row overflow-hidden">

        {/* Left column — 3D map, sticky on desktop */}
        <aside className="
          w-full max-h-[60vh]
          lg:w-80 xl:w-96 lg:max-h-none lg:sticky lg:top-0 lg:self-start lg:h-screen
          border-b border-slate-700/50 lg:border-b-0 lg:border-r lg:border-slate-700/50
        ">
          <MuscleMap3D />
        </aside>

        {/* Right column — scrollable panels */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">

            {activeTab === 'Today' && (
              <>
                <ActivitySummary />
                <RecoveryMetrics />
                <ClaudeCard />
                <ScoreChart />
                <WorkoutLog />
                <RecoveryStatus />
                <SleepCard />
              </>
            )}

            {activeTab === 'History' && (
              <>
                <ActivityCharts />
                <ScoreChart />
              </>
            )}

            {activeTab === 'Check-in' && (
              <div className="bg-slate-800 rounded-xl p-6 text-slate-400 text-sm">
                Soreness check-in for today will appear here.
              </div>
            )}

          </div>
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden flex border-t border-slate-700/50 bg-slate-900/95 backdrop-blur">
        {TABS.map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 py-3 text-xs font-medium transition-colors ${
              activeTab === tab
                ? 'text-white border-t-2 border-emerald-400'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            {tab}
          </button>
        ))}
      </nav>
    </div>
  )
}
