'use client'

import { useState, useEffect, useRef } from 'react'
import { Send, Loader2, ShieldAlert, WalletCards, Search, ShieldCheck, ClipboardList, Sparkles, ArrowUpRight } from 'lucide-react'
import ConfirmationCard from './ConfirmationCard'
import InstructionConfirmationCard from './InstructionConfirmationCard'
import RiskLimitConfirmationCard from './RiskLimitConfirmationCard'
import OrderPlanCard, { type OrderPlan } from './OrderPlanCard'
import ResponseContent from './ResponseContent'
import { streamChat } from '@/lib/api'

interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  streaming?: boolean
  draft?: DraftData | null
  instructionDraft?: InstructionDraftData | null
  riskLimitDraft?: RiskLimitDraftData | null
  orderPlan?: OrderPlan | null
  injectionBlocked?: boolean
}

interface DraftData {
  order_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  order_type: string
  quantity: number
  price?: number
  trigger_price?: number
  quoted_price?: number
  risk_score?: number
  risk_check_passed?: boolean
  risk_reason?: string
}

interface InstructionDraftData {
  name: string
  symbol: string
  condition_type: 'PRICE_ABOVE' | 'PRICE_BELOW'
  condition_value: number
  action_side: 'BUY' | 'SELL'
  action_quantity: number
  action_order_type?: string
  expires_in_hours?: number
}

interface RiskLimitDraftData {
  draft_id: string
  limit_type: string
  label: string
  current_value: number
  value: number
  expires_at: string
}

const QUICK_ACTIONS = [
  { title: 'Analyse portfolio', detail: 'Holdings, balance and P&L', icon: WalletCards, prompt: 'Analyse my current demo portfolio, holdings, and P&L.' },
  { title: 'Check stock price', detail: 'Look up a supported quote', icon: Search, prompt: 'Show me the current INFY price and my position.' },
  { title: 'Review risk', detail: 'Understand portfolio risk limits', icon: ShieldCheck, prompt: 'Review my portfolio exposure and current risk limits.' },
  { title: 'Review pending orders', detail: 'See drafts awaiting approval', icon: ClipboardList, prompt: 'Show my pending orders and their approval status.' },
]

