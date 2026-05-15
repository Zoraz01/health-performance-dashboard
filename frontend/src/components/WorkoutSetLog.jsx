import { prettyKey } from '../lib/formatters'

function kgToLbs(kg) {
  return Math.round(kg * 22.0462) / 10
}

function ExerciseBlock({ exercise }) {
  const { title, primary_muscle_group, sets } = exercise
  let totalReps = 0
  let totalVolumeLbs = 0
  sets.forEach(s => {
    totalReps += (s.reps ?? 0)
    if (s.weight_kg != null) totalVolumeLbs += kgToLbs(s.weight_kg) * (s.reps ?? 0)
  })

  return (
    <div className="py-3">
      <div className="flex items-center gap-2 mb-2.5">
        <span className="text-slate-200 text-[13px] font-semibold">{title}</span>
        <span className="px-1.5 py-0.5 rounded text-[9px] uppercase tracking-wider bg-slate-800 text-slate-500 font-medium ring-1 ring-slate-700">
          {prettyKey(primary_muscle_group)}
        </span>
        <span className="ml-auto text-[10px] text-slate-500 font-mono shrink-0">{sets.length} sets</span>
      </div>
      <table className="w-full">
        <tbody>
          {sets.map((s, i) => {
            const weightLbs = s.weight_kg != null ? kgToLbs(s.weight_kg) : null
            const vol = weightLbs != null ? Math.round(weightLbs * (s.reps ?? 0)) : null
            const repsDisplay = s.duration_seconds != null ? `${s.duration_seconds}s` : (s.reps != null ? `${s.reps}` : '—')
            return (
              <tr key={i} className={i % 2 === 0 ? 'bg-slate-800/30 rounded' : ''}>
                <td className="py-1 pl-2 pr-3 text-[10px] text-slate-600 font-mono w-6">{i + 1}</td>
                <td className="py-1 px-2 text-[11.5px] text-slate-300 tabular-nums font-mono">
                  {weightLbs != null ? `${weightLbs} lbs` : 'BW'}
                </td>
                <td className="py-1 px-2 text-[11.5px] text-slate-300 tabular-nums font-mono">{repsDisplay} reps</td>
                <td className="py-1 pl-2 pr-2 text-[11.5px] text-slate-500 tabular-nums font-mono text-right">
                  {vol != null ? `${vol.toLocaleString()}` : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="flex justify-end gap-4 pt-1.5 text-[9.5px] text-slate-600 font-mono border-t border-slate-800/60 mt-1">
        <span>{totalReps} total reps</span>
        {totalVolumeLbs > 0 && <span>{Math.round(totalVolumeLbs).toLocaleString()} lbs vol</span>}
      </div>
    </div>
  )
}

export default function WorkoutSetLog({ data }) {
  if (!data?.exercises?.length) {
    return <div className="py-4 text-center text-slate-500 text-sm">No set data recorded.</div>
  }
  return (
    <div className="divide-y divide-slate-800/60">
      {data.exercises.map((ex, i) => <ExerciseBlock key={i} exercise={ex} />)}
    </div>
  )
}
