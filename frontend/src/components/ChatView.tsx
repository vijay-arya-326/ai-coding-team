import { useEffect, useRef } from 'react'
import MessageBubble from './MessageBubble'

export interface ToolActivity {
  name: string
  output?: string
}

export interface UiMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

interface ChatViewProps {
  messages: UiMessage[]
  streaming: boolean
  stream: string
  toolActivity: ToolActivity[]
  error: string | null
  input: string
  onInputChange: (value: string) => void
  onSend: () => void
}

export default function ChatView({
  messages,
  streaming,
  stream,
  toolActivity,
  error,
  input,
  onInputChange,
  onSend,
}: ChatViewProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages.length, stream, toolActivity.length])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (input.trim() && !streaming) onSend()
    }
  }

  const isEmpty = messages.length === 0 && !streaming

  return (
    <section className="flex h-full min-w-0 flex-1 flex-col bg-slate-100">
      <div className="mx-auto flex w-full max-w-3xl flex-1 min-h-0 flex-col gap-4 overflow-y-auto px-6 py-6">
        {isEmpty ? (
          <div className="m-auto max-w-[480px] text-center text-slate-500">
            <h2 className="mb-2 text-xl font-semibold text-slate-800">Chat with your agent</h2>
            <p className="leading-relaxed">
              Powered by a LangGraph agent running on phi3 via Ollama. Conversations are stored per
              thread in SQLite.
            </p>
          </div>
        ) : (
          <>
            {messages.map((msg) => (
              <MessageBubble key={msg.id} role={msg.role} content={msg.content} />
            ))}
            {streaming && <MessageBubble role="assistant" content={stream} streaming />}
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
        <div ref={bottomRef} />
      </div>

      <form
        className="mx-auto flex w-full max-w-3xl gap-2.5 px-6 pb-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (input.trim() && !streaming) onSend()
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
        <button
          type="submit"
          disabled={streaming || !input.trim()}
          className="self-end cursor-pointer rounded-xl bg-indigo-500 px-5 py-3 text-[15px] font-semibold text-white transition-colors hover:bg-indigo-600 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {streaming ? 'Streaming…' : 'Send'}
        </button>
      </form>
    </section>
  )
}