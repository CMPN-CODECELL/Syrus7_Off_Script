'use client'

import { useState, useEffect } from 'react'
import TickerStrip from '@/components/TickerStrip'
import ChatPanel from '@/components/ChatPanel'
import PortfolioSidebar from '@/components/PortfolioSidebar'
import InstructionsPanel from '@/components/InstructionsPanel'
import AuditLog from '@/components/AuditLog'
import { LayoutDashboard, MessageSquare, BookOpen, FileText } from 'lucide-react'

type Tab = 'chat' | 'instructions' | 'audit'

export default function Home() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: 'var(--bg)' }}>
      <header className="flex items-center justify-between px-6 py-3 border-b shrink-0" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold tracking-widest accent-text">STOCKITUP</span>
          <span className="text-xs muted-text border px-2 py-0.5 rounded" style={{ borderColor: 'var(--border)' }}>AI TRADING COPILOT</span>
        </div>
        <nav className="flex items-center gap-1">
          {([
            { id: 'chat', label: 'Copilot', icon: MessageSquare },
            { id: 'instructions', label: 'Instructions', icon: BookOpen },
            { id: 'audit', label: 'Audit Log', icon: FileText },
          ] as const).map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setActiveTab(id)} className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all" style={{ background: activeTab === id ? 'var(--accent-dim)' : 'transparent', color: activeTab === id ? 'var(--accent)' : 'var(--text-muted)', border: `1px solid ${activeTab === id ? 'var(--accent)' : 'transparent'}` }}>
              <Icon size={13} />{label}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-2 text-xs text-amber-400" title="Orders and portfolio use the local mock broker">
          <span className="w-2 h-2 rounded-full bg-amber-400" />MOCK MODE
        </div>
      </header>
      <TickerStrip />
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-hidden">
          {activeTab === 'chat' && <ChatPanel />}
          {activeTab === 'instructions' && <InstructionsPanel />}
          {activeTab === 'audit' && <AuditLog />}
        </main>
        <aside className="w-72 border-l shrink-0 overflow-y-auto" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
          <PortfolioSidebar />
        </aside>
      </div>
    </div>
  )
}
