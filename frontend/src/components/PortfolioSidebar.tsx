'use client'
import { useState, useEffect } from 'react'

export default function PortfolioSidebar() {
  const [account, setAccount] = useState<any>(null)
  const [positions, setPositions] = useState<any[]>([])

  useEffect(() => {
    // In a real app this would poll or use WebSockets. For demo, fetch every 5s.
    const fetchData = async () => {
      try {
        const accRes = await fetch('http://localhost:8001/account')
        setAccount(await accRes.json())
        const posRes = await fetch('http://localhost:8001/positions')
        const posData = await posRes.json()
        setPositions(posData.positions)
      } catch (e) {
        console.error('Failed to fetch portfolio')
      }
    }
    fetchData()
    const timer = setInterval(fetchData, 5000)
    return () => clearInterval(timer)
  }, [])

  if (!account) return <div className="p-6 text-sm muted-text">Loading portfolio...</div>

  return (
    <div className="p-4 space-y-6">
      {/* Account Overview */}
      <div className="syrus-surface-2 p-4">
        <h4 className="text-xs font-bold muted-text uppercase tracking-widest mb-3">Portfolio Value</h4>
        <p className="text-2xl font-mono font-bold tracking-tight accent-text">
          ₹{account.total_value.toLocaleString('en-IN')}
        </p>
        <div className="flex justify-between mt-4 text-xs">
          <span className="muted-text">Available Funds</span>
          <span className="font-mono">₹{account.funds_available.toLocaleString('en-IN')}</span>
        </div>
        <div className="flex justify-between mt-1 text-xs">
          <span className="muted-text">Margin Used</span>
          <span className="font-mono">₹{account.funds_used.toLocaleString('en-IN')}</span>
        </div>
      </div>

      {/* Positions List */}
      <div>
        <h4 className="text-xs font-bold muted-text uppercase tracking-widest mb-3 px-1">Open Positions</h4>
        <div className="space-y-2">
          {positions.map((pos: any) => (
            <div key={pos.symbol} className="syrus-surface-2 p-3 text-sm">
              <div className="flex justify-between items-center mb-1">
                <span className="font-bold">{pos.symbol}</span>
                <span className="font-mono font-semibold"
                      style={{ color: pos.pnl >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                  {pos.pnl >= 0 ? '+' : ''}₹{pos.pnl.toLocaleString('en-IN')}
                </span>
              </div>
              <div className="flex justify-between text-xs muted-text font-mono">
                <span>{pos.quantity} @ {pos.avg_price.toFixed(2)}</span>
                <span>LTP: {pos.ltp.toFixed(2)}</span>
              </div>
            </div>
          ))}
          {positions.length === 0 && (
            <p className="text-xs muted-text text-center py-4">No open positions.</p>
          )}
        </div>
      </div>
    </div>
  )
}
