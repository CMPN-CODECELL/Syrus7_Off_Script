import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'StockItUp — AI Trading Copilot',
  description: 'Talk to your trading account in plain English. By Team Off Script.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="terminal">
      {/* Change data-theme to "luxury" to switch themes instantly */}
      <body>{children}</body>
    </html>
  )
}
