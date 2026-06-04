export interface SimulationState {
  utilization: number
  vramRatio: number
  temperature: number
  powerDraw: number
  clockDrift: number
  packetDrop: number
}

export type CircuitBreakerState = 'CLOSED' | 'HALF_OPEN' | 'OPEN'

export interface PresetScenario {
  name: string
  label: string
  values: Partial<SimulationState>
  color: string
}
