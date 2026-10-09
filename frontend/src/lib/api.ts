'use client'

export async function streamChat(
  message: string,
  history: { role: string; content: string }[],
  callbacks: {
    onText: (text: string) => void
    onDraft: (draft: any, tool?: string) => void
    onInjectionBlocked: (reason: string) => void
    onError: (message: string) => void
    onDone: () => void
  }
) {
  const res = await fetch('http://localhost:8000/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_history: history }),
  })

  if (!res.ok) throw new Error(`Backend returned ${res.status}`)

  if (!res.body) throw new Error('No response body')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()

  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'text') {
            callbacks.onText(data.content)
          } else if (data.type === 'draft') {
            callbacks.onDraft(data.data, data.tool)
          } else if (data.type === 'injection_blocked') {
            callbacks.onInjectionBlocked(data.reason)
          } else if (data.type === 'done') {
            callbacks.onDone()
          } else if (data.type === 'error') {
            callbacks.onError(data.content)
          }
        } catch (e) {
          // Incomplete JSON chunk, skip
        }
      }
    }
  }
  if (buffer.startsWith('data: ')) {
    try {
      const data = JSON.parse(buffer.slice(6))
      if (data.type === 'text') callbacks.onText(data.content)
      else if (data.type === 'draft') callbacks.onDraft(data.data, data.tool)
      else if (data.type === 'error') callbacks.onError(data.content)
      else if (data.type === 'done') callbacks.onDone()
    } catch { /* Ignore an incomplete final SSE event. */ }
  }
}
