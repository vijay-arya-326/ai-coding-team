export interface MessageDto {
  role: 'user' | 'assistant' | 'tool'
  content: string
  created_at: string | null
  stream_started_at?: string | null
  stream_elapsed_ms?: number | null
  attachments?: { name: string; mime?: string; path?: string }[]
}

export interface ThreadSummary {
  thread_id: string
  title: string | null
  archived: boolean
  workspace_id: string | null
  chat_type: string | null
  message_count: number
  created_at: string | null
  updated_at: string | null
  last_message: MessageDto | null
  first_user_message: string | null
}

export interface AttachmentMeta {
  name: string
  path?: string
  mime?: string
  size?: number
}

export interface ThreadDetail {
  thread_id: string
  title: string | null
  archived: boolean
  workspace_id: string | null
  chat_type: string | null
  attachments: AttachmentMeta[]
  created_at: string | null
  updated_at: string | null
  messages: MessageDto[]
  pending_approval: ApprovalInfo | null
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
  | {
      event: 'approval'
      approval_id: string
      kind: string
      description: string
      command?: string | null
      path?: string | null
    }
  | { event: 'end'; content?: string }
  | { event: 'error'; detail: string }

export interface ApprovalInfo {
  approval_id: string
  kind: string
  description: string
  command?: string | null
  path?: string | null
}

export interface ApprovalDecision {
  approved: boolean
  allow?: 'once' | 'always'
}

export type ApprovalMode = 'once' | 'always'

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
  workspace_id: string | null
}

export interface WorkspaceConfig {
  safe_commands?: string[]
  unsafe_commands?: string[]
  allowed_commands?: string[]
  exemptions?: string[]
}

export interface Workspace {
  id: string
  name: string
  root_path: string
  is_default: boolean
  config: WorkspaceConfig
  guidelines?: string
  created_at: string | null
  updated_at: string | null
  active: boolean
}

export interface FolderEntry {
  name: string
  path: string
}

export interface BrowseResult {
  path: string
  name: string
  parent: string | null
  entries: FolderEntry[]
}

export interface ThreadRuns {
  thread_id: string
  title: string | null
  archived: boolean
  workspace_id: string | null
  run_count: number
  totals: RunTotals
  runs: RunRound[]
}

export interface BackgroundActivity {
  detail: string
  completed: boolean
  updated_by: string | null
  updated_at: string | null
}
