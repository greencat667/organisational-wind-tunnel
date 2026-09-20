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
