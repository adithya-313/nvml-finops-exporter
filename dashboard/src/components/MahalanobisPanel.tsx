interface Props {
  dM: number
}

export default function MahalanobisPanel({ dM }: Props) {
  const isAnomaly = dM > 3.5

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        ML Engine: Mahalanobis Distance
      </h2>
      <div className="space-y-4">
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-bold font-mono tracking-tight">{dM.toFixed(2)}</span>
          <span className="text-sm text-gray-500">
            D<sub>M</sub>
          </span>
        </div>

        {isAnomaly ? (
          <div className="animate-pulse-red bg-red-900/40 border border-red-700 rounded-lg px-4 py-3">
            <span className="text-red-400 font-bold text-sm">
              ⚠ CRITICAL ANOMALY: MULTI-VARIATE DEVIATION
            </span>
          </div>
        ) : (
          <div className="bg-gray-800 rounded-lg px-4 py-3">
            <span className="text-emerald-400 font-semibold text-sm">✓ System Nominal</span>
            {dM > 2.5 && (
              <span className="text-yellow-400 text-sm ml-2">(Elevated — approaching threshold)</span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
