'use client'

import { useState } from 'react'

type PlanLeg = { order_id: string; symbol: string; side: 'BUY' | 'SELL'; order_type: string; quantity: number; quoted_price: number; risk_score?: number }
export type OrderPlan = { plan_id: string; orders: PlanLeg[] }

export default function OrderPlanCard({ plan, onFinished }: { plan: OrderPlan; onFinished: (message: string) => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [status, setStatus] = useState('')

  const act = async (action: 'approve' | 'reject') => {
    setBusy(true); setError('')
    try {
      const res = await fetch(`http://localhost:8000/orders/plans/${plan.plan_id}/${action}`, { method: 'POST' })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Plan action failed.')
      setStatus(data.status)
      const summary = action === 'reject' ? data.message : `${data.status}: ${data.results.map((r: any) => `${r.symbol} ${r.status}`).join(', ')}`
      setMessage(summary)
      onFinished(summary)
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to process the plan.') }
    finally { setBusy(false) }
  }

  return <section className="mt-3 rounded-xl p-4" style={{ border: '1px solid var(--accent)', background: 'var(--surface)' }}>
    <div className="flex justify-between items-center mb-3"><strong className="accent-text">ORDER PLAN · {plan.orders.length} ORDERS</strong>{status && <span className="text-xs muted-text">{status}</span>}</div>
    <div className="space-y-2">{plan.orders.map((leg) => <div key={leg.order_id} className="flex justify-between gap-3 rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--surface-2)' }}>
      <span><b>{leg.side} {leg.symbol}</b><span className="block muted-text">{leg.quantity} shares · {leg.order_type}</span></span>
      <span className="text-right">₹{Number(leg.quoted_price).toLocaleString('en-IN', { minimumFractionDigits: 2 })}<span className="block muted-text">estimate ₹{(leg.quantity * leg.quoted_price).toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span></span>
    </div>)}</div>
    <p className="text-xs muted-text mt-3">One approval submits the complete plan after all quotes and risk checks pass. Broker fills cannot be rolled back if a later leg fails.</p>
    {error && <p className="text-sm mt-2" style={{ color: 'var(--danger)' }}>{error}</p>}
    {message && <p className="text-sm mt-2">{message}</p>}
    {!status && <div className="flex gap-2 mt-3"><button disabled={busy} onClick={() => act('approve')} className="flex-1 rounded-lg py-2 font-semibold disabled:opacity-50" style={{ background: 'var(--accent)', color: '#000' }}>{busy ? 'Processing…' : 'Approve entire plan'}</button><button disabled={busy} onClick={() => act('reject')} className="rounded-lg px-4 py-2" style={{ border: '1px solid var(--border)' }}>Reject</button></div>}
  </section>
}
