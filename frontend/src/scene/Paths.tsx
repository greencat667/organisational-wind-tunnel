import { useMemo } from 'react'
import * as THREE from 'three'
import type { Structure, XRay } from '../lib/types'
import { Line } from '@react-three/drei'

/** Formal process paths (team -> team) as faint arcs; weight = monthly volume. Dependencies mode highlights critical links. */
export function ProcessPaths({ structure, offset, xray, teamPos, network }:
  { structure: Structure; offset: [number, number, number]; xray: XRay; teamPos: Record<string, [number, number]>; network?: { a: string; b: string; w: number }[] }) {
  const edges = useMemo(() => {
    const m = new Map<string, { a: string; b: string; w: number }>()
    for (const p of structure.processes) {
      const tids = p.stages.map((s) => s.team_id)
      for (let i = 0; i + 1 < tids.length; i++) {
        if (tids[i] === tids[i + 1]) continue
        const k = `${tids[i]}>${tids[i + 1]}`
        const e = m.get(k) || { a: tids[i], b: tids[i + 1], w: 0 }
        e.w += p.arrival_rate
        m.set(k, e)
      }
    }
    return [...m.values()]
  }, [structure])
  const maxW = Math.max(1, ...edges.map((e) => e.w))
  const show = xray !== 'information' && xray !== 'cost'
  const showInformal = xray === 'information' && network
  return (
    <group position={offset}>
      {show && edges.map((e) => {
        const a = teamPos[e.a], b = teamPos[e.b]
        if (!a || !b) return null
        const pts = arc(a, b, 0.25 + 1.5 * (e.w / maxW))
        const critical = xray === 'dependencies' && e.w / maxW > 0.5
        return <Line key={e.a + e.b} points={pts} color={critical ? '#ff7a8a' : '#6fd3ff'} transparent opacity={critical ? 0.7 : 0.08 + 0.25 * (e.w / maxW)} lineWidth={critical ? 2 : 1} />
      })}
      {showInformal && network!.map((e) => {
        const a = teamPos[e.a], b = teamPos[e.b]
        if (!a || !b) return null
        return <Line key={'i' + e.a + e.b} points={arc(a, b, 0.6)} color={'#ff9cc7'} transparent opacity={Math.min(0.9, 0.15 + e.w / 10)} lineWidth={1 + Math.min(3, e.w / 4)} dashed dashSize={0.4} gapSize={0.25} />
      })}
    </group>
  )
}

function arc(a: [number, number], b: [number, number], h: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = []
  for (let i = 0; i <= 24; i++) {
    const t = i / 24
    pts.push(new THREE.Vector3(a[0] + (b[0] - a[0]) * t, 0.3 + Math.sin(Math.PI * t) * h, a[1] + (b[1] - a[1]) * t))
  }
  return pts
}
