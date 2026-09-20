import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { OrbitControls, Stars, Grid } from '@react-three/drei'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { useStore } from '../lib/store'
import type { Frame, WorldLabel, Structure } from '../lib/types'
import { Employees } from './Employees'
import { Teams } from './Teams'
import { Flows } from './Flows'
import { ProcessPaths } from './Paths'
import { api } from '../lib/api'

/** Root 3D scene. Renders one or two worlds (split universe) and drives the intra-month animation clock. */
export function Scene() {
  return (
    <Canvas dpr={[1, 1.75]} gl={{ antialias: true, powerPreference: 'high-performance' }} camera={{ position: [0, 42, 58], fov: 40, near: 0.5, far: 600 }}
      onPointerMissed={() => useStore.getState().select(null)}>
      <color attach="background" args={['#07090f']} />
      <fog attach="fog" args={['#07090f', 140, 420]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[30, 60, 20]} intensity={1.1} color={'#dfe8ff'} />
      <pointLight position={[-40, 20, -30]} intensity={40} color={'#6fd3ff'} distance={120} />
      <pointLight position={[40, 15, 30]} intensity={30} color={'#ffb566'} distance={120} />
      <Stars radius={200} depth={60} count={1500} factor={3} saturation={0} fade speed={0.3} />
      <Suspense fallback={null}>
        <Worlds />
      </Suspense>
      <CameraRig />
    </Canvas>
  )
}

function Worlds() {
  const frames = useStore((s) => s.frames)
  const structure = useStore((s) => s.structure)
  const viewMonth = useStore((s) => s.viewMonth)
  const viewMode = useStore((s) => s.viewMode)
  const world = useStore((s) => s.world)
  const xray = useStore((s) => s.xray)
  const status = useStore((s) => s.status)
  const showNetwork = useStore((s) => s.showNetwork)
  const [t01, setT01] = useState(0)
  const lastMonth = useRef(-1)
  const clock = useRef(0)
  const [network, setNetwork] = useState<Record<string, any>>({})

  const forked = !!status?.forked && frames.intervention.length > 0
  const labels: WorldLabel[] = viewMode === 'split' && forked ? ['baseline', 'intervention'] : [forked && world === 'intervention' ? 'intervention' : 'baseline']
  const spread = viewMode === 'split' && forked ? 1 : 0
  const extent = useMemo(() => {
    const s = structure.baseline
    if (!s) return 30
    let m = 0
    for (const k in s.layout.departments) { const [x, z, r] = s.layout.departments[k]; m = Math.max(m, Math.abs(x) + r, Math.abs(z) + r) }
    return m
  }, [structure.baseline])

  const cur: Record<string, Frame | null> = {}
  const prev: Record<string, Frame | null> = {}
  for (const l of labels) {
    const fs = frames[l]
    const at = viewMonth === null ? fs.length - 1 : Math.max(0, fs.findIndex((f) => f.month === viewMonth) === -1 ? fs.length - 1 : fs.findIndex((f) => f.month === viewMonth))
    cur[l] = fs[at] || null
    prev[l] = fs[at - 1] || null
  }
  const monthKey = (cur.baseline?.month ?? 0) * 1000 + (cur.intervention?.month ?? 0)
  useFrame((_, dt) => {
    if (monthKey !== lastMonth.current) { lastMonth.current = monthKey; clock.current = 0 }
    const speed = status?.playing ? Math.max(0.6, status.speed) : 0.6
    clock.current = Math.min(1, clock.current + dt * speed)
    setT01(clock.current)
  })
  useEffect(() => {
    if (!showNetwork || xray !== 'information') return
    let alive = true
    for (const l of labels) api(`/network/${l}`).then((n) => alive && setNetwork((s) => ({ ...s, [l]: n.informal.team_edges }))).catch(() => {})
    return () => { alive = false }
  }, [showNetwork, xray, monthKey])

  const diffTeams = useMemo(() => {
    if (viewMode !== 'difference' || !forked) return undefined
    const b = frames.baseline[frames.baseline.length - 1], i = frames.intervention[frames.intervention.length - 1]
    if (!b || !i) return undefined
    const out: Record<string, number> = {}
    for (const t of i.teams) { const tb = b.teams.find((x) => x.id === t.id); if (tb) out[t.id] = Math.abs(t.backlog_months - tb.backlog_months) * 2 + Math.abs(t.workload - tb.workload) + Math.abs(t.headcount - tb.headcount) * 0.2 }
    return out
  }, [viewMode, forked, frames])

  return (
    <group>
      <Grid position={[0, -0.02, 0]} args={[400, 400]} cellSize={4} cellThickness={0.4} cellColor={'#111827'} sectionSize={20} sectionThickness={0.8} sectionColor={'#182236'} fadeDistance={300} fadeStrength={2} infiniteGrid />
      {labels.map((l, idx) => {
        const f = cur[l]; const s = structure[l] || structure.baseline
        if (!f || !s) return null
        const ox = spread ? (idx === 0 ? -(extent + 6) : extent + 6) : 0
        const offset: [number, number, number] = [ox, 0, 0]
        const teamPos: Record<string, [number, number]> = {}
        f.teams.forEach((t) => (teamPos[t.id] = [t.x, t.z]))
        const teamDept: Record<string, string> = {}
        f.teams.forEach((t) => (teamDept[t.id] = t.dept))
        return (
          <group key={l}>
            <ProcessPaths structure={s} offset={offset} xray={xray} teamPos={teamPos} network={network[l]} />
            <Teams frame={f} world={l} offset={offset} xray={xray} diffTeams={l === 'intervention' ? diffTeams : undefined} />
            <Employees frame={f} prev={prev[l]} world={l} offset={offset} teamDept={teamDept} xray={xray} t01={t01} />
            <Flows frame={f} offset={offset} xray={xray} t01={t01} teamPos={teamPos} />
            {spread ? <WorldLabelText label={l} x={ox} z={extent + 4} /> : null}
          </group>
        )
      })}
    </group>
  )
}

