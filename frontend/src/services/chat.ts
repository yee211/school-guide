import type { ChatResponse, ChatSource, HistoryTurn } from '../types/chat'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

export async function askSchoolAssistant(
  message: string,
  history: HistoryTurn[] = [],
): Promise<ChatResponse> {
  const response = await fetch(apiUrl('/chat'), {
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
  const response = await fetch(apiUrl('/chat/stream'), {
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

  let terminal = false
  function dispatch(line: string) {
    if (!line.startsWith('data:')) return
    let event
    try { event = JSON.parse(line.slice(5).trim()) } catch { return }
    if (event.type === 'delta') callbacks.onDelta(event.content)
    else if (event.type === 'done') { terminal = true; callbacks.onDone(event.sources ?? []) }
    else if (event.type === 'error') { terminal = true; callbacks.onError(event.message ?? '服务异常，请稍后重试') }
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) dispatch(line)
      if (done) {
        if (buffer.trim()) dispatch(buffer)
        break
      }
    }
    if (!terminal && !signal?.aborted) callbacks.onError('连接中断')
  } finally {
    reader.releaseLock()
  }
}
