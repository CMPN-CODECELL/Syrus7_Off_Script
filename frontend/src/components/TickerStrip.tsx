'use client'
import { useState, useEffect } from 'react'

export default function TickerStrip() {
  const [data, setData] = useState<{prices: Record<string, number>}>({ prices: {} })

  useEffect(() => {
    // Fetch snapshot from backend (which pulls from Redis)
    const fetchSnapshot = async () => {
      try {
        const res = await fetch('http://localhost:8000/chat/price-snapshot')
        const json = await res.json()
        if (json.prices) setData(json)
      } catch (e) {
        console.error('Ticker failed')
      }
    }
    fetchSnapshot()
    const timer = setInterval(fetchSnapshot, 10000) // Update tape every 10s
    return () => clearInterval(timer)
  }, [])

  const entries = Object.entries(data.prices)
  if (entries.length === 0) return null

  // Duplicate for seamless infinite scroll
  const tape = [...entries, ...entries, ...entries]

  return (
    <div className="ticker-wrap border-b shrink-0 py-1.5"
         style={{ borderColor: 'var(--border)', background: 'var(--surface-2)' }}>
      <div className="ticker-inner">
        {tape.map(([symbol, price], idx) => (
          <div key={`${symbol}-${idx}`} className="inline-flex items-center gap-2 px-6 border-r text-xs font-mono font-medium" style={{ borderColor: 'var(--border)' }}>
            <span className="muted-text">{symbol.replace('.NS', '')}</span>
            <span style={{ color: 'var(--text)' }}>₹{price.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
