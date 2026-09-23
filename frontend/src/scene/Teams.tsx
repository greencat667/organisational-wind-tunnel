import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { Html, Text } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import type { Frame, WorldLabel, XRay, TeamFrame } from '../lib/types'
import { useStore } from '../lib/store'
import { deptColor, WORK, WORK_HIGH, COST_PAY, COST_OVERTIME, COST_AI, budgetColor, budgetCss, kFmt } from './palette'

/** Team clusters: a ground disc (district plate), a queue "stack" that grows with backlog, a label, and a management-load ring. */
export function Teams({ frame, world, offset, xray, diffTeams }: { frame: Frame; world: WorldLabel; offset: [number, number, number]; xray: XRay; diffTeams?: Record<string, number> }) {
  const select = useStore((s) => s.select)
  const setHover = useStore((s) => s.set)
  const selection = useStore((s) => s.selection)
  return (
    <group position={offset}>
      {frame.departments.map((d) => (
        <mesh key={d.id} position={[d.x, 0.005, d.z]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[d.r, 48]} />
          <meshBasicMaterial color={deptColor(d.id)} transparent opacity={d.hiring_frozen ? 0.05 : 0.035} depthWrite={false} />
        </mesh>
      ))}
      {frame.departments.map((d) => (
        <Text key={'l' + d.id} position={[d.x, 0.06, d.z + d.r + 0.6]} rotation={[-Math.PI / 2, 0, 0]} fontSize={1.5} color={'#55617a'} anchorX="center" anchorY="middle" letterSpacing={0.3}>
          {d.name.toUpperCase()}
        </Text>
      ))}
      {xray === 'cost' && frame.departments.map((d) => (
        <Text key={'c' + d.id} position={[d.x, 0.06, d.z + d.r + 1.75]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.62} anchorX="center" anchorY="middle" letterSpacing={0.12}
          color={d.hiring_frozen ? '#ff7a8a' : budgetCss(d.spend_ratio ?? 0)}>
          {`${Math.round((d.spend_ratio ?? 0) * 100)}% OF BUDGET${d.hiring_frozen ? ' · HIRING FROZEN' : ''}`}
        </Text>
      ))}
      {frame.teams.map((t) => (
        <TeamCluster key={t.id} t={t} world={world} xray={xray} selected={!!selection && selection.kind === 'team' && selection.id === t.id && selection.world === world}
          diff={diffTeams ? diffTeams[t.id] || 0 : 0}
          onClick={() => select({ kind: 'team', id: t.id, world })}
          onHover={(x, y) => setHover({ hover: { kind: 'team', id: t.id, world, x, y } })} onOut={() => setHover({ hover: null })} />
      ))}
    </group>
  )
}

/** Cost view: a stacked tower beside the team — pay (grey), overtime (amber), AI running cost (cyan) — on one scale
 * across every team (and both worlds), so taller = more spent this month. Grows smoothly as spend changes. */
const COST_UNIT = 12000   // £ per world unit of height
function CostTower({ t }: { t: TeamFrame }) {
  const parts: [number, THREE.Color][] = [[t.cost_pay ?? 0, COST_PAY], [t.cost_overtime ?? 0, COST_OVERTIME], [t.cost_ai ?? 0, COST_AI]]
  const refs = useRef<(THREE.Mesh | null)[]>([])
  const cur = useRef<number[]>([0, 0, 0])
  useFrame((_, dt) => {
    let base = 0
    parts.forEach(([v], i) => {
      const h = Math.min(9, v / COST_UNIT)
      cur.current[i] += (h - cur.current[i]) * Math.min(1, dt * 2.5)
      const m = refs.current[i]
      if (m) { const hh = Math.max(0.001, cur.current[i]); m.scale.y = hh; m.position.y = base + hh / 2; m.visible = cur.current[i] > 0.01 }
      base += cur.current[i]
    })
  })
  const total = (t.cost_month ?? 0)
  return (
    <group position={[t.r + 1.2, 0, 0]}>
      {parts.map(([, c], i) => (
        <mesh key={i} ref={(m) => { refs.current[i] = m }} raycast={() => null}>
          <boxGeometry args={[0.8, 1, 0.8]} />
          <meshStandardMaterial color={c} emissive={c} emissiveIntensity={i === 0 ? 0.45 : 1.1} transparent opacity={0.92} toneMapped={false} />
        </mesh>
      ))}
      <Text position={[0, 0.05, 0.75]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.7} color={budgetCss(t.budget_ratio ?? 0)} anchorX="center" anchorY="top">{kFmt(total)}</Text>
    </group>
  )
}

