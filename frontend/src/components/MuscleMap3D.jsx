import { useRef, useMemo, useEffect, useState, useCallback } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { useGLTF, OrbitControls, Center, Bounds } from '@react-three/drei'
import * as THREE from 'three'
import { useTheme } from '../ThemeContext'

const MODEL = new URL(
  '../assets/3d model/male_full_body_ecorche.glb',
  import.meta.url
).href

const MESH_TO_MUSCLE = [
  'glutes',      // 0
  'shoulders',   // 1
  'calves',      // 2
  'hamstrings',  // 3
  null,          // 4
  'back',        // 5  whole back (lats + upper_back + traps + lower_back)
  null,          // 6  face
  'quadriceps',  // 7
  null,          // 8
  null,          // 9  hands
  'chest',       // 10
  null,          // 11
  null,          // 12 hip abductors — not tracked
  null,  // 13
  'forearms',    // 14
  'upper_arms',  // 15 biceps + triceps
]

const COMPOSITE_MUSCLES = {
  back:       ['lats', 'upper_back', 'traps', 'lower_back'],
  upper_arms: ['biceps', 'triceps'],
}

const MUSCLE_LABELS = {
  chest:      'Chest',
  shoulders:  'Shoulders',
  forearms:   'Forearms',
  back:       'Back',
  quadriceps: 'Quads',
  hamstrings: 'Hamstrings',
  glutes:     'Glutes',
  calves:     'Calves',
  upper_arms: 'Upper Arms',
}

// Recovery mode — green / yellow / red traffic light
const REC = {
  ready:   '#22c55e',
  partial: '#eab308',
  fatigued:'#ef4444',
  noData:  '#d1d5db',  // near-white — neutral base
  hover:   '#fbbf24',
}

// Volume mode
const VOL = {
  none: '#d1d5db',
  low:  '#4bc4e8',
  mid:  '#eab308',
  high: '#ef4444',
  hover:'#fbbf24',
}

const SCENE_BG = { dark: '#0c242c', light: '#c2b8ac' }

function resolvePct(key, data) {
  if (!key || !data) return null
  const subs = COMPOSITE_MUSCLES[key]
  if (subs) {
    const pcts = subs.map(k => data[k]?.recovery_pct).filter(v => v != null)
    return pcts.length ? Math.min(...pcts) : null
  }
  return data[key]?.recovery_pct ?? null
}

function resolveVol(key, data) {
  if (!key || !data) return null
  const subs = COMPOSITE_MUSCLES[key]
  if (subs) {
    return subs.reduce((sum, k) => sum + (data[k]?.volume ?? 0), 0)
  }
  return data[key]?.volume ?? null
}

function recoveryColor(pct) {
  if (pct == null) return REC.noData
  if (pct >= 80)   return REC.ready
  if (pct >= 40)   return REC.partial
  return REC.fatigued
}

function volumeColor(vol, maxVol) {
  if (vol == null || vol === 0) return VOL.none
  const t = Math.min(1, vol / Math.max(maxVol, 1))
  if (t < 0.33) return VOL.low
  if (t < 0.66) return VOL.mid
  return VOL.high
}

function Spinner({ target }) {
  useFrame(() => {
    if (target.current) target.current.rotation.y += 0.0012
  })
  return null
}

function Body({ innerRef, data, mode, maxVol, onHover, onUnhover, onPin }) {
  const { scene } = useGLTF(MODEL)
  const hoveredRef = useRef(null)

  useMemo(() => {
    let i = 0
    scene.traverse(node => {
      if (node.isMesh) {
        node.material = new THREE.MeshStandardMaterial({
          color:             new THREE.Color(recoveryColor(null)),
          emissive:          new THREE.Color('#000000'),
          emissiveIntensity: 0,
          roughness: 0.55,
          metalness: 0.05,
        })
        node.castShadow = true
        node.userData.muscleKey  = MESH_TO_MUSCLE[i] ?? null
        node.userData.meshIndex  = i
        i++
      }
    })
  }, [scene])

  useEffect(() => {
    scene.traverse(node => {
      if (node.isMesh && node.material) {
        const key = node.userData.muscleKey
        let color
        if (mode === 'volume') {
          color = volumeColor(resolveVol(key, data), maxVol)
        } else {
          color = recoveryColor(resolvePct(key, data))
        }
        node.material.color.set(color)
        node.material.needsUpdate = true
      }
    })
  }, [scene, data, mode, maxVol])

  const hoverColor = mode === 'volume' ? VOL.hover : REC.hover

  return (
    <Center>
      <group ref={innerRef}>
        <primitive
          object={scene}
          onPointerOver={(e) => {
            e.stopPropagation()
            // Skip hover logic for touch — tap (onClick) handles it instead
            if (e.pointerType === 'touch') return
            const key = e.object.userData.muscleKey
            if (hoveredRef.current && hoveredRef.current !== e.object) {
              hoveredRef.current.material.emissive.set('#000000')
              hoveredRef.current.material.emissiveIntensity = 0
              hoveredRef.current = null
            }
            if (!key) { onUnhover(); return }
            hoveredRef.current = e.object
            e.object.material.emissive.set(hoverColor)
            e.object.material.emissiveIntensity = 0.35
            onHover(key, e.nativeEvent)
          }}
          onPointerOut={(e) => {
            if (e.pointerType === 'touch') return
            if (hoveredRef.current) {
              hoveredRef.current.material.emissive.set('#000000')
              hoveredRef.current.material.emissiveIntensity = 0
              hoveredRef.current = null
            }
            onUnhover()
          }}
          onClick={(e) => {
            e.stopPropagation()
            const key = e.object.userData.muscleKey
            if (!key) return
            // Highlight tapped mesh
            if (hoveredRef.current && hoveredRef.current !== e.object) {
              hoveredRef.current.material.emissive.set('#000000')
              hoveredRef.current.material.emissiveIntensity = 0
            }
            hoveredRef.current = e.object
            e.object.material.emissive.set(hoverColor)
            e.object.material.emissiveIntensity = 0.35
            onPin(key, e.nativeEvent)
          }}
        />
      </group>
    </Center>
  )
}

