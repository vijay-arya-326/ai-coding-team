export interface MessageDto {
  role: 'user' | 'assistant' | 'tool'
  content: string
  created_at: string | null
  stream_started_at?: string | null
  stream_elapsed_ms?: number | null
}

export interface ThreadSummary {
  thread_id: string
  title: string | null
  archived: boolean
  message_count: number
  created_at: string | null
  updated_at: string | null
  last_message: MessageDto | null
  first_user_message: string | null
}

export interface ThreadDetail {
  thread_id: string
  title: string | null
  archived: boolean
  created_at: string | null
  updated_at: string | null
  messages: MessageDto[]
}

export interface ThreadUpdate {
  title?: string | null
  archived?: boolean
}

export type StreamEvent =
  | { event: 'start'; thread_id: string }
  | { event: 'token'; delta: string }
  | { event: 'tool_start'; tool: string }
  | { event: 'tool_end'; tool: string; output: string }
  | { event: 'end' }
  | { event: 'error'; detail: string }

export interface ToolComm {
  name: string | null
  input: string | null
  output: string | null
}

export interface RunRound {
  run_index: number
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  input_preview: string | null
  output_preview: string | null
  tools: ToolComm[]
}

export interface RunTotals {
  input_tokens: number
  output_tokens: number
  total_tokens: number
  tool_count: number
  avg_duration_ms: number | null
}

export interface RunSummary {
  thread_id: string
  title: string | null
  run_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  tool_count: number
  last_run_at: string | null
}

export interface ThreadRuns {
  thread_id: string
  title: string | null
  archived: boolean
  run_count: number
  totals: RunTotals
  runs: RunRound[]
}