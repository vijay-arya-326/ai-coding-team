export interface MessageDto {
  role: 'user' | 'assistant' | 'tool'
  content: string
}

export interface ThreadSummary {
  thread_id: string
  message_count: number
  created_at: string | null
  updated_at: string | null
  last_message: MessageDto | null
}

export interface ThreadDetail {
  thread_id: string
  created_at: string | null
  updated_at: string | null
  messages: MessageDto[]
}

export type StreamEvent =
  | { event: 'start'; thread_id: string }
  | { event: 'token'; delta: string }
  | { event: 'tool_start'; tool: string }
  | { event: 'tool_end'; tool: string; output: string }
  | { event: 'end' }
  | { event: 'error'; detail: string }