/** AI agent pool: a ring of small cubes beside the team. Cyan = working, dim = paused/under-supervised, red = incident. */
function AgentPool({ t }: { t: TeamFrame }) {
  const ref = useRef<THREE.InstancedMesh>(null!)
  const n = Math.max(1, Math.round(t.ai_agents || 0))
  const geo = useMemo(() => new THREE.BoxGeometry(0.28, 0.28, 0.28), [])
  const tmp = useMemo(() => new THREE.Object3D(), [])
  const col = useMemo(() => new THREE.Color(), [])
  useFrame(({ clock }) => {
    const m = ref.current; if (!m) return
    const time = clock.getElapsedTime()
    const cx = -(t.r + 1.4), cz = 0
    const radius = 0.5 + 0.12 * n
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + time * (t.ai_incident || t.ai_paused ? 0 : 0.35)
      const y = 0.6 + 0.12 * Math.sin(time * 2 + i)
      tmp.position.set(cx + Math.cos(a) * radius, y, cz + Math.sin(a) * radius)
      tmp.rotation.set(time * 0.5, a, 0)
      const s = 0.8 + 0.25 * Math.sin(time * 3 + i * 0.7)
      tmp.scale.set(s, s, s)
      tmp.updateMatrix(); m.setMatrixAt(i, tmp.matrix)
      if (t.ai_incident) col.set('#ff7a8a')
      else if (t.ai_paused) col.set('#3a4658')
      else { col.set('#6fd3ff'); col.multiplyScalar(0.45 + 0.55 * (t.ai_coverage ?? 1)) }
      m.setColorAt(i, col)
    }
    m.count = n; m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true
  })
  return (
    <group>
      <instancedMesh ref={ref} args={[geo, undefined, Math.max(1, n)]} frustumCulled={false} raycast={() => null}>
        <meshStandardMaterial emissive={'#ffffff'} emissiveIntensity={0.6} toneMapped={false} />
      </instancedMesh>
      <Text position={[-(t.r + 1.4), 0.05, 1.1 + 0.12 * n]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.34} color={t.ai_incident ? '#ff7a8a' : '#6fd3ff'} anchorX="center">
        {`${n} AI agent${n === 1 ? '' : 's'}${t.ai_incident ? ' · incident' : t.ai_paused ? ' · paused' : (t.ai_coverage ?? 1) < 0.8 ? ' · under-supervised' : ''}${t.supervisors ? ` · ${t.supervisors} sup.` : ''}`}
      </Text>
    </group>
  )
}