import { Text } from '@react-three/drei'
function WorldLabelText({ label, x, z }: { label: string; x: number; z: number }) {
  return <Text position={[x, 0.1, z]} rotation={[-Math.PI / 2, 0, 0]} fontSize={1.6} color={label === 'baseline' ? '#7fa7ff' : '#ffb566'} anchorX="center" letterSpacing={0.4}>{label.toUpperCase()}</Text>
}

/** Orbit controls plus cinematic / follow-the-consequences behaviour. */
function CameraRig() {
  const controls = useRef<any>(null)
  const watch = useStore((s) => s.watch)
  const follow = useStore((s) => s.followConsequences)
  const selection = useStore((s) => s.selection)
  const frames = useStore((s) => s.frames)
  const status = useStore((s) => s.status)
  const viewMode = useStore((s) => s.viewMode)
  const structure = useStore((s) => s.structure)
  const { camera } = useThree()
  const target = useRef(new THREE.Vector3())
  const goal = useRef<THREE.Vector3 | null>(null)
  const goalCam = useRef<THREE.Vector3 | null>(null)
  const extent = useMemo(() => { const s = structure.baseline; if (!s) return 30; let m = 0; for (const k in s.layout.departments) { const [x, z, r] = s.layout.departments[k]; m = Math.max(m, Math.abs(x) + r, Math.abs(z) + r) } return m }, [structure.baseline])
  const offX = (w: WorldLabel) => (viewMode === 'split' && status?.forked ? (w === 'baseline' ? -(extent + 6) : extent + 6) : 0)

  useEffect(() => {
    if (!selection) { goal.current = null; goalCam.current = null; return }
    const f = frames[selection.world][frames[selection.world].length - 1]
    if (!f) return
    if (selection.kind === 'team') {
      const t = f.teams.find((x) => x.id === selection.id)
      if (t) { goal.current = new THREE.Vector3(t.x + offX(selection.world), 0.5, t.z); goalCam.current = new THREE.Vector3(t.x + offX(selection.world) + 6, 12, t.z + 14) }
    } else {
      const e = f.employees.find((x) => x[0] === selection.id)
      if (e) { goal.current = new THREE.Vector3(e[2] + offX(selection.world), 0.6, e[3]); goalCam.current = new THREE.Vector3(e[2] + offX(selection.world) + 3, 6, e[3] + 7) }
    }
  }, [selection])

  useEffect(() => {
    if (!follow || !status?.forked) return
    const b = frames.baseline[frames.baseline.length - 1], i = frames.intervention[frames.intervention.length - 1]
    if (!b || !i) return
    let best: any = null, bestD = 0
    for (const t of i.teams) { const tb = b.teams.find((x) => x.id === t.id); if (!tb) continue; const d = Math.abs(t.backlog_months - tb.backlog_months) * 2 + Math.abs(t.workload - tb.workload) + Math.abs(t.headcount - tb.headcount) * 0.3; if (d > bestD) { bestD = d; best = t } }
    if (best && bestD > 0.15) { goal.current = new THREE.Vector3(best.x + offX('intervention'), 0.5, best.z); goalCam.current = new THREE.Vector3(best.x + offX('intervention') + 8, 14, best.z + 16) }
  }, [follow, frames.intervention.length])

  const t = useRef(0)
  const fitted = useRef(false)
  useEffect(() => { fitted.current = false }, [viewMode, status?.forked])
  useFrame((_, dt) => {
    t.current += dt
    const c = controls.current
    if (!c) return
    if (!fitted.current && structure.baseline) {
      fitted.current = true
      const span = viewMode === 'split' && status?.forked ? extent * 2 + 12 : extent
      camera.position.set(0, span * 1.35 + 14, span * 1.55 + 18)
      c.target.set(0, 0, 0)
    }
    if (watch && !selection && !follow) {
      const r = extent * 1.9 + 10
      const a = t.current * 0.045
      const gx = Math.cos(a) * r, gz = Math.sin(a) * r
      camera.position.lerp(new THREE.Vector3(gx, 22 + 6 * Math.sin(a * 0.7), gz), Math.min(1, dt * 0.6))
      c.target.lerp(new THREE.Vector3(0, 1, 0), Math.min(1, dt))
    } else if (goal.current && goalCam.current) {
      c.target.lerp(goal.current, Math.min(1, dt * 2.2))
      camera.position.lerp(goalCam.current, Math.min(1, dt * 1.6))
      if (camera.position.distanceTo(goalCam.current) < 0.3) { goalCam.current = null }
    }
    c.update()
  })
  return <OrbitControls ref={controls} enableDamping dampingFactor={0.08} maxPolarAngle={Math.PI * 0.47} minDistance={4} maxDistance={220} />
}
