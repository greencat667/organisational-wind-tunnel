import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { Frame, Structure, XRay } from '../lib/types'
import { INFO, WORK, WORK_HIGH } from './palette'

const tmp = new THREE.Object3D()
const col = new THREE.Color()

/** Work items travelling along arcs between team clusters during the month (t01 = progress through the month). */
export function Flows({ frame, offset, xray, t01, teamPos }: { frame: Frame; offset: [number, number, number]; xray: XRay; t01: number; teamPos: Record<string, [number, number]> }) {
  const showWork = xray === 'work' || xray === 'structure' || xray === 'change' || xray === 'capacity'
  const showInfo = xray === 'information' || xray === 'structure'
  const flows = useMemo(() => (showWork ? frame.flows : []).slice(0, 300).map((f, i) => ({ ...f, phase: hash(f.item) * 0.6, lift: 1.2 + 1.8 * hash(f.item + 'l') })), [frame, showWork])
  const infos = useMemo(() => (showInfo ? frame.info_flows : []).slice(0, 200).map((f) => ({ ...f, phase: hash(f.packet + f.to) * 0.6 })), [frame, showInfo])
  const wref = useRef<THREE.InstancedMesh>(null!)
  const iref = useRef<THREE.InstancedMesh>(null!)
  const geo = useMemo(() => new THREE.SphereGeometry(0.13, 8, 8), [])
  const igeo = useMemo(() => new THREE.SphereGeometry(0.07, 6, 6), [])

  useFrame(() => {
    const m = wref.current
    if (m) {
      flows.forEach((f, i) => {
        const a = teamPos[f.from], b = teamPos[f.to]
        if (!a || !b) { tmp.scale.set(0, 0, 0); tmp.updateMatrix(); m.setMatrixAt(i, tmp.matrix); return }
        const t = clamp01((t01 - f.phase) / 0.4)
        const x = a[0] + (b[0] - a[0]) * t, z = a[1] + (b[1] - a[1]) * t
        const y = 0.6 + Math.sin(Math.PI * t) * f.lift
        const vis = t > 0 && t < 1 ? 1 : 0
        tmp.position.set(offset[0] + x, offset[1] + y, offset[2] + z)
        const s = vis * (f.priority === 1 ? 1.5 : f.priority === 2 ? 1.1 : 0.8) * (f.transfer ? 1.4 : 1)
        tmp.scale.set(s, s, s)
        tmp.updateMatrix()
        m.setMatrixAt(i, tmp.matrix)
        col.copy(f.transfer ? WORK_HIGH : WORK)
        m.setColorAt(i, col)
      })
      m.count = flows.length
      m.instanceMatrix.needsUpdate = true
      if (m.instanceColor) m.instanceColor.needsUpdate = true
    }
    const im = iref.current
    if (im) {
      infos.forEach((f, i) => {
        // info pulses travel between employees; we only know team positions of holders cheaply, so use employee positions if present
        const a = empPos.get(f.from), b = empPos.get(f.to)
        if (!a || !b) { tmp.scale.set(0, 0, 0); tmp.updateMatrix(); im.setMatrixAt(i, tmp.matrix); return }
        const t = clamp01((t01 - f.phase) / 0.4)
        const x = a[0] + (b[0] - a[0]) * t, z = a[1] + (b[1] - a[1]) * t
        const y = 0.9 + Math.sin(Math.PI * t) * 0.8
        tmp.position.set(offset[0] + x, offset[1] + y, offset[2] + z)
        const s = t > 0 && t < 1 ? 1 : 0
        tmp.scale.set(s, s, s)
        tmp.updateMatrix()
        im.setMatrixAt(i, tmp.matrix)
        im.setColorAt(i, f.kind === 'rumour' ? col.set('#ff9cc7') : col.copy(INFO))
      })
      im.count = infos.length
      im.instanceMatrix.needsUpdate = true
      if (im.instanceColor) im.instanceColor.needsUpdate = true
    }
  })
  const empPos = useMemo(() => { const m = new Map<string, [number, number]>(); frame.employees.forEach((e) => m.set(e[0], [e[2], e[3]])); return m }, [frame])
  return (
    <group>
      <instancedMesh ref={wref} args={[geo, undefined, Math.max(1, flows.length)]} frustumCulled={false} raycast={() => null}>
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={iref} args={[igeo, undefined, Math.max(1, infos.length)]} frustumCulled={false} raycast={() => null}>
        <meshBasicMaterial toneMapped={false} transparent opacity={0.9} />
      </instancedMesh>
    </group>
  )
}

function hash(s: string) { let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0; return (h % 1000) / 1000 }
function clamp01(x: number) { return Math.max(0, Math.min(1, x)) }
