interface Props {
  isZombie: boolean
  isIdleBurn: boolean
  wastedDaily: number
}

export default function FinancialLedgerPanel({ isZombie, isIdleBurn, wastedDaily }: Props) {
  const hasWaste = isZombie || isIdleBurn

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
        Financial Ledger
      </h2>
      <div className="space-y-4">
        <div className="flex justify-between items-center pb-3 border-b border-gray-800">
          <span className="text-sm text-gray-400">Base GPU Rate</span>
          <span className="font-mono text-gray-200 font-semibold">$1.00 / hr</span>
        </div>

        {isZombie && (
          <div className="flex items-start gap-2">
            <span className="text-red-400 text-sm">⚠</span>
            <span className="text-xs text-red-400/90">
              Zombie GPU Detected — VRAM allocated but no compute utilization
            </span>
          </div>
        )}
        {isIdleBurn && (
          <div className="flex items-start gap-2">
            <span className="text-red-400 text-sm">⚠</span>
            <span className="text-xs text-red-400/90">
              Idle-Burn Detected — power being drawn with no compute work
            </span>
          </div>
        )}

        {hasWaste ? (
          <div className="bg-red-900/20 border border-red-800/50 rounded-lg p-4">
            <div className="text-xs text-red-300 uppercase tracking-wider font-semibold">
              Wasted Spend Rate
            </div>
            <div className="text-3xl font-bold text-red-400 font-mono mt-1">
              ${wastedDaily.toFixed(2)}
              <span className="text-sm font-normal text-red-300 ml-1">/ day</span>
            </div>
            <div className="text-xs text-red-400/70 mt-1">
              ${(wastedDaily / 24).toFixed(2)} / hr &middot; $
              {(wastedDaily * 30).toFixed(0)} / month (30d)
            </div>
          </div>
        ) : (
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-xs text-gray-500 uppercase tracking-wider">Status</div>
            <div className="text-emerald-400 font-semibold mt-1">
              ✓ No Wasted Spend Detected
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
