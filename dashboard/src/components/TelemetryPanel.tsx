import { SimulationState } from '../types'

interface Props {
  state: SimulationState
}

interface MetricDef {
  label: string
  raw: (s: SimulationState) => number
  display: (v: number) => string
  unit: string
  color: (s: SimulationState) => string
  barPct: (s: SimulationState) => number
}

const metrics: MetricDef[] = [
  {
    label: 'GPU Utilization',
    raw: (s) => s.utilization,
    display: (v) => `${v}`,
    unit: '%',
    color: (s) => (s.utilization > 90 ? 'text-red-400' : 'text-emerald-400'),
    barPct: (s) => s.utilization,
  },
  {
    label: 'VRAM Memory Ratio',
    raw: (s) => s.vramRatio,
    display: (v) => `${(v * 100).toFixed(0)}`,
    unit: '%',
    color: () => 'text-blue-400',
    barPct: (s) => s.vramRatio * 100,
  },
  {
    label: 'Core Temperature',
    raw: (s) => s.temperature,
    display: (v) => `${v}`,
    unit: '°C',
    color: (s) => (s.temperature > 85 ? 'text-red-400' : 'text-orange-400'),
    barPct: (s) => ((s.temperature - 30) / 70) * 100,
  },
  {
    label: 'Power Draw',
    raw: (s) => s.powerDraw,
    display: (v) => `${v}`,
    unit: 'W',
    color: (s) => (s.powerDraw > 200 ? 'text-red-400' : 'text-yellow-400'),
    barPct: (s) => ((s.powerDraw - 20) / 230) * 100,
  },
]

export default function TelemetryPanel({ state }: Props) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        Raw Telemetry Stream
      </h2>
      <div className="grid grid-cols-2 gap-4">
        {metrics.map((m) => {
          const rawVal = m.raw(state)
          return (
            <div key={m.label} className="bg-gray-800 rounded-lg p-4">
              <div className="text-xs text-gray-500 mb-1">{m.label}</div>
              <div className={`text-2xl font-bold font-mono ${m.color(state)}`}>
                {m.display(rawVal)}
                <span className="text-sm ml-0.5 text-gray-400">{m.unit}</span>
              </div>
              <div className="mt-2 w-full h-1.5 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-150 ${m.color(state).replace('text-', 'bg-')}`}
                  style={{ width: `${Math.min(100, Math.max(0, m.barPct(state)))}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