export default function ChatPanel({ prompt, onPromptConsumed }: { prompt?: string; onPromptConsumed?: () => void }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [history, setHistory] = useState<{ role: string; content: string }[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef  = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = async (text?: string) => {
    const userText = text || input.trim()
    if (!userText || isStreaming) return

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: userText }
    const assistantId = (Date.now() + 1).toString()
    const assistantMsg: Message = { id: assistantId, role: 'assistant', content: '', streaming: true }

    setMessages(prev => [...prev, userMsg, assistantMsg])
    setInput('')
    setIsStreaming(true)

    let currentDraft: DraftData | null = null
    let currentInstructionDraft: InstructionDraftData | null = null
    let currentRiskLimitDraft: RiskLimitDraftData | null = null
    let currentOrderPlan: OrderPlan | null = null
    let currentAssistantContent = ''

    try {
      await streamChat(
        userText,
        history,
        {
          onText: (chunk) => {
            currentAssistantContent += chunk
            setMessages(prev =>
              prev.map(m => m.id === assistantId
                ? { ...m, content: m.content + chunk }
                : m
              )
            )
          },
          onDraft: (draftData, tool) => {
            if (tool === 'create_standing_instruction') {
              currentInstructionDraft = draftData
            } else if (tool === 'propose_risk_limit_update') {
              currentRiskLimitDraft = draftData
            } else if (tool === 'create_order_plan') {
              currentOrderPlan = draftData
            } else {
              currentDraft = draftData
            }
          },
          onInjectionBlocked: (reason) => {
            setMessages(prev =>
              prev.map(m => m.id === assistantId
                ? { ...m, streaming: false, injectionBlocked: true, content: `⚠️ Message blocked by injection shield: ${reason}` }
                : m
              )
            )
          },
          onError: (message) => {
            setMessages(prev => prev.map(m => m.id === assistantId
              ? { ...m, streaming: false, content: message }
              : m
            ))
          },
          onDone: () => {
            setMessages(prev =>
              prev.map(m => m.id === assistantId
                ? { ...m, streaming: false, draft: currentDraft, instructionDraft: currentInstructionDraft, riskLimitDraft: currentRiskLimitDraft, orderPlan: currentOrderPlan }
                : m
              )
            )
            setHistory(prev => [
              ...prev,
              { role: 'user', content: userText },
              { role: 'assistant', content: currentAssistantContent },
            ])
          },
        }
      )
    } catch (err) {
      setMessages(prev =>
        prev.map(m => m.id === assistantId
          ? { ...m, streaming: false, content: 'Connection error. Please try again.' }
          : m
        )
      )
    } finally {
      setIsStreaming(false)
      inputRef.current?.focus()
    }
  }

  useEffect(() => {
    if (prompt) { sendMessage(prompt); onPromptConsumed?.() }
  }, [prompt])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleOrderApproved = (orderId: string, outcome: string) => {
    setMessages(prev =>
      prev.map(m =>
        m.draft?.order_id === orderId
          ? { ...m, content: `${m.content}\n\n${outcome}`, draft: null }
          : m
      )
    )
  }

  return (
    <div className="flex flex-col h-full">

      {/* Messages */}
      <div className={`chat-messages flex-1 overflow-y-auto p-4 space-y-4 ${messages.length === 0 ? 'chat-empty' : ''}`}>
        {messages.length === 0 && <div className="welcome-state"><div className="welcome-icon"><Sparkles size={19}/></div><span className="panel-eyebrow">YOUR AI TRADING COPILOT</span><h2>Good morning.</h2><p>What would you like to work through today?</p><div className="quick-action-grid">{QUICK_ACTIONS.map(({title,detail,icon:Icon,prompt:actionPrompt})=><button key={title} className="quick-action-card" onClick={()=>sendMessage(actionPrompt)} disabled={isStreaming}><span className="quick-action-icon"><Icon size={17}/></span><span><b>{title}</b><small>{detail}</small></span><ArrowUpRight size={14} className="quick-action-arrow"/></button>)}</div><div className="welcome-disclosure">Ask questions, review risk, or prepare a draft. Trade proposals need your explicit approval.</div></div>}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-2xl ${msg.role === 'user' ? 'order-user' : 'order-assistant'}`}>

              {msg.injectionBlocked ? (
                <div className="flex items-start gap-2 p-3 rounded-lg"
                     style={{ background: '#ff4d6d15', border: '1px solid var(--danger)' }}>
                  <ShieldAlert size={16} style={{ color: 'var(--danger)', marginTop: 2, flexShrink: 0 }} />
                  <span style={{ color: 'var(--danger)', fontSize: 13 }}>{msg.content}</span>
                </div>
              ) : msg.role === 'user' ? (
                <div
                  className="px-4 py-3 rounded-xl text-sm ml-auto"
                  style={{
                    background: 'var(--accent-dim)',
                    border: '1px solid var(--accent)',
                    color: 'var(--text)',
                    whiteSpace: 'pre-wrap',
                    fontFamily: 'var(--font-body)',
                  }}
                >
                  {msg.content}
                </div>
              ) : (
                <article className={`assistant-response-card ${msg.streaming ? 'is-streaming' : ''}`}>
                  <header className="response-card-header">
                    <span className="response-avatar"><Sparkles size={13}/></span>
                    <span className="response-brand">STOCKITUP <small>AI COPILOT</small></span>
                    <span className="response-live-status">{msg.streaming ? <><Loader2 size={10} className="animate-spin"/> THINKING</> : 'INSIGHT'}</span>
                  </header>
                  <div className="response-card-content">
                    {msg.content ? <ResponseContent content={msg.content}/> : <div className="response-skeleton"><i/><i/><i/></div>}
                  </div>
                </article>
              )}

              {/* Draft confirmation card */}
              {msg.draft && !msg.injectionBlocked && (
                <div className="mt-3">
                  <ConfirmationCard
                    draft={msg.draft}
                    onApproved={(outcome) => handleOrderApproved(msg.draft!.order_id, outcome)}
                    onRejected={(outcome) => handleOrderApproved(msg.draft!.order_id, outcome)}
                  />
                </div>
              )}
              {msg.instructionDraft && !msg.injectionBlocked && (
                <div className="mt-3">
                  <InstructionConfirmationCard draft={msg.instructionDraft} />
                </div>
              )}
              {msg.riskLimitDraft && !msg.injectionBlocked && (
                <div className="mt-3">
                  <RiskLimitConfirmationCard draft={msg.riskLimitDraft} />
                </div>
              )}
              {msg.orderPlan && !msg.injectionBlocked && (
                <OrderPlanCard plan={msg.orderPlan} onFinished={(outcome) => setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, content: `${m.content}\n\n${outcome}`, orderPlan: null } : m))} />
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {/* Input */}
      <div className="chat-composer p-4 border-t" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-end gap-3 p-3 rounded-xl"
             style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
            rows={1}
            className="flex-1 resize-none bg-transparent outline-none text-sm"
            style={{ color: 'var(--text)', fontFamily: 'var(--font-body)', maxHeight: 120 }}
            disabled={isStreaming}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isStreaming}
            className="p-2 rounded-lg transition-all disabled:opacity-30"
            style={{ background: 'var(--accent)', color: '#000' }}
          >
            {isStreaming
              ? <Loader2 size={16} className="animate-spin" />
              : <Send size={16} />
            }
          </button>
        </div>
        <p className="text-xs muted-text mt-2 text-center">
          Orders need your approval or an active standing rule you approved.
        </p>
      </div>
    </div>
  )
}
