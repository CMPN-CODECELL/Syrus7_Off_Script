'use client'
import { FormEvent, useEffect, useState } from 'react'
import { Search } from 'lucide-react'

type Props = { onSearch?: (symbol: string) => void }
export default function TickerStrip({ onSearch }: Props) {
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [provider, setProvider] = useState('')
  useEffect(() => {
    let alive = true
    const fetchSnapshot = async () => {
      try {
        const response = await fetch('http://localhost:8000/chat/price-snapshot')
        if (!response.ok) throw new Error('Price feed unavailable')
        const data = await response.json()
        if (alive) { setPrices(data.prices || {}); setProvider(data.provider || '') }
      } catch { if (alive) { setPrices({}); setProvider('') } } finally { if (alive) setLoading(false) }
    }
    fetchSnapshot()
    const timer = setInterval(fetchSnapshot, 10000)
    return () => { alive = false; clearInterval(timer) }
  }, [])
  const submit = (event: FormEvent) => { event.preventDefault(); const symbol = search.trim().toUpperCase().replace(/\.NS$/, ''); if (!symbol) return; onSearch?.(symbol); setSearch('') }
  const indices = [
    { symbol: 'NIFTY 50', value: prices['NIFTY 50'] ?? prices['^NSEI'] },
    { symbol: 'SENSEX', value: prices.SENSEX ?? prices['^BSESN'] },
  ]
  return <section className="ticker-strip" aria-label="Market ticker">
    <div className="ticker-indices">{indices.map(index => <div className="ticker-index" key={index.symbol}><span>{index.symbol}</span><b>{typeof index.value === 'number' ? index.value.toLocaleString('en-IN', { maximumFractionDigits: 2 }) : '—'}</b></div>)}<div className="ticker-market"><i/><span>{loading ? 'Connecting to quote feed' : Object.keys(prices).length ? provider === 'yahoo_finance' ? 'External quote feed' : 'Demo market feed' : 'Quote feed unavailable'}</span></div></div>
    <div className="ticker-stocks">{Object.entries(prices).slice(0, 5).map(([symbol,value]) => <div className="ticker-stock" key={symbol}><span>{symbol.replace('.NS','')}</span><b>₹{Number(value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</b></div>)}{!loading && Object.keys(prices).length === 0 && <span className="ticker-empty">Waiting for quote data</span>}</div>
    <form className="ticker-search" onSubmit={submit}><Search size={14}/><input aria-label="Search stock symbol" placeholder="Search symbol" value={search} onChange={event => setSearch(event.target.value)}/></form>
    <span className="ticker-disclosure">{provider === 'yahoo_finance' ? 'YAHOO FINANCE · MAY BE DELAYED' : 'DEMO QUOTES'}</span>
  </section>
}