function TeamCluster({ t, world, xray, selected, diff, onClick, onHover, onOut }:
  { t: TeamFrame; world: WorldLabel; xray: XRay; selected: boolean; diff: number; onClick: () => void; onHover: (x: number, y: number) => void; onOut: () => void }) {
  const color = useMemo(() => deptColor(t.dept), [t.dept])
  const ring = useRef<THREE.Mesh>(null!)
  const stack = useRef<THREE.Mesh>(null!)
  const target = useRef(0)
  const backlog = t.backlog_months
  const queueH = Math.min(9, 0.15 + backlog * 2.2)
  const hot = backlog > 1
  useFrame((_, dt) => {
    target.current += (queueH - target.current) * Math.min(1, dt * 2.5)
    if (stack.current) { stack.current.scale.y = target.current; stack.current.position.y = target.current / 2 }
    if (ring.current) { const m = ring.current.material as THREE.MeshBasicMaterial; m.opacity = 0.25 + 0.5 * Math.max(0, t.management_load - 0.8) * (0.5 + 0.5 * Math.sin(performance.now() / 300)) }
  })
  const stackColor = hot ? WORK_HIGH : WORK
  const showQueue = xray === 'work' || xray === 'capacity' || xray === 'change' || xray === 'structure'
  const showMgmt = xray === 'structure' || xray === 'capacity' || xray === 'dependencies'
  return (
    <group position={[t.x, 0, t.z]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]} onClick={(e) => { e.stopPropagation(); onClick() }}
        onPointerMove={(e) => onHover(e.nativeEvent.clientX, e.nativeEvent.clientY)} onPointerOut={onOut}>
        <ringGeometry args={[t.r + 0.4, t.r + 0.55, 64]} />
        <meshBasicMaterial color={selected ? '#ffffff' : color} transparent opacity={selected ? 0.9 : 0.25} depthWrite={false} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.005, 0]} raycast={() => null}>
        <circleGeometry args={[t.r + 0.4, 48]} />
        <meshBasicMaterial color={xray === 'capacity' ? new THREE.Color().setHSL(0.6 - 0.6 * Math.min(1, Math.max(0, (t.workload - 0.5))), 0.8, 0.5)
          : xray === 'cost' ? budgetColor(t.budget_ratio ?? 0) : color}
          transparent opacity={xray === 'capacity' ? 0.18 : xray === 'cost' ? 0.24 : 0.06} depthWrite={false} />
      </mesh>
      {diff > 0.05 && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]} raycast={() => null}>
          <ringGeometry args={[t.r + 0.7, t.r + 0.7 + Math.min(3, diff), 64]} />
          <meshBasicMaterial color={'#ffb566'} transparent opacity={0.35} depthWrite={false} />
        </mesh>
      )}
      {showMgmt && (
        <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]} raycast={() => null}>
          <ringGeometry args={[0.5, 0.65, 32]} />
          <meshBasicMaterial color={t.management_load > 1.1 ? '#ff7a8a' : '#d9c7ff'} transparent opacity={0.3} depthWrite={false} />
        </mesh>
      )}
      {showQueue && (
        <group position={[t.r + 1.2, 0, 0]}>
          <mesh ref={stack} raycast={() => null}>
            <boxGeometry args={[0.55, 1, 0.55]} />
            <meshStandardMaterial color={stackColor} emissive={stackColor} emissiveIntensity={hot ? 1.2 : 0.5} transparent opacity={0.85} toneMapped={false} />
          </mesh>
          <Text position={[0, -0.25, 0.5]} fontSize={0.42} color={'#8b96ab'} anchorX="center" anchorY="top">{`${t.queue}`}</Text>
        </group>
      )}
      {xray === 'cost' && <CostTower t={t} />}
      {!!t.ai_agents && t.ai_agents > 0 && <AgentPool t={t} />}
      <Text position={[0, 0.05, -(t.r + 1.0)]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.62} color={selected ? '#ffffff' : '#c3cbe0'} anchorX="center" anchorY="middle" letterSpacing={0.08}>
        {t.name}
      </Text>
      <Text position={[0, 0.05, -(t.r + (xray === 'cost' ? 1.85 : 1.75))]} rotation={[-Math.PI / 2, 0, 0]} fontSize={xray === 'cost' ? 0.5 : 0.38}
        color={xray === 'cost' ? budgetCss(t.budget_ratio ?? 0) : '#5a6478'} anchorX="center" anchorY="middle">
        {xray === 'cost'
          ? `${kFmt(t.cost_month ?? 0)}/mo · ${Math.round((t.budget_ratio ?? 0) * 100)}% of budget${t.cost_per_hour != null ? ` · £${Math.round(t.cost_per_hour)}/h worked` : ''}`
          : `${t.headcount}${t.vacancies ? ` (+${t.vacancies} vacant)` : ''} · ${Math.round(t.workload * 100)}%${!t.accepting ? ' · closed' : ''}`}
      </Text>
    </group>
  )
}