function SceneBg({ isDark }) {
  return <color attach="background" args={[isDark ? SCENE_BG.dark : SCENE_BG.light]} />
}

export default function MuscleMap3D({ data }) {
  const bodyRef = useRef()
  const { isDark } = useTheme()
  const [hover, setHover]   = useState(null)   // mouse-only, cursor-relative
  const [pinned, setPinned] = useState(null)   // tap/click, persists until dismissed
  const [mode, setMode]     = useState('recovery')

  // Active tooltip: pinned takes priority over hover
  const tooltip = pinned ?? hover

  const handleHover   = useCallback((key, e) => setHover({ key, x: e.offsetX, y: e.offsetY }), [])
  const handleUnhover = useCallback(() => setHover(null), [])
  const handlePin     = useCallback((key, e) => {
    setPinned(prev => {
      if (prev?.key === key) return null  // tap same muscle again → dismiss
      // Touch: anchor tooltip to fixed position in container; mouse: cursor position
      return e.pointerType === 'touch'
        ? { key, touch: true }
        : { key, x: e.offsetX, y: e.offsetY, touch: false }
    })
  }, [])

  // Max volume across all muscles — used to scale volume colors
  const maxVol = useMemo(() => {
    if (!data) return 1
    return Math.max(1, ...Object.values(data).map(d => d?.volume ?? 0))
  }, [data])

  const tooltipPct  = tooltip ? resolvePct(tooltip.key, data) : null
  const tooltipVol  = tooltip ? resolveVol(tooltip.key, data) : null
  const tooltipSubs = tooltip ? COMPOSITE_MUSCLES[tooltip.key] : null

  const REC_LEGEND = [
    { color: REC.fatigued, label: 'Fatigued'  },
    { color: REC.partial,  label: 'Recovering' },
    { color: REC.ready,    label: 'Ready'       },
  ]
  const VOL_LEGEND = [
    { color: VOL.low,  label: 'Low'  },
    { color: VOL.mid,  label: 'Med'  },
    { color: VOL.high, label: 'High' },
  ]
  const legend = mode === 'recovery' ? REC_LEGEND : VOL_LEGEND

  return (
    <div className="relative rounded-2xl ring-1 ring-slate-800 bg-gradient-to-b from-slate-900/80 to-slate-950 overflow-hidden lg:sticky lg:top-6 h-[400px] lg:h-auto"
      style={{ aspectRatio: '3 / 4' }}
    >
      {/* Header */}
      <div className="absolute top-0 inset-x-0 z-20 px-4 pt-4 flex items-start justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-semibold">
            Muscle Map
          </div>
          <div className="text-slate-100 text-base font-semibold mt-0.5">
            {mode === 'recovery' ? 'Recovery heatmap' : '30-day volume'}
          </div>
        </div>

        {/* Recovery / Volume toggle */}
        <div className="inline-flex items-center bg-slate-950/70 backdrop-blur ring-1 ring-slate-800 rounded-md p-0.5 mt-1">
          {[{ id: 'recovery', label: 'Recovery' }, { id: 'volume', label: 'Volume' }].map(t => (
            <button
              key={t.id}
              onClick={() => setMode(t.id)}
              className={
                'px-2 py-1 rounded-[5px] text-[10.5px] font-semibold transition-colors ' +
                (mode === t.id
                  ? 'bg-slate-800 text-slate-100'
                  : 'text-slate-400 hover:text-slate-200')
              }
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 3D canvas — fills the panel */}
      <Canvas
        camera={{ position: [0, 0, 5], fov: 48 }}
        style={{ width: '100%', height: '100%' }}
        gl={{ antialias: true }}
        onPointerMissed={() => setPinned(null)}
      >
        <SceneBg isDark={isDark} />
        <ambientLight intensity={0.65} />
        <directionalLight position={[2, 4, 3]} intensity={1.5} />
        <directionalLight position={[-2, 2, -2]} intensity={0.45} color="#6090ff" />

        <Bounds fit clip observe={false} margin={0.85}>
          <Body
            innerRef={bodyRef}
            data={data}
            mode={mode}
            maxVol={maxVol}
            onHover={handleHover}
            onUnhover={handleUnhover}
            onPin={handlePin}
          />
        </Bounds>

        <Spinner target={bodyRef} />

        <OrbitControls
          makeDefault
          enableZoom={false}
          enablePan={false}
          minPolarAngle={Math.PI / 2}
          maxPolarAngle={Math.PI / 2}
        />
      </Canvas>

      {/* Tooltip — cursor-relative for mouse, centered for touch */}
      {tooltip && (
        <div
          className="pointer-events-none absolute z-10 rounded-lg px-3 py-2 text-xs shadow-xl ring-1 ring-slate-700"
          style={tooltip.touch
            ? {
                bottom: '52px',
                left: '50%',
                transform: 'translateX(-50%)',
                background: isDark ? 'rgba(6,24,29,0.97)' : 'rgba(248,246,240,0.97)',
              }
            : {
                left: tooltip.x + 14,
                top:  tooltip.y - 8,
                background: isDark ? 'rgba(6,24,29,0.96)' : 'rgba(248,246,240,0.96)',
              }
          }
        >
          <div className="text-[10px] uppercase tracking-widest text-slate-500 font-medium mb-0.5">
            {MUSCLE_LABELS[tooltip.key] ?? tooltip.key}
          </div>

          {mode === 'recovery' ? (
            tooltipPct != null ? (
              <>
                <div className="tabular-nums font-semibold text-slate-100 text-sm">
                  {Math.round(tooltipPct)}%
                  <span className="text-slate-500 text-[10px] font-normal ml-1">recovered</span>
                </div>
                {tooltipSubs && (
                  <div className="text-slate-600 text-[10px] mt-0.5">
                    {tooltipSubs.map(k => {
                      const pct = data?.[k]?.recovery_pct
                      return pct != null ? `${k.replace('_', ' ')} ${Math.round(pct)}%` : null
                    }).filter(Boolean).join(' · ')}
                  </div>
                )}
              </>
            ) : (
              <div className="text-slate-500 text-[10px]">No data yet</div>
            )
          ) : (
            tooltipVol != null && tooltipVol > 0 ? (
              <>
                <div className="tabular-nums font-semibold text-slate-100 text-sm">
                  {tooltipVol.toLocaleString()}
                  <span className="text-slate-500 text-[10px] font-normal ml-1">kg·reps</span>
                </div>
                <div className="text-slate-500 text-[10px] mt-0.5 font-mono">30-day total</div>
                {tooltipSubs && (
                  <div className="text-slate-600 text-[10px] mt-0.5">
                    {tooltipSubs.map(k => {
                      const v = data?.[k]?.volume
                      return v ? `${k.replace('_', ' ')} ${v.toLocaleString()}` : null
                    }).filter(Boolean).join(' · ')}
                  </div>
                )}
              </>
            ) : (
              <div className="text-slate-500 text-[10px]">No volume recorded</div>
            )
          )}
        </div>
      )}

      {/* Legend + hint */}
      <div className="absolute bottom-0 inset-x-0 z-20 px-4 pb-3 flex items-end justify-between gap-3">
        <div className="bg-slate-950/70 backdrop-blur ring-1 ring-slate-800 rounded-md px-2.5 py-1.5">
          <div className="flex items-center gap-2">
            <div className="flex rounded overflow-hidden">
              {legend.map((s, i) => (
                <div key={i} className="w-3 h-2" style={{ background: s.color }} />
              ))}
            </div>
            <div className="flex gap-2 text-[9.5px] uppercase tracking-wider text-slate-400 font-mono">
              {legend.map((s, i) => <span key={i}>{s.label}</span>)}
            </div>
          </div>
        </div>
        <div className="text-[9.5px] uppercase tracking-widest text-slate-500 font-mono">
          tap · drag · rotate
        </div>
      </div>
    </div>
  )
}

useGLTF.preload(MODEL)
