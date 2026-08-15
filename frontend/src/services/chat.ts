import type { ChatResponse } from '../types/chat'

export async function askSchoolAssistant(message: string): Promise<ChatResponse> {
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const detail = payload?.detail?.message
    throw new Error(detail || '服务暂时不可用，请稍后重试')
  }

  return response.json()
}
