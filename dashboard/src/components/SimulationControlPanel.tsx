import { SimulationState } from '../types'

interface Props {
  state: SimulationState
  onChange: (partial: Partial<SimulationState>) => void
}

const sliders: {
  key: keyof SimulationState
  label: string
  min: number
  max: number
  step: number
  unit: string
}[] = [
  { key: 'utilization', label: 'GPU Utilization', min: 0, max: 100, step: 1, unit: '%' },
  { key: 'vramRatio', label: 'VRAM Memory Ratio', min: 0, max: 1, step: 0.01, unit: '' },
  { key: 'temperature', label: 'Core Temperature', min: 30, max: 100, step: 1, unit: '°C' },
  { key: 'powerDraw', label: 'Power Draw', min: 20, max: 250, step: 1, unit: 'W' },
  { key: 'clockDrift', label: 'Host Clock Drift', min: -100, max: 100, step: 1, unit: 'ms' },
  { key: 'packetDrop', label: 'Network Packet Drop', min: 0, max: 100, step: 1, unit: '%' },
]

export default function SimulationControlPanel({ state, onChange }: Props) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        Simulation Control Panel
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {sliders.map(({ key, label, min, max, step, unit }) => (
          <div key={key}>
            <div className="flex justify-between items-baseline mb-1">
              <label className="text-sm text-gray-400">{label}</label>
              <span className="font-mono text-sm text-cyan-400 font-semibold">
                {state[key]}{unit}
              </span>
            </div>
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              value={state[key]}
              onChange={(e) => onChange({ [key]: parseFloat(e.target.value) })}
              className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-cyan-500"
            />
            <div className="flex justify-between text-xs text-gray-600 mt-0.5">
              <span>{min}{unit}</span>
              <span>{max}{unit}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
