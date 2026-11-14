import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import MessageBubble, { type BubbleMeta } from './MessageBubble'
import type { ApprovalDecision, ApprovalInfo } from '../types'

export interface ToolActivity {
  name: string
  output?: string
}

export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: string | null
  meta?: BubbleMeta | null
  attachments?: { name: string; mime?: string }[]
}

interface ChatViewProps {
  attachments: { name: string; type: string; data: string }[]
  onAttach: (file: File) => void
  onRemoveAttachment: (index: number) => void
  messages: UiMessage[]
  streaming: boolean
  stream: string
  streamStartedAt: number | null
  streamElapsedMs: number
  toolActivity: ToolActivity[]
  approvals: ApprovalInfo[]
  approvalDecisions: Record<string, ApprovalDecision>
  error: string | null
  input: string
  onInputChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  onDecideApproval: (approvalId: string, approved: boolean, allow?: 'always') => void
}

export default function ChatView({
  attachments,
  onAttach,
  onRemoveAttachment,
  messages,
  streaming,
  stream,
  streamStartedAt,
  streamElapsedMs,
  toolActivity,
  approvals,
  approvalDecisions,
  error,
  input,
  onInputChange,
  onSend,
  onStop,
  onDecideApproval,
}: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const atBottomRef = useRef(true)
  const [showRaw, setShowRaw] = useState(false)
  const [webSearchCountdown, setWebSearchCountdown] = useState<number | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    atBottomRef.current = distance < 80
  }

  useEffect(() => {
    if (!atBottomRef.current) return
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, stream, streamElapsedMs, toolActivity.length, streaming])

  const pendingApproval = approvals.some((a) => !approvalDecisions[a.approval_id])
  const webSearchApproval = approvals.find(
    (a) => a.kind === 'web_search' && !approvalDecisions[a.approval_id],
  )

  useEffect(() => {
    if (!webSearchApproval) return
    setWebSearchCountdown(60)
    const timer = window.setInterval(() => {
      setWebSearchCountdown((seconds) => {
        if (seconds === null || seconds <= 1) {
          window.clearInterval(timer)
          onDecideApproval(webSearchApproval.approval_id, true)
          return 0
        }
        return seconds - 1
      })
    }, 1_000)
    return () => window.clearInterval(timer)
  }, [onDecideApproval, webSearchApproval])

  const send = () => {
    atBottomRef.current = true
    onSend()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !streaming && !pendingApproval) send()
    }
  }

  const isEmpty = messages.length === 0 && !streaming

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-slate-100">
      <div ref={scrollRef} onScroll={handleScroll} className="mx-auto flex w-full max-w-3xl flex-1 min-h-0 flex-col gap-4 overflow-y-auto px-6 py-6">
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowRaw((v) => !v)}
            className={`cursor-pointer rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              showRaw
                ? 'border-indigo-500 bg-indigo-500 text-white'
                : 'border-slate-300 bg-white text-slate-500 hover:border-indigo-400 hover:text-indigo-600'
            }`}
          >
            {showRaw ? 'Hide raw' : 'Show raw'}
          </button>
        </div>
        {isEmpty ? (
          <div className="m-auto max-w-[480px] text-center text-slate-500">
            <h2 className="mb-2 text-xl font-semibold text-slate-800">Chat with your agent</h2>
            <p className="leading-relaxed">
              Powered by a LangGraph agent running on llama3.1:8b via Ollama with tools (file operations, shell commands). Conversations are stored per
              thread in SQLite.
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <div key={msg.id} className={`flex w-full flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                <MessageBubble
                  role={msg.role}
                  content={msg.content}
                  createdAt={msg.createdAt}
                  meta={msg.meta}
                  showRaw={showRaw}
                />
                {msg.attachments && msg.attachments.length > 0 && (
                  <div className="mt-1 flex flex-col items-start gap-1">
                    {msg.attachments.map((a, i) => (
                      <span key={i} className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-xs text-slate-700 shadow-sm">
                        {a.mime?.startsWith('image/') ? '🖼' : '📄'} {a.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {streaming && (
              <MessageBubble
                role="assistant"
                content={stream}
                streaming
                streamStartedAt={streamStartedAt}
                streamElapsedMs={streamElapsedMs}
                showRaw={showRaw}
              />
            )}
            {error && (
              <div className="self-center rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-sm text-red-600">
                {error}
              </div>
            )}
          </>
        )}

        {toolActivity.length > 0 && (
          <div className="flex max-w-3xl flex-col gap-1.5 self-start">
            {toolActivity.map((tool, i) => (
              <div
                key={i}
                className="rounded-lg border border-slate-200 bg-slate-100 px-2.5 py-1.5 text-xs text-slate-600"
              >
                ⚙ {tool.name}
                {tool.output !== undefined && (
                  <div className="markdown mt-1 text-emerald-700">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        a: ({ href, children }) => (
                          <a href={href} target="_blank" rel="noopener noreferrer">
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {tool.output}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {approvals.map((a) => {
          if (approvalDecisions[a.approval_id]) return null
          return (
            <div
              key={a.approval_id}
              className="w-full max-w-md self-start rounded-xl border border-amber-200 bg-amber-50 p-3.5"
            >
              <div className="flex items-center gap-2 text-[13px] font-semibold text-amber-800">
                <span aria-hidden="true">⚠</span> Action requires approval
              </div>
              <p className="mt-1 text-[13px] leading-snug text-amber-900">{a.description}</p>
              {a.kind === 'web_search' && (
                <p className="mt-1 text-xs font-medium text-amber-700">
                  Auto-approves in {webSearchCountdown ?? 60} sec
                </p>
              )}
              {a.command && (
                <code className="mt-1.5 block rounded-md bg-white/70 px-2 py-1 text-[12px] break-all font-mono text-slate-700">
                  {a.command}
                </code>
              )}
              <div className="mt-2.5 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => onDecideApproval(a.approval_id, true)}
                  className="cursor-pointer rounded-lg bg-emerald-600 px-3.5 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-emerald-700"
                >
                  {a.kind === 'web_search' ? `Approve (${webSearchCountdown ?? 60}s)` : 'Approve'}
                </button>
                <button
                  type="button"
                  onClick={() => onDecideApproval(a.approval_id, true, 'always')}
                  className="cursor-pointer rounded-lg border border-emerald-600 bg-white px-3.5 py-1.5 text-[13px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-50"
                >
                  Approve &amp; Always allow
                </button>
                <button
                  type="button"
                  onClick={() => onDecideApproval(a.approval_id, false)}
                  className="cursor-pointer rounded-lg border border-slate-300 bg-white px-3.5 py-1.5 text-[13px] font-semibold text-slate-600 transition-colors hover:bg-slate-100"
                >
                  Reject
                </button>
              </div>
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      <form
        className="mx-auto flex w-full max-w-3xl flex-col gap-2 px-6 pb-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim() && !streaming && !pendingApproval) send()
        }}
      >
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {attachments.map((a, i) => (
              <span key={i} className="flex items-center gap-1 rounded-md bg-slate-200 px-2 py-1 text-xs">
                {a.type.startsWith('image/') ? '🖼' : '📄'} {a.name}
                <button type="button" onClick={() => onRemoveAttachment(i)} className="ml-1 text-slate-500 hover:text-red-500">×</button>
              </span>
            ))}
          </div>
        )}
        <div className="flex gap-2.5">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            Array.from(e.target.files || []).forEach(onAttach)
            e.target.value = ''
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="shrink-0 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm text-slate-600 hover:bg-slate-50"
          title="Attach file"
        >
          📎
        </button>
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onPaste={(e) => {
            const items = e.clipboardData?.items
            if (!items) return
            for (const item of Array.from(items)) {
              const file = item.getAsFile()
              if (file) {
                e.preventDefault()
                onAttach(file)
              }
            }
          }}
          onKeyDown={handleKeyDown}
          placeholder={
            pendingApproval
              ? 'Approve or reject the pending action to continue…'
              : 'Ask the agent something…'
          }
          rows={2}
          className="flex-1 resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-[15px] text-slate-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/15"
        />
        {streaming ? (
          <button
            type="button"
            onClick={onStop}
            className="flex cursor-pointer items-center gap-1.5 self-end rounded-xl bg-red-500 px-5 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-red-600"
          >
            <span className="text-xs" aria-hidden="true">
              ■
            </span>
            Stop
          </button>
        ) : (
          <button
            type="submit"
            disabled={!input.trim() || pendingApproval}
            className="self-end cursor-pointer rounded-xl bg-indigo-500 px-5 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Send
          </button>
        )}
        </div>
      </form>
    </section>
  )
}
