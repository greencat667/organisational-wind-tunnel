export type EmployeeRow = [string, string, number, number, number, number, number, string, number, string, number, number]
// [id, team, x, z, workload, stress, morale, status, is_manager, behaviour, tasks, onboarding]

export interface TeamFrame {
  id: string; name: string; dept: string; x: number; z: number; r: number; queue: number; backlog_months: number; workload: number
  headcount: number; vacancies: number; management_load: number; morale: number; accepting: boolean; automation: number; function: string; ai_agents?: number
}
export interface Flow { item: string; from: string; to: string; kind: string; priority: number; transfer?: boolean }
export interface InfoFlow { packet: string; from: string; to: string; kind: string }
export interface Frame {
  month: number; label: string; employees: EmployeeRow[]; teams: TeamFrame[]; flows: Flow[]; info_flows: InfoFlow[]
  departments: { id: string; name: string; x: number; z: number; r: number; hiring_frozen: boolean }[]
  new_events: SimEvent[]
}
export interface SimEvent {
  id: number; month: number; kind: string; actor: string | null; action: string; entities: string[]; description: string
  significant: boolean; emergent: boolean; causes: number[]; engine?: string | null; date?: string
}
export interface Metrics { [k: string]: any; month: number; label: string; teams: Record<string, any> }
export interface Status {
  id: string; template: string; seed: number; engine: string; engine_info: any; engine_stats: any; engine_error: string | null
  month: number; label: string; forked: boolean; fork_month: number | null; plan: any; intervention_text: string; playing: boolean; speed: number
  headcount: number; mean_step_ms: number | null
}
export interface Structure {
  template: string; seed: number; departments: any[]; teams: any[]; employees: any[]
  processes: { id: string; name: string; kind: string; arrival_rate: number; frontline: boolean; origin: string | null; stages: { team_id: string; skill: string; hours: number; approval: boolean }[] }[]
  layout: { teams: Record<string, [number, number, number]>; departments: Record<string, [number, number, number]> }
}
export type WorldLabel = 'baseline' | 'intervention'
export type XRay = 'structure' | 'work' | 'information' | 'capacity' | 'cost' | 'change' | 'dependencies'
export type ViewMode = 'single' | 'split' | 'difference'
