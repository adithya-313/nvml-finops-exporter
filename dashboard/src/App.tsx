import { useState, useMemo } from 'react'
import { SimulationState } from './types'
import SimulationControlPanel from './components/SimulationControlPanel'
import ScenarioPresets from './components/ScenarioPresets'
import TelemetryPanel from './components/TelemetryPanel'
import MahalanobisPanel from './components/MahalanobisPanel'
import NTPResiliencePanel from './components/NTPResiliencePanel'
import FinancialLedgerPanel from './components/FinancialLedgerPanel'

const NORMAL_BASELINE = { util: 80, vram: 0.7, temp: 65, power: 150 }

function calcMahalanobis(s: SimulationState): number {
  const std = { util: 20, vram: 0.15, temp: 10, power: 30 }
  const du = (s.utilization - NORMAL_BASELINE.util) / std.util
  const dv = (s.vramRatio - NORMAL_BASELINE.vram) / std.vram
  const dt = (s.temperature - NORMAL_BASELINE.temp) / std.temp
  const dp = (s.powerDraw - NORMAL_BASELINE.power) / std.power
  return Math.sqrt(du * du + dv * dv + dt * dt + dp * dp)
}

export default function App() {
  const [state, setState] = useState<SimulationState>({
    utilization: 80,
    vramRatio: 0.7,
    temperature: 65,
    powerDraw: 150,
    clockDrift: 10,
    packetDrop: 0,
  })

  const dM = useMemo(() => calcMahalanobis(state), [state])
  const circuitBreaker = useMemo(() => {
    if (state.packetDrop < 10) return 'CLOSED' as const
    if (state.packetDrop > 30) return 'OPEN' as const
    return 'HALF_OPEN' as const
  }, [state.packetDrop])

  const isTimeDrift = Math.abs(state.clockDrift) > 50
  const isZombie = state.utilization < 5 && state.vramRatio > 0.9
  const isIdleBurn = state.utilization < 5 && state.powerDraw > 50
  const wastedDaily = isZombie || isIdleBurn ? 24.0 : 0

  return (
    <div className="min-h-screen bg-gray-950 text-gray-100">
      <header className="border-b border-gray-800 px-6 py-4 bg-gray-900/50 backdrop-blur-sm sticky top-0 z-10">
        <div className="max-w-6xl mx-auto">
          <h1 className="text-xl font-bold tracking-tight">nvml-finops-dashboard</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            GPU Telemetry &middot; Mahalanobis Anomaly Detection &middot; FinOps Management
          </p>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-6 space-y-6">
        <SimulationControlPanel
          state={state}
          onChange={(partial) => setState((prev) => ({ ...prev, ...partial }))}
        />
        <ScenarioPresets onSelect={(values) => setState((prev) => ({ ...prev, ...values }))} />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <TelemetryPanel state={state} />
          <MahalanobisPanel dM={dM} />
          <NTPResiliencePanel
            clockDrift={state.clockDrift}
            circuitBreaker={circuitBreaker}
            isTimeDrift={isTimeDrift}
          />
          <FinancialLedgerPanel
            isZombie={isZombie}
            isIdleBurn={isIdleBurn}
            wastedDaily={wastedDaily}
          />
        </div>
      </main>
    </div>
  )
}
