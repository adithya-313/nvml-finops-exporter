import { SimulationState, PresetScenario } from '../types'

interface Props {
  onSelect: (values: Partial<SimulationState>) => void
}

const presets: PresetScenario[] = [
  {
    name: 'normal',
    label: 'Normal Baseline',
    color: 'bg-emerald-600 hover:bg-emerald-500',
    values: { utilization: 80, vramRatio: 0.7, temperature: 65, powerDraw: 150, clockDrift: 10, packetDrop: 0 },
  },
  {
    name: 'zombie',
    label: 'Zombie GPU',
    color: 'bg-red-700 hover:bg-red-600',
    values: { utilization: 0, vramRatio: 0.95, temperature: 40, powerDraw: 30, clockDrift: 10, packetDrop: 0 },
  },
  {
    name: 'idle-burn',
    label: 'Idle-Burn',
    color: 'bg-orange-600 hover:bg-orange-500',
    values: { utilization: 0, vramRatio: 0.1, temperature: 60, powerDraw: 120, clockDrift: 10, packetDrop: 0 },
  },
  {
    name: 'time-desync',
    label: 'Time Desync',
    color: 'bg-yellow-600 hover:bg-yellow-500',
    values: { utilization: 80, vramRatio: 0.7, temperature: 65, powerDraw: 150, clockDrift: 85, packetDrop: 0 },
  },
  {
    name: 'flapping',
    label: 'Network Flapping',
    color: 'bg-purple-600 hover:bg-purple-500',
    values: { utilization: 80, vramRatio: 0.7, temperature: 65, powerDraw: 150, clockDrift: 10, packetDrop: 40 },
  },
]

export default function ScenarioPresets({ onSelect }: Props) {
  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        Scenario Presets
      </h2>
      <div className="flex flex-wrap gap-3">
        {presets.map((p) => (
          <button
            key={p.name}
            onClick={() => onSelect(p.values)}
            className={`px-4 py-2 rounded-md text-sm font-medium text-white transition-colors ${p.color}`}
          >
            {p.label}
          </button>
        ))}
      </div>
    </div>
  )
}
