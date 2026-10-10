'use client'
import { useEffect, useState } from 'react'
import { ArrowUpRight, ChevronRight, CircleAlert, Clock3, RefreshCw, WalletCards } from 'lucide-react'

const API = 'http://localhost:8000'
const MOCK = 'http://localhost:8001'
type Order = { id: string; symbol: string; side: string; order_type: string; quantity: number; status: string; created_at?: string; trigger_price?: number; quoted_price?: number }
type Activity = { event_type: string; symbol?: string; created_at: string }

function badgeClass(status: string) {
  const value = status.toUpperCase()
  if (['DRAFT','PENDING','APPROVED'].includes(value)) return 'status-badge status-pending'
  if (['FILLED','EXECUTED','COMPLETED','PARTIAL'].includes(value)) return 'status-badge status-positive'
  if (['REJECTED','CANCELLED'].includes(value)) return 'status-badge status-negative'
  if (['FAILED','EXPIRED','ERROR'].includes(value)) return 'status-badge status-failed'
  return 'status-badge'
}
const prettyStatus = (status: string) => ({ DRAFT: 'Pending approval', FILLED: 'Executed · demo', SUBMITTED: 'Submitted · demo', PARTIAL: 'Part-filled · demo', APPROVED: 'Approved · demo' } as Record<string,string>)[status.toUpperCase()] || status.replace(/_/g,' ').toLowerCase().replace(/\b\w/g, c => c.toUpperCase())

export default function TradingPanel({ onReviewOrders, onAskPrice }: { onReviewOrders: () => void; onAskPrice: (symbol: string) => void }) {
  const [orders, setOrders] = useState<Order[]>([])
  const [events, setEvents] = useState<Activity[]>([])
  const [prices, setPrices] = useState<Record<string,number>>({})
  const [account, setAccount] = useState<any>(null)
  const [selected, setSelected] = useState<Order | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = async () => {
    try {
      const [orderRes, auditRes, priceRes, accountRes] = await Promise.all([fetch(`${API}/orders/`), fetch(`${API}/audit/?limit=6`), fetch(`${API}/chat/price-snapshot`), fetch(`${MOCK}/account`)] )
      if (![orderRes,auditRes,priceRes,accountRes].every(r => r.ok)) throw new Error('Some dashboard data could not be loaded.')
      const [orderData,auditData,priceData,accountData] = await Promise.all([orderRes.json(),auditRes.json(),priceRes.json(),accountRes.json()])
      setOrders(orderData.orders || []); setEvents(auditData.entries || []); setPrices(priceData.prices || {}); setAccount(accountData); setError('')
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load trading panel.') } finally { setLoading(false) }
  }
  useEffect(() => { load(); const timer = setInterval(load, 10000); return () => clearInterval(timer) }, [])
  const pending = orders.filter(order => ['DRAFT','PENDING','APPROVED'].includes(order.status.toUpperCase())).slice(0,3)
  const watchlist = ['RELIANCE.NS','INFY.NS','TCS.NS']
  return <div className="trading-panel">
    <div className="rail-heading"><div><span className="panel-eyebrow">YOUR DEMO ACCOUNT</span><h2>Trading overview</h2></div><button className="icon-button" aria-label="Refresh trading data" onClick={load}><RefreshCw size={14}/></button></div>
    {error && <div className="inline-error"><CircleAlert size={15}/><span>{error}</span></div>}
    <div className="mini-account"><span className="mini-account-icon"><WalletCards size={17}/></span><div><span>Portfolio value</span><b>{account ? `₹${Number(account.total_value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}` : loading ? 'Loading…' : 'Unavailable'}</b></div><small>DEMO</small></div>
    <section className="rail-section"><div className="rail-section-title"><h3>Pending orders</h3><button onClick={onReviewOrders}>View all <ArrowUpRight size={12}/></button></div>
      {loading ? <div className="rail-empty">Loading order queue…</div> : pending.length ? <div className="rail-order-list">{pending.map(order => <button className={`rail-order ${selected?.id === order.id ? 'selected' : ''}`} key={order.id} onClick={() => setSelected(selected?.id === order.id ? null : order)}><span className="rail-order-top"><b>{order.side} {order.symbol?.replace('.NS','')}</b><span className={badgeClass(order.status)}>{prettyStatus(order.status)}</span></span><span className="rail-order-sub">{order.quantity} shares · {order.order_type}</span></button>)}</div> : <div className="rail-empty">No pending orders. Your new drafts will appear here.</div>}
      {selected && <div className="selected-order-detail"><div><span>Quantity</span><b>{selected.quantity} shares</b></div><div><span>Order type</span><b>{selected.order_type}</b></div>{selected.trigger_price && <div><span>Trigger</span><b>₹{Number(selected.trigger_price).toLocaleString('en-IN')}</b></div>}<button onClick={onReviewOrders}>Review order details <ChevronRight size={13}/></button><small>Approval remains required before this draft is sent.</small></div>}
    </section>
    <section className="rail-section"><div className="rail-section-title"><h3>Watchlist</h3><span className="rail-demo-tag">DEMO QUOTES</span></div><div className="watchlist-rows">{watchlist.map(symbol => <button key={symbol} onClick={() => onAskPrice(symbol.replace('.NS',''))}><span>{symbol.replace('.NS','')}</span><b>{prices[symbol] ? `₹${Number(prices[symbol]).toLocaleString('en-IN',{maximumFractionDigits:2})}` : '—'}</b><ChevronRight size={13}/></button>)}</div></section>
    <section className="rail-section"><div className="rail-section-title"><h3>Recent activity</h3><Clock3 size={13}/></div>{events.length ? <div className="activity-rows">{events.slice(0,4).map((event,index) => <div className="activity-row" key={`${event.event_type}-${index}`}><i/><span>{event.event_type.replace(/_/g,' ').toLowerCase().replace(/\b\w/g,c=>c.toUpperCase())}{event.symbol ? ` · ${event.symbol}` : ''}<small>{event.created_at ? new Date(event.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'}) : 'Recent'}</small></span></div>)}</div> : <div className="rail-empty">No activity recorded yet.</div>}</section>
    <p className="rail-disclosure">All prices, balances, and broker responses are simulated for demonstration.</p>
  </div>
}
