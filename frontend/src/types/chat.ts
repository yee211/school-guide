export interface ChatSource {
  title: string
  source: string
}

export interface ChatResponse {
  message: string
  answer: string
  sources: ChatSource[]
}

export interface HistoryTurn {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
}
