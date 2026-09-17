import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { formatTimestamp } from '../api'

export interface BubbleMeta {
  startedAt: number
  elapsedMs: number
}

interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  createdAt?: string | null
  meta?: BubbleMeta | null
  streaming?: boolean
  streamStartedAt?: number | null
  streamElapsedMs?: number
}

function UserIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`${className} shrink-0`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-2.2 3.6-4 8-4s8 1.8 8 4" />
    </svg>
  )
}

function AssistantIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`${className} shrink-0`}
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 2 14.4 7.2l5.6 1-4 4.2 1 5.6-5-2.9-5 2.9 1-5.6-4-4.2 5.6-1z" />
      <circle cx="19.5" cy="4.5" r="1.5" />
    </svg>
  )
}

function stripAssistantFence(content: string): string {
  const lines = content.split(/\r?\n/)
  if (lines.length === 0 || !lines[0].trim().startsWith('```')) {
    return content
  }
  const rest = lines.slice(1)
  if (rest.length > 0 && rest[rest.length - 1].trim().startsWith('```')) {
    rest.pop()
  }
  return rest.join('\n').trim()
}

function formatDuration(elapsedMs: number): string {
  const totalSec = Math.max(0, Math.round(elapsedMs / 1000))
  if (totalSec < 60) return `${totalSec} sec`
  return `${Math.floor(totalSec / 60)}m ${totalSec % 60} sec`
}

export default function MessageBubble({
  role,
  content,
  createdAt,
  meta,
  streaming,
  streamStartedAt,
  streamElapsedMs = 0,
}: MessageBubbleProps) {
  const assistant = role === 'assistant'
  const rendered = assistant ? stripAssistantFence(content) : content
  const streamMeta =
    streaming && streamStartedAt
      ? `Started ${formatTimestamp(new Date(streamStartedAt).toISOString())} · streaming ${(
          streamElapsedMs / 1000
        ).toFixed(1)}s`
      : null
  const duration = meta ? `[${formatDuration(meta.elapsedMs)}]` : null

  return (
    <div
      className={`flex max-w-[85%] items-start gap-2.5 ${
        assistant ? 'self-start' : 'self-end'
      }`}
    >
      {assistant && (
        <span className="mt-3 flex h-8 w-8 items-center justify-center rounded-full bg-indigo-500 text-white">
          <AssistantIcon className="h-4 w-4" />
        </span>
      )}
      <div
        className={`min-w-0 rounded-[14px] border border-slate-200 px-3.5 py-3 text-[15px] leading-relaxed ${
          assistant
            ? 'rounded-bl-[4px] bg-white'
            : 'rounded-br-[4px] bg-indigo-50'
        }`}
      >
        <div className="mb-1 flex items-baseline gap-2">
          <span className="text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
            {assistant ? 'Agent' : 'You'}
          </span>
        </div>
        <div className="markdown break-words text-slate-800">
          <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml>
            {rendered}
          </ReactMarkdown>
        </div>
        {(createdAt || duration) && (
          <div className="mt-1 text-right text-[11px] text-slate-400">
            {createdAt && <span>{formatTimestamp(createdAt)}</span>}
            {duration && <span> {duration}</span>}
          </div>
        )}
        {streamMeta && (
          <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-indigo-600">
            <span className="h-2 w-2 animate-blink rounded-full bg-indigo-500" />
            {streamMeta}
          </div>
        )}
      </div>
      {!assistant && (
        <span className="mt-3 flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-slate-600">
          <UserIcon className="h-4 w-4" />
        </span>
      )}
    </div>
  )
}