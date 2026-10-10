'use client'

import { useState } from 'react'
import Link from 'next/link'
import { Activity, ArrowLeft, BookOpen, BriefcaseBusiness, LineChart, ChevronLeft, ChevronRight, ClipboardCheck, FileClock, Menu, MessageSquareText, Shield, SlidersHorizontal, X } from 'lucide-react'
import TickerStrip from '@/components/TickerStrip'
import ChatPanel from '@/components/ChatPanel'
import InstructionsPanel from '@/components/InstructionsPanel'
import AuditLog from '@/components/AuditLog'
import TradingPanel from '@/components/TradingPanel'
import MarketWatch from '@/components/MarketWatch'
import PortfolioInsights from '@/components/PortfolioInsights'
import OrdersApprovals from '@/components/OrdersApprovals'

type View = 'copilot' | 'instructions' | 'audit' | 'market' | 'portfolio' | 'orders' | 'stops'
const navGroups = [
  { label: 'Workspace', items: [
    { id: 'copilot', label: 'Copilot', icon: MessageSquareText },
    { id: 'instructions', label: 'Instructions', icon: BookOpen },
    { id: 'audit', label: 'Audit log', icon: FileClock },
  ] },
  { label: 'Trading', items: [
    { id: 'market', label: 'Market watch', icon: Activity },
    { id: 'portfolio', label: 'Portfolio insights', icon: BriefcaseBusiness },
    { id: 'orders', label: 'Orders & approvals', icon: ClipboardCheck },
    { id: 'stops', label: 'Stop-loss rules', icon: SlidersHorizontal },
  ] },
] as const
const viewTitles: Record<View, string> = { copilot: 'Copilot', instructions: 'Instructions', audit: 'Audit log', market: 'Market watch', portfolio: 'Portfolio insights', orders: 'Orders & approvals', stops: 'Stop-loss management' }

export default function DashboardShell() {
  const [view, setView] = useState<View>('copilot')
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [chatPrompt, setChatPrompt] = useState('')
  const navigateToChat = (prompt?: string) => { if (prompt) setChatPrompt(prompt); setView('copilot'); setMobileOpen(false) }

  return <div className="dashboard-shell">
    {mobileOpen && <button className="mobile-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <aside className={`app-sidebar ${collapsed ? 'is-collapsed' : ''} ${mobileOpen ? 'mobile-open' : ''}`}>
      <div className="sidebar-brand-row"><Link href="/" className="sidebar-brand"><span className="brand-mark"><LineChart size={19}/></span>{!collapsed && <span>STOCKITUP</span>}</Link><button className="sidebar-toggle desktop-only" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? <ChevronRight size={16}/> : <ChevronLeft size={16}/>}</button><button className="sidebar-toggle mobile-only" onClick={() => setMobileOpen(false)} aria-label="Close sidebar"><X size={16}/></button></div>
      <div className="sidebar-mode"><span className="mode-dot"/>{!collapsed && <><span>DEMO ENVIRONMENT</span><span className="mode-label">MOCK</span></>}</div>
      <nav className="sidebar-nav" aria-label="Main navigation">{navGroups.map(group => <div className="nav-group" key={group.label}><div className="nav-group-label">{!collapsed ? group.label : <span className="nav-group-rule"/>}</div>{group.items.map(({id,label,icon:Icon}) => <button key={id} title={collapsed ? label : undefined} aria-current={view === id ? 'page' : undefined} className={`nav-item ${view === id ? 'active' : ''}`} onClick={() => { setView(id); setMobileOpen(false) }}><Icon size={17}/>{!collapsed && <span>{label}</span>}{view === id && !collapsed && <i className="nav-active-dot"/>}</button>)}</div>)}</nav>
      <div className="sidebar-bottom"><div className="approval-note"><Shield size={16}/>{!collapsed && <span>Human approval enabled</span>}</div>{!collapsed && <p>Quotes and orders are simulated demo data.</p>}</div>
    </aside>
    <div className="dashboard-main">
      <header className="app-header"><div className="header-leading"><button className="sidebar-toggle mobile-only" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={18}/></button><div><div className="page-kicker">STOCKITUP <span>/</span> WORKSPACE</div><h1>{viewTitles[view]}</h1></div></div><div className="header-actions"><span className="market-status"><i/> Demo feed</span><span className="header-separator"/><Link href="/" className="back-home"><ArrowLeft size={14}/>Home</Link></div></header>
      <TickerStrip onSearch={(symbol) => navigateToChat(`Check the current price for ${symbol}`)} />
      <div className={`workspace-grid ${view !== 'copilot' ? 'workspace-grid-single' : ''}`}>
        <main className="workspace-content" key={view}>
          {view === 'copilot' && <ChatPanel prompt={chatPrompt} onPromptConsumed={() => setChatPrompt('')} />}
          {view === 'instructions' && <InstructionsPanel onCreate={() => navigateToChat('Help me create a standing instruction. Ask for the symbol, trigger price, action, and quantity if needed.')} />}
          {view === 'audit' && <AuditLog />}
          {view === 'market' && <MarketWatch onAskPrice={(symbol) => navigateToChat(`Check the current price for ${symbol}`)} />}
          {view === 'portfolio' && <PortfolioInsights />}
          {view === 'orders' && <OrdersApprovals />}
          {view === 'stops' && <InstructionsPanel stopLossOnly onCreate={() => navigateToChat('Help me set up a stop-loss rule. Ask for the stock, trigger price, and number of shares to sell.')} />}
        </main>
        {view === 'copilot' && <aside className="workspace-rail"><TradingPanel onReviewOrders={() => setView('orders')} onAskPrice={(symbol) => navigateToChat(`Check the current price for ${symbol}`)} /></aside>}
      </div>
    </div>
  </div>
}
