import type { ChatResponse, ChatSource, HistoryTurn } from '../types/chat'

export async function askSchoolAssistant(
  message: string,
  history: HistoryTurn[] = [],
): Promise<ChatResponse> {
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail?.message
    throw new Error(detail || '服务暂时不可用，请稍后重试')
  }

  return response.json()
}

export interface StreamCallbacks {
  onDelta: (content: string) => void
  onDone: (sources: ChatSource[]) => void
  onError: (message: string) => void
}

export async function askSchoolAssistantStream(
  message: string,
  history: HistoryTurn[],
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  })

  if (!response.ok || !response.body) {
    throw new Error('服务暂时不可用，请稍后重试')
  }


  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      try {
        const event = JSON.parse(payload)
        if (event.type === 'delta') {
          callbacks.onDelta(event.content)
        } else if (event.type === 'done') {
          callbacks.onDone(event.sources ?? [])
        } else if (event.type === 'error') {
          callbacks.onError(event.message ?? '服务异常，请稍后重试')
        }
      } catch {
        // 忽略无法解析的行
      }
    }
  }
}
