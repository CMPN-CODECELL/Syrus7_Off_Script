'use client'
import { useEffect, useState } from 'react'
import { Activity, ArrowUpRight, BarChart3, Search } from 'lucide-react'

type Point = { time: string; price: number }
type History = { symbol: string; provider: string; mode: string; points: Point[] }
const API = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000'
const ranges = [{ label: '1D', days: 1 }, { label: '1W', days: 7 }, { label: '1M', days: 30 }, { label: '3M', days: 90 }]

function PriceChart({ points }: { points: Point[] }) {
  const width = 760, height = 210, padX = 8, padY = 16
  const values = points.map(p => Number(p.price)).filter(Number.isFinite)
  if (values.length < 2) return <div className="chart-empty"><BarChart3 size={21}/><span>Chart appears as the selected feed records price updates.</span></div>
  const min = Math.min(...values), max = Math.max(...values), span = max - min || Math.max(max * .005, 1)
  const coords = values.map((v, i) => `${padX + (i / (values.length - 1)) * (width - 2 * padX)},${height - padY - ((v - min) / span) * (height - 2 * padY)}`)
  const last = coords[coords.length - 1].split(',')
  return <svg className="price-chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Price history line chart" preserveAspectRatio="none">
    {[0, 1, 2, 3].map(i => <line key={i} x1="0" x2={width} y1={padY + i * (height - 2 * padY) / 3} y2={padY + i * (height - 2 * padY) / 3} className="chart-grid-line"/>)}
    <polyline points={coords.join(' ')} className="chart-line"/>
    <circle cx={last[0]} cy={last[1]} r="4" className="chart-dot"/>
  </svg>
}

export default function MarketWatch({ onAskPrice }: { onAskPrice: (symbol: string) => void }) {
  const [snapshot, setSnapshot] = useState<Record<string, number>>({})
  const [sources, setSources] = useState<Record<string, string>>({})
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState('NIFTY 50')
  const [range, setRange] = useState(30)
  const [history, setHistory] = useState<History | null>(null)
  const [loading, setLoading] = useState(true)
  const [chartLoading, setChartLoading] = useState(false)
  const [chartError, setChartError] = useState('')
  const [error, setError] = useState('')
  const refresh = async () => {
    try { const r = await fetch(`${API}/chat/price-snapshot`); if (!r.ok) throw new Error('Quote service is unavailable.'); const d = await r.json(); const next = d.prices || {}; setSnapshot(next); setSources(d.sources || {}); setSelected(current => current === 'NIFTY 50' && !next['NIFTY 50'] && Object.keys(next).length ? Object.keys(next)[0] : current); setError('') }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load quotes.') }
    finally { setLoading(false) }
  }
  useEffect(() => { refresh(); const t = setInterval(refresh, 15000); return () => clearInterval(t) }, [])
  useEffect(() => {
    let active = true
    setChartLoading(true)
    fetch(`${API}/market/history/${encodeURIComponent(selected)}?days=${range}`)
      .then(async r => { if (!r.ok) throw new Error('Chart data is unavailable.'); return r.json() })
      .then(d => { if (active) { setHistory(d); setChartError('') } })
      .catch(e => { if (active) { setHistory(null); setChartError(e instanceof Error ? e.message : 'Chart data is unavailable.') } })
      .finally(() => { if (active) setChartLoading(false) })
    return () => { active = false }
  }, [selected, range])
  const shown = Object.entries(snapshot)
  const submit = (e: React.FormEvent) => { e.preventDefault(); const value = search.trim().toUpperCase().replace(/\.NS$/, ''); if (!value) return; setSelected(value); onAskPrice(value); setSearch('') }
  const chartPoints = history?.points || []
  const source = history?.provider === 'yahoo_finance' ? 'Yahoo Finance · may be delayed' : history?.provider === 'fixed_demo_fallback' ? 'Demo broker · sampled quotes' : 'Waiting for feed'
  return <div className="data-view market-watch"><div className="data-view-header"><div><div className="page-kicker">MARKET DATA</div><h2>Market watch</h2><p>Quote feed and price history for supported symbols. External feed data may be delayed.</p></div><form className="view-search" onSubmit={submit}><Search size={15}/><input placeholder="Find a symbol…" value={search} onChange={e => setSearch(e.target.value)}/><button aria-label="Ask copilot about symbol"><ArrowUpRight size={14}/></button></form></div>
    {error && <p className="inline-error"><Activity size={15}/>{error}</p>}
    <div className="market-index-grid">{['NIFTY 50', 'SENSEX'].map(symbol => <button className={`index-card index-card-button ${selected === symbol ? 'selected' : ''}`} key={symbol} onClick={() => setSelected(symbol)}><span>{symbol}<small>{sources[symbol] === 'yahoo_finance' ? 'EXTERNAL FEED' : 'DEMO FEED'}</small></span><strong>{snapshot[symbol] ? Number(snapshot[symbol]).toLocaleString('en-IN') : '—'}</strong><small>{snapshot[symbol] ? 'Latest available quote' : loading ? 'Loading…' : 'No quote supplied by the feed'}</small></button>)}</div>
    <section className="chart-card"><div className="chart-card-head"><div><div className="page-kicker">PRICE HISTORY</div><h3>{selected}</h3><span>{source}</span></div><div className="chart-controls">{ranges.map(item => <button key={item.days} onClick={() => setRange(item.days)} className={range === item.days ? 'active' : ''}>{item.label}</button>)}</div></div>
      {chartLoading ? <div className="chart-empty">Loading price history…</div> : chartError ? <div className="chart-empty">{chartError}</div> : <PriceChart points={chartPoints}/>}<div className="chart-scale">{chartPoints[0]?.time ? new Date(chartPoints[0].time).toLocaleDateString() : 'History builds as quotes arrive'}<span>{chartPoints.at(-1)?.time ? new Date(chartPoints.at(-1)!.time).toLocaleString() : 'No fabricated points'}</span></div>
    </section>
    <div className="data-table-card"><div className="table-head"><span>SUPPORTED SYMBOL</span><span>LAST PRICE</span><span>SOURCE</span><span/></div>{loading ? <div className="table-state">Loading available quotes…</div> : shown.length ? shown.map(([symbol, value]) => <button className={`table-row ${selected === symbol ? 'row-selected' : ''}`} key={symbol} onClick={() => setSelected(symbol)}><span className="symbol-cell"><i/>{symbol.replace('.NS', '')}<small>{symbol.endsWith('.NS') ? 'NSE' : 'Index'}</small></span><b>₹{Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b><span className="source-label">{sources[symbol] === 'yahoo_finance' ? 'Yahoo Finance' : 'Demo feed'}</span><ArrowUpRight size={15}/></button>) : <div className="table-state">No quote snapshot yet. Check the data provider configuration and service health.</div>}</div>
    <div className="inline-notice">Select a row or index to chart it. Demo charts contain only snapshots recorded by this app; external prices can be delayed. A missing value is never filled with an estimate.</div>
  </div>
}
