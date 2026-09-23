import * as THREE from 'three'
export const DEPT_COLORS: Record<string, string> = {
  executive: '#d9c7ff', finance: '#7fa7ff', operations: '#6fd3ff', income: '#ffb566', fundraising: '#ffb566', communications: '#ff9c7a',
  programmes: '#7fe0b0', programme_delivery: '#7fe0b0', technology: '#b3a4ff', people: '#ffd27a', policy: '#a3ffe0', campaigns: '#ff8ab0',
  supporter_services: '#9cf0ff',
}
export function deptColor(id: string): THREE.Color {
  return new THREE.Color(DEPT_COLORS[id] || '#9aa8c4')
}
export const BASELINE = new THREE.Color('#7fa7ff')
export const INTERVENTION = new THREE.Color('#ffb566')
export const WORK = new THREE.Color('#ffd27a')
export const WORK_HIGH = new THREE.Color('#ff7a8a')
export const INFO = new THREE.Color('#6fd3ff')
export const STRESS = new THREE.Color('#ff7a8a')
export const CALM = new THREE.Color('#9fd4ff')

// cost view. Budget colours follow the model's own rule: a department freezes hiring when projected spend passes 102%
// of budget, so amber = getting close (from 90%), red = past the freeze line.
export const COST_PAY = new THREE.Color('#c3cbe0')
export const COST_OVERTIME = new THREE.Color('#ffb566')
export const COST_AI = new THREE.Color('#6fd3ff')
const UNDER = new THREE.Color('#7fe0b0'), NEAR = new THREE.Color('#ffb566'), OVER = new THREE.Color('#ff7a8a')
export function budgetColor(ratio: number): THREE.Color {
  if (ratio <= 0.9) return UNDER.clone()
  if (ratio <= 1.02) return UNDER.clone().lerp(NEAR, (ratio - 0.9) / 0.12)
  return NEAR.clone().lerp(OVER, Math.min(1, (ratio - 1.02) / 0.1))
}
export function budgetCss(ratio: number): string { return '#' + budgetColor(ratio).getHexString() }
/** £k with one decimal under £100k: 29986 → "£30.0k". */
export function kFmt(v: number): string { return v >= 100000 ? `£${Math.round(v / 1000)}k` : `£${(v / 1000).toFixed(1)}k` }
