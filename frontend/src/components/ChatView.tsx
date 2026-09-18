import { useEffect, useRef, useState } from 'react'
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
}

interface ChatViewProps {
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
  onDecideApproval: (approvalId: string, approved: boolean, allow?: 'once' | 'always') => void
}

export default function ChatView({
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

  const send = () => {
    atBottomRef.current = true
    onSend()
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !streaming) send()
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
              <MessageBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
                createdAt={msg.createdAt}
                meta={msg.meta}
                showRaw={showRaw}
              />
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
          <div className="flex flex-wrap gap-1.5 self-start">
            {toolActivity.map((tool, i) => (
              <span
                key={i}
                className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs text-slate-600"
              >
                ⚙ {tool.name}
                {tool.output !== undefined && (
                  <em className="text-emerald-700 not-italic"> → {tool.output}</em>
                )}
              </span>
            ))}
          </div>
        )}

        {approvals.map((a) => {
          const decision = approvalDecisions[a.approval_id]
          return (
            <div
              key={a.approval_id}
              className="w-full max-w-md self-start rounded-xl border border-amber-200 bg-amber-50 p-3.5"
            >
              <div className="flex items-center gap-2 text-[13px] font-semibold text-amber-800">
                <span aria-hidden="true">⚠</span> Action requires approval
              </div>
              <p className="mt-1 text-[13px] leading-snug text-amber-900">{a.description}</p>
              {a.command && (
                <code className="mt-1.5 block rounded-md bg-white/70 px-2 py-1 text-[12px] break-all font-mono text-slate-700">
                  {a.command}
                </code>
              )}
              {!decision ? (
                <div className="mt-2.5 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onDecideApproval(a.approval_id, true)}
                    className="cursor-pointer rounded-lg bg-emerald-600 px-3.5 py-1.5 text-[13px] font-semibold text-white transition-colors hover:bg-emerald-700"
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => onDecideApproval(a.approval_id, true, 'once')}
                    className="cursor-pointer rounded-lg border border-emerald-600 bg-white px-3.5 py-1.5 text-[13px] font-semibold text-emerald-700 transition-colors hover:bg-emerald-50"
                  >
                    Approve &amp; Allow once
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
              ) : decision.status === 'rejected' ? (
                <p className="mt-2.5 text-[12px] text-slate-500">✕ Rejected — nothing was executed.</p>
              ) : decision.status === 'approved' ? (
                <>
                  <pre className="mt-2.5 max-h-40 overflow-auto rounded-lg bg-white/80 px-2.5 py-2 text-[11.5px] leading-relaxed break-words whitespace-pre-wrap font-mono text-slate-700">
                    {decision.result ?? decision.output ?? ''}
                    {decision.exit_code != null ? `exit ${decision.exit_code}` : ''}
                    {decision.error ? `Error: ${decision.error}` : ''}
                  </pre>
                  {(decision.allow_granted === 'once' || decision.allow_granted === 'always') && (
                    <p className="mt-1.5 text-[11.5px] text-slate-500">
                      {decision.allow_granted === 'once'
                        ? 'Exemption granted — the same command auto-runs once next time.'
                        : 'Exemption granted — the same command is allowed permanently.'}
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-2.5 text-[12px] text-slate-500">Approval not found (may have expired).</p>
              )}
            </div>
          )
        })}
        <div ref={bottomRef} />
      </div>

      <form
        className="mx-auto flex w-full max-w-3xl gap-2.5 px-6 pb-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim() && !streaming) send()
        }}
      >
        <textarea
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the agent something…"
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
            disabled={!input.trim()}
            className="self-end cursor-pointer rounded-xl bg-indigo-500 px-5 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Send
          </button>
        )}
      </form>
    </section>
  )
}