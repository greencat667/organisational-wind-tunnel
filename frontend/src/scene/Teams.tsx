import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import { Html, Text } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import type { Frame, WorldLabel, XRay, TeamFrame } from '../lib/types'
import { useStore } from '../lib/store'
import { deptColor, WORK, WORK_HIGH } from './palette'

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
      {frame.teams.map((t) => (
        <TeamCluster key={t.id} t={t} world={world} xray={xray} selected={!!selection && selection.kind === 'team' && selection.id === t.id && selection.world === world}
          diff={diffTeams ? diffTeams[t.id] || 0 : 0}
          onClick={() => select({ kind: 'team', id: t.id, world })}
          onHover={(x, y) => setHover({ hover: { kind: 'team', id: t.id, world, x, y } })} onOut={() => setHover({ hover: null })} />
      ))}
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
        <meshBasicMaterial color={xray === 'capacity' ? new THREE.Color().setHSL(0.6 - 0.6 * Math.min(1, Math.max(0, (t.workload - 0.5))), 0.8, 0.5) : color}
          transparent opacity={xray === 'capacity' ? 0.18 : 0.06} depthWrite={false} />
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
      {!!t.ai_agents && t.ai_agents > 0 && (
        <mesh position={[-(t.r + 1.0), 0.6, 0]} raycast={() => null}>
          <octahedronGeometry args={[0.35 + 0.08 * Math.min(8, t.ai_agents), 0]} />
          <meshStandardMaterial color={'#6fd3ff'} emissive={'#6fd3ff'} emissiveIntensity={0.8} wireframe toneMapped={false} />
        </mesh>
      )}
      <Text position={[0, 0.05, -(t.r + 1.0)]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.62} color={selected ? '#ffffff' : '#c3cbe0'} anchorX="center" anchorY="middle" letterSpacing={0.08}>
        {t.name}
      </Text>
      <Text position={[0, 0.05, -(t.r + 1.75)]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.38} color={'#5a6478'} anchorX="center" anchorY="middle">
        {`${t.headcount}${t.vacancies ? ` (+${t.vacancies} vacant)` : ''} · ${Math.round(t.workload * 100)}%${!t.accepting ? ' · closed' : ''}`}
      </Text>
    </group>
  )
}
