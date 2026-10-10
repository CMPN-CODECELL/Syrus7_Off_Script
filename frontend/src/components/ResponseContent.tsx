import { Fragment, ReactNode } from 'react'

function inline(text: string, keyPrefix: string): ReactNode[] {
  const token = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\*(?!\s)[^*]+\*)/g
  const out: ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  let index = 0
  while ((match = token.exec(text))) {
    if (match.index > last) out.push(...emphasize(text.slice(last, match.index), `${keyPrefix}-p${index++}`))
    const value = match[0]
    if (value.startsWith('**') || value.startsWith('__')) out.push(<strong key={`${keyPrefix}-b${index++}`}>{inline(value.slice(2, -2), `${keyPrefix}-strong-${index}`)}</strong>)
    else if (value.startsWith('`')) out.push(<code key={`${keyPrefix}-c${index++}`}>{value.slice(1, -1)}</code>)
    else out.push(<em key={`${keyPrefix}-i${index++}`}>{value.slice(1, -1)}</em>)
    last = match.index + value.length
  }
  if (last < text.length) out.push(...emphasize(text.slice(last), `${keyPrefix}-p${index++}`))
  return out
}

function emphasize(text: string, key: string): ReactNode[] {
  const currency = /([+−-]₹\s?[\d,]+(?:\.\d+)?(?:\s*\([+-]?[\d,.]+%\))?|₹\s?[\d,]+(?:\.\d+)?(?:\s*\([+-]?[\d,.]+%\))?)/g
  const parts: ReactNode[] = []
  let last = 0
  let match: RegExpExecArray | null
  let index = 0
  while ((match = currency.exec(text))) {
    if (match.index > last) parts.push(text.slice(last, match.index))
    const value = match[0]
    const mood = /^[+]/.test(value) ? 'positive' : /^[-−]/.test(value) ? 'negative' : ''
    parts.push(<span key={`${key}-${index++}`} className={mood ? `response-value ${mood}` : 'response-value'}>{value}</span>)
    last = match.index + value.length
  }
  if (last < text.length) parts.push(text.slice(last))
  return parts.length ? parts : [text]
}

function isMetricLine(line: string) { return /^\s*[-*+]\s+\*\*[^*]+(?::)?\*\*:?\s*.+$/.test(line) }
function metricLine(line: string) {
  const match = line.trim().replace(/^[-*+]\s+/, '').match(/^\*\*(.+?)(?::)?\*\*:?\s*(.+)$/)
  return match ? { label: match[1].replace(/:$/, ''), value: match[2] } : null
}
const isBullet = (line: string) => /^\s*[-*+]\s+/.test(line)
const isNumber = (line: string) => /^\s*\d+[.)]\s+/.test(line)
const isTableRule = (line: string) => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
const tableCells = (line: string) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim())

/** A small, safe Markdown renderer for model responses; text is always emitted as React text. */
export default function ResponseContent({ content }: { content: string }) {
  const lines = content.replace(/\r/g, '').split('\n')
  const blocks: ReactNode[] = []
  let paragraph: string[] = []
  let index = 0
  const flushParagraph = () => {
    if (!paragraph.length) return
    blocks.push(<p key={`p-${index++}`}>{inline(paragraph.join(' '), `p-${index}`)}</p>)
    paragraph = []
  }
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) { flushParagraph(); i++; continue }
    const fence = line.match(/^\s*```(\w*)\s*$/)
    if (fence) {
      flushParagraph(); i++
      const code: string[] = []
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) code.push(lines[i++])
      if (i < lines.length) i++
      blocks.push(<pre className="response-code" key={`code-${index++}`}><code>{code.join('\n')}</code></pre>)
      continue
    }
    if (line.includes('|') && i + 1 < lines.length && isTableRule(lines[i + 1])) {
      flushParagraph()
      const headers = tableCells(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) rows.push(tableCells(lines[i++]))
      blocks.push(<div className="response-table-wrap" key={`table-${index++}`}><table><thead><tr>{headers.map((cell, n) => <th key={`th-${n}`}>{inline(cell, `th-${index}-${n}`)}</th>)}</tr></thead><tbody>{rows.map((row, r) => <tr key={`tr-${r}`}>{headers.map((_, c) => <td key={`td-${r}-${c}`}>{inline(row[c] || '', `td-${index}-${r}-${c}`)}</td>)}</tr>)}</tbody></table></div>)
      continue
    }
    const heading = line.match(/^\s{0,3}(#{1,3})\s+(.+?)\s*#*\s*$/)
    if (heading) {
      flushParagraph()
      const Tag = heading[1].length === 1 ? 'h2' : heading[1].length === 2 ? 'h3' : 'h4'
      blocks.push(<Tag className="response-heading" key={`h-${index++}`}>{inline(heading[2], `h-${index}`)}</Tag>)
      i++; continue
    }
    if (isBullet(line) || isNumber(line)) {
      flushParagraph()
      const ordered = isNumber(line)
      const items: string[] = []
      while (i < lines.length && (ordered ? isNumber(lines[i]) : isBullet(lines[i]))) {
        items.push(lines[i].replace(ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/, ''))
        i++
      }
      const metrics = !ordered && items.length > 1 && items.every(item => metricLine(`- ${item}`))
      if (metrics) {
        blocks.push(<div className="response-metric-grid" key={`metrics-${index++}`}>{items.map((item, n) => { const metric = metricLine(`- ${item}`)!; return <div className="response-metric" key={`metric-${n}`}><span>{inline(metric.label, `ml-${index}-${n}`)}</span><strong>{inline(metric.value, `mv-${index}-${n}`)}</strong></div> })}</div>)
      } else {
        const List = ordered ? 'ol' : 'ul'
        blocks.push(<List className={`response-list ${ordered ? 'numbered' : ''}`} key={`list-${index++}`}>{items.map((item, n) => <li key={`li-${n}`}>{inline(item, `li-${index}-${n}`)}</li>)}</List>)
      }
      continue
    }
    if (/^\s*>/.test(line)) {
      flushParagraph(); const quote: string[] = []
      while (i < lines.length && /^\s*>/.test(lines[i])) quote.push(lines[i++].replace(/^\s*>\s?/, ''))
      blocks.push(<blockquote key={`q-${index++}`}>{inline(quote.join(' '), `q-${index}`)}</blockquote>); continue
    }
    paragraph.push(line.trim())
    i++
  }
  flushParagraph()
  return <div className="formatted-response">{blocks.map((block, n) => <Fragment key={`block-${n}`}>{block}</Fragment>)}</div>
}
