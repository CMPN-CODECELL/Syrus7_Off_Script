import Link from 'next/link'
import { ArrowRight, Bot, Check, CircleDot, ClipboardCheck, LineChart, Search, ShieldCheck, SlidersHorizontal, Sparkles, WalletCards, Zap } from 'lucide-react'

const features = [
  { icon: Bot, title: 'AI copilot', text: 'Ask portfolio questions and shape trade ideas in natural language.' },
  { icon: LineChart, title: 'Market insights', text: 'Check supported quotes and understand the context around your holdings.' },
  { icon: SlidersHorizontal, title: 'Stop-loss controls', text: 'Create, review, pause, and cancel price-triggered standing rules.' },
  { icon: ShieldCheck, title: 'Risk analysis', text: 'Review order checks and guardrails before approving a proposal.' },
  { icon: WalletCards, title: 'Human-approved trading', text: 'Review order details and explicitly approve before a draft is submitted.' },
]

export default function LandingPage() {
  return <main className="landing-page">
    <header className="landing-nav">
      <Link href="/" className="brand-lockup"><span className="brand-mark"><LineChart size={20}/></span><span>StockItUp</span></Link>
      <div className="landing-nav-right"><span className="demo-chip"><i/> Mock broker · configurable data</span><Link href="/app" className="button-primary">Launch Copilot <ArrowRight size={15}/></Link></div>
    </header>

    <section className="hero-section">
      <div className="hero-copy">
        <div className="eyebrow"><Sparkles size={13}/> YOUR PORTFOLIO, WITH A COPILOT</div>
        <h1>Trade smarter.<br/><span>Stay in control.</span></h1>
        <p>Turn plain-language ideas into reviewable trade drafts. Get portfolio insights, check risk, and keep approval in your hands at every step.</p>
        <div className="hero-actions"><Link href="/app" className="button-primary button-large">Launch Copilot <ArrowRight size={16}/></Link><a href="#features" className="button-quiet">Explore features <ArrowRight size={15}/></a></div>
        <div className="hero-proof"><span><ShieldCheck size={15}/> Review before action</span><span><Zap size={15}/> Natural-language workflows</span></div>
      </div>
      <div className="preview-wrap" aria-label="Preview of the StockItUp dashboard">
        <div className="preview-window">
          <div className="preview-top"><div className="window-dots"><i/><i/><i/></div><span>StockItUp / Copilot</span><span className="preview-live"><i/> DEMO</span></div>
          <div className="preview-content">
            <div className="preview-sidebar"><span className="preview-logo"><LineChart size={15}/> STOCKITUP</span><b>● &nbsp;Copilot</b><span>▤ &nbsp;Instructions</span><span>◷ &nbsp;Audit log</span><span>⌁ &nbsp;Market watch</span></div>
            <div className="preview-main"><div className="preview-greeting"><small>STOCKITUP AI · DEMO MODE</small><h3>Good morning.</h3><p>What would you like to review today?</p></div><div className="preview-cards"><div><WalletCards size={16}/><b>Analyse portfolio</b><small>Review holdings & value</small></div><div><LineChart size={16}/><b>Check a quote</b><small>Supported demo symbols</small></div></div><div className="preview-input">Ask your copilot… <span>↑</span></div></div>
          </div>
          <div className="preview-foot"><span><i/> APPROVAL REQUIRED</span><span>DEMO QUOTES · MOCK BROKER</span></div>
        </div>
        <div className="preview-glow"/>
      </div>
    </section>

    <section className="feature-section" id="features"><div className="section-heading"><div><div className="eyebrow">BUILT AROUND CLARITY</div><h2>Useful tools. Clear decisions.</h2></div><p>One calm workspace for your portfolio, trading ideas, and risk controls.</p></div>
      <div className="feature-grid">{features.map(({icon: Icon,title,text}, i) => <article className="feature-card" key={title}><span className="feature-icon"><Icon size={19}/></span><span className="feature-index">0{i+1}</span><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>
    <section className="landing-workflow"><div className="section-heading"><div><div className="eyebrow">A CLEARER WAY TO ACT</div><h2>From question to reviewed decision.</h2></div><p>Useful context at each step, with the trader in control of what happens next.</p></div><div className="workflow-grid">
      {[{n:'01',icon:Search,title:'Ask in plain language',body:'Check a supported stock, explore a portfolio question, or describe an order idea.'},{n:'02',icon:Sparkles,title:'Get structured context',body:'The copilot explains the request and can prepare a draft for risk review.'},{n:'03',icon:ClipboardCheck,title:'Review before action',body:'Inspect the terms, risk checks, and status. Approval is explicit and recorded.'}].map(({n,icon:Icon,title,body})=><article className="workflow-step" key={n}><span className="workflow-number">{n}</span><span className="feature-icon"><Icon size={18}/></span><h3>{title}</h3><p>{body}</p></article>)}
    </div></section>
    <section className="landing-insights"><div className="insights-copy"><div className="eyebrow">MARKET CONTEXT, AT A GLANCE</div><h2>See the signal.<br/><span>Keep the whole picture.</span></h2><p>Move between market watch, portfolio insights, order approvals, and stop-loss instructions without losing the context of your decision.</p><Link href="/app" className="button-quiet">Explore the workspace <ArrowRight size={14}/></Link></div><div className="insights-preview"><div className="insights-preview-head"><span><CircleDot size={14}/> MARKET WATCH</span><small>EXAMPLE VIEW</small></div><div className="insight-quote"><span>NIFTY 50 <small>INDEX</small></span><strong>Price history</strong><svg viewBox="0 0 420 120" preserveAspectRatio="none" aria-label="Illustrative chart preview"><path d="M0 88 C32 78 36 52 66 62 S109 99 139 72 S179 34 208 48 S243 86 277 53 S316 48 341 30 S385 50 420 18"/></svg><small>Chart values use the configured quote feed.</small></div><div className="insights-pills"><span><Check size={12}/>Portfolio context</span><span><Check size={12}/>Risk review</span><span><Check size={12}/>Order status</span></div></div></section>
    <section className="landing-safety"><div className="safety-icon"><ShieldCheck size={20}/></div><div><div className="eyebrow">DESIGNED TO KEEP YOU IN CONTROL</div><h2>Approval stays with you.</h2><p>Order drafts are not executed automatically. The local demonstration uses a mock broker; demo results are clearly identified and are not real trades. Configure a market data provider separately to view external quotes.</p></div><Link href="/app" className="button-primary">Open Copilot <ArrowRight size={15}/></Link></section>
    <footer className="landing-footer"><Link href="/" className="brand-lockup"><span className="brand-mark"><LineChart size={17}/></span><span>StockItUp</span></Link><p>Orders use a local mock broker. Market quotes use the configured feed and may be delayed. No live brokerage execution.</p><span>© StockItUp · Team Off Script</span></footer>
  </main>
}
