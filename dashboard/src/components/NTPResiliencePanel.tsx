import { CircuitBreakerState } from '../types'

interface Props {
  clockDrift: number
  circuitBreaker: CircuitBreakerState
  isTimeDrift: boolean
}

const cbConfig: Record<CircuitBreakerState, { color: string; bg: string; label: string }> = {
  CLOSED: {
    color: 'text-emerald-400',
    bg: 'bg-emerald-900/30 border-emerald-700/50',
    label: 'CLOSED — Normal Operation',
  },
  HALF_OPEN: {
    color: 'text-yellow-400',
    bg: 'bg-yellow-900/30 border-yellow-700/50',
    label: 'HALF_OPEN — Recovery Attempt',
  },
  OPEN: {
    color: 'text-red-400',
    bg: 'bg-red-900/30 border-red-700/50',
    label: 'OPEN — Requests Blocked',
  },
}

export default function NTPResiliencePanel({ clockDrift, circuitBreaker, isTimeDrift }: Props) {
  const cb = cbConfig[circuitBreaker]

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        NTP &amp; Resilience
      </h2>
      <div className="space-y-5">
        <div>
          <div className="text-xs text-gray-500 mb-1">Clock Drift</div>
          <div
            className={`text-xl font-mono font-bold ${isTimeDrift ? 'text-red-400' : 'text-gray-200'}`}
          >
            {clockDrift >= 0 ? '+' : ''}
            {clockDrift} ms
          </div>
          {isTimeDrift && (
            <div className="mt-1.5 inline-block bg-red-900/30 border border-red-700/50 rounded px-2 py-0.5">
              <span className="text-xs text-red-400 font-semibold">⚠ CRITICAL TIME DRIFT</span>
            </div>
          )}
        </div>
        <div>
          <div className="text-xs text-gray-500 mb-1.5">Circuit Breaker</div>
          <div className={`inline-block px-3 py-1.5 rounded-md border text-sm font-semibold ${cb.bg} ${cb.color}`}>
            {cb.label}
          </div>
        </div>
      </div>
    </div>
  )
}
