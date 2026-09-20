import { useFrame } from '@react-three/fiber'
import { useMemo, useRef, useEffect } from 'react'
import * as THREE from 'three'
import type { Frame, EmployeeRow, WorldLabel, XRay } from '../lib/types'
import { useStore } from '../lib/store'
import { deptColor, STRESS } from './palette'

const tmp = new THREE.Object3D()
const col = new THREE.Color()

/** Employees as instanced luminous figures (capsule body + glow). State affects pulse, jitter, brightness, height. */
export function Employees({ frame, prev, world, offset, teamDept, xray, t01 }:
  { frame: Frame; prev: Frame | null; world: WorldLabel; offset: [number, number, number]; teamDept: Record<string, string>; xray: XRay; t01: number }) {
  const ref = useRef<THREE.InstancedMesh>(null!)
  const glow = useRef<THREE.InstancedMesh>(null!)
  const select = useStore((s) => s.select)
  const setHover = useStore((s) => s.set)
  const selection = useStore((s) => s.selection)
  const count = frame.employees.length
  const prevPos = useMemo(() => {
    const m = new Map<string, EmployeeRow>()
    prev?.employees.forEach((e) => m.set(e[0], e))
    return m
  }, [prev])
  const seeds = useMemo(() => frame.employees.map((e) => hash(e[0])), [frame])
  const geo = useMemo(() => new THREE.CapsuleGeometry(0.16, 0.34, 4, 8), [])
  const glowGeo = useMemo(() => new THREE.SphereGeometry(0.34, 10, 10), [])

  useEffect(() => { if (ref.current) ref.current.count = count; if (glow.current) glow.current.count = count }, [count])

  useFrame(({ clock }) => {
    const mesh = ref.current; const g = glow.current
    if (!mesh || !g) return
    const time = clock.getElapsedTime()
    frame.employees.forEach((e, i) => {
      const [id, team, x, z, workload, stress, morale, status, isMgr, behaviour] = e
      const roleKind = e[12]
      const p = prevPos.get(id)
      const px = p ? p[2] : x, pz = p ? p[3] : z
      const cx = px + (x - px) * ease(t01), cz = pz + (z - pz) * ease(t01)
      const s = seeds[i]
      const pulse = 1 + 0.06 * Math.sin(time * (1.2 + 2.4 * Math.max(0, workload - 0.8)) + s * 6.28)
      const jitter = Math.max(0, stress - 0.55) * 0.12
      const jx = jitter * Math.sin(time * 13 + s * 10), jz = jitter * Math.cos(time * 11 + s * 7)
      let y = 0.45 + (isMgr ? 0.25 : roleKind === 'supervisor' ? 0.12 : 0)
      let scale = (isMgr ? 1.25 : roleKind === 'supervisor' ? 1.1 : 1) * pulse
      let alpha = 1
      if (status === 'left') { y += 2.5 * t01; scale *= Math.max(0.05, 1 - t01); alpha = 1 - t01 }
      if (status === 'leaving') { y += 0.4 }
      if (e[11] > 0) scale *= 0.85
      tmp.position.set(offset[0] + cx + jx, offset[1] + y, offset[2] + cz + jz)
      tmp.scale.set(scale, scale * (1 + 0.5 * (workload > 1.15 ? 0.3 : 0)), scale)
      tmp.rotation.set(0, 0, 0)
      tmp.updateMatrix()
      mesh.setMatrixAt(i, tmp.matrix)
      // colour: department hue, shifted toward stress red; dim when inactive/low morale
      col.copy(deptColor(teamDept[team] || ''))
      if (xray === 'capacity') { col.setHSL(0.6 - 0.6 * clamp01((workload - 0.5) / 1.0), 0.8, 0.55) }
      else if (xray === 'change') { col.set(behaviour === 'working' ? '#4d5a70' : '#ffb566') }
      else { col.lerp(STRESS, clamp01((stress - 0.45) * 1.4)); if (roleKind === 'supervisor') col.lerp(new THREE.Color('#6fd3ff'), 0.55) }
      const bright = 0.55 + 0.45 * morale
      col.multiplyScalar(bright * alpha)
      if (selection && selection.kind === 'employee' && selection.id === id && selection.world === world) col.set('#ffffff')
      mesh.setColorAt(i, col)
      // glow
      const gs = scale * (0.9 + 0.5 * Math.max(0, workload - 0.9)) * alpha
      tmp.position.y = offset[1] + y + 0.05
      tmp.scale.set(gs, gs, gs)
      tmp.updateMatrix()
      g.setMatrixAt(i, tmp.matrix)
      col.multiplyScalar(0.35)
      g.setColorAt(i, col)
    })
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    g.instanceMatrix.needsUpdate = true
    if (g.instanceColor) g.instanceColor.needsUpdate = true
  })

  return (
    <group>
      <instancedMesh ref={ref} args={[geo, undefined, Math.max(1, count)]} frustumCulled={false}
        onClick={(ev) => { ev.stopPropagation(); const i = ev.instanceId; if (i != null && frame.employees[i]) select({ kind: 'employee', id: frame.employees[i][0], world }) }}
        onPointerMove={(ev) => { const i = ev.instanceId; if (i != null && frame.employees[i]) setHover({ hover: { kind: 'employee', id: frame.employees[i][0], world, x: ev.nativeEvent.clientX, y: ev.nativeEvent.clientY } }) }}
        onPointerOut={() => setHover({ hover: null })}>
        <meshStandardMaterial roughness={0.35} metalness={0.1} emissive={'#ffffff'} emissiveIntensity={0.25} toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={glow} args={[glowGeo, undefined, Math.max(1, count)]} frustumCulled={false} raycast={() => null}>
        <meshBasicMaterial transparent opacity={0.22} depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
      </instancedMesh>
    </group>
  )
}

function hash(s: string) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return (h % 1000) / 1000 }
function ease(t: number) { return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t }
function clamp01(x: number) { return Math.max(0, Math.min(1, x)) }
