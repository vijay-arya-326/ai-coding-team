import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchThread, resumeChat, stopChat, streamChat } from '../api'
import type { ToolActivity, UiMessage } from '../components/ChatView'
import type { ApprovalDecision, ApprovalInfo, StreamEvent } from '../types'

export interface UseChatSessionOptions {
  notify: (message: string, kind?: 'success' | 'error') => void
  onNavigateChat: () => void
  onThreadsChanged: () => void
}

export interface ChatSession {
  activeId: string | null
  setActiveId: (id: string | null) => void
  messages: UiMessage[]
  input: string
  setInput: (value: string) => void
  streaming: boolean
  streamText: string
  streamStartedAt: number | null
  streamElapsedMs: number
  toolActivity: ToolActivity[]
  error: string | null
  approvals: ApprovalInfo[]
  approvalDecisions: Record<string, ApprovalDecision>
  newChat: () => void
  selectThread: (threadId: string) => Promise<void>
  handleSend: () => Promise<void>
  handleStop: () => void
  handleApproval: (approvalId: string, approved: boolean, allow?: 'always') => Promise<void>
  reportError: (message: string) => void
}

export function useChatSession({
  notify,
  onNavigateChat,
  onThreadsChanged,
}: UseChatSessionOptions): ChatSession {
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null)
  const [streamElapsedMs, setStreamElapsedMs] = useState(0)
  const [toolActivity, setToolActivity] = useState<ToolActivity[]>([])
  const [error, setError] = useState<string | null>(null)
  const [approvals, setApprovals] = useState<ApprovalInfo[]>([])
  const [approvalDecisions, setApprovalDecisions] = useState<Record<string, ApprovalDecision>>({})

  const abortRef = useRef<AbortController | null>(null)
  const stoppedRef = useRef(false)
  const streamThreadIdRef = useRef<string | null>(null)

  useEffect(() => {
    if (streamStartedAt === null) return
    const timer = setInterval(() => setStreamElapsedMs(Date.now() - streamStartedAt), 250)
    return () => clearInterval(timer)
  }, [streamStartedAt])

  useEffect(() => () => abortRef.current?.abort(), [])

  const resetSession = useCallback(() => {
    abortRef.current?.abort()
    setMessages([])
    setStreamText('')
    setToolActivity([])
    setError(null)
    setStreaming(false)
    setStreamStartedAt(null)
    setStreamElapsedMs(0)
    setApprovals([])
    setApprovalDecisions({})
  }, [])

  const reportError = useCallback((message: string) => {
    setError(message)
  }, [])

  const handleStop = useCallback(() => {
    stoppedRef.current = true
    if (streamThreadIdRef.current) void stopChat(streamThreadIdRef.current)
    abortRef.current?.abort()
  }, [])

  const runStream = useCallback(
    async (
      makeGen: (signal: AbortSignal) => AsyncGenerator<StreamEvent>,
      threadId: string | null,
    ): Promise<boolean> => {
      const controller = new AbortController()
      abortRef.current = controller
      let currentId = threadId
      let acc = ''
      let startedAt = 0
      let failed = false
      stoppedRef.current = false
      streamThreadIdRef.current = null
      setStreaming(true)
      setStreamText('')
      setToolActivity([])
      setStreamStartedAt(null)
      setStreamElapsedMs(0)

      try {
        for await (const evt of makeGen(controller.signal)) {
          switch (evt.event) {
            case 'start':
              if (!currentId) {
                currentId = evt.thread_id
                setActiveId(evt.thread_id)
              }
              streamThreadIdRef.current = currentId
              startedAt = Date.now()
              setStreamStartedAt(startedAt)
              break
            case 'token':
              acc += evt.delta
              setStreamText(acc)
              break
            case 'tool_start':
              setToolActivity((prev) => [...prev, { name: evt.tool }])
              break
            case 'tool_end':
              setToolActivity((prev) =>
                prev.map((t, i) =>
                  i === prev.length - 1 && t.name === evt.tool ? { ...t, output: evt.output } : t,
                ),
              )
              break
            case 'approval':
              setApprovals((prev) => [
                ...prev,
                {
                  approval_id: evt.approval_id,
                  kind: evt.kind,
                  description: evt.description,
                  command: evt.command,
                  path: evt.path,
                },
              ])
              break
            case 'error':
              throw new Error(evt.detail)
            case 'end':
              break
          }
        }

        const elapsedMs = startedAt ? Date.now() - startedAt : 0
        setMessages((prev) => [
          ...prev,
          {
            id: `a-${Date.now()}`,
            role: 'assistant',
            content: acc || '…',
            createdAt: new Date().toISOString(),
            meta: { startedAt, elapsedMs },
          },
        ])
        return true
      } catch (err) {
        failed = true
        if (!controller.signal.aborted) {
          setError(err instanceof Error ? err.message : 'Chat failed')
        } else if (stoppedRef.current) {
          const elapsedMs = startedAt ? Date.now() - startedAt : 0
          setMessages((prev) => [
            ...prev,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              content: acc || '…',
              createdAt: new Date().toISOString(),
              meta: { startedAt, elapsedMs },
            },
          ])
          setError(null)
          failed = false
        } else {
          failed = false
        }
        return !failed
      } finally {
        setStreaming(false)
        setStreamText('')
        setToolActivity([])
        setStreamStartedAt(null)
        setStreamElapsedMs(0)
        streamThreadIdRef.current = null
        abortRef.current = null
        onThreadsChanged()
      }
    },
    [onThreadsChanged],
  )

  const hasPendingApproval = approvals.some((a) => !approvalDecisions[a.approval_id])

  const handleApproval = useCallback(
    async (approvalId: string, approved: boolean, allow?: 'always') => {
      const threadId = streamThreadIdRef.current ?? activeId
      if (!threadId || streaming) return
      setApprovalDecisions((prev) => ({ ...prev, [approvalId]: { approved, allow } }))
      const ok = await runStream(
        (signal) => resumeChat(threadId, approvalId, approved, allow, signal),
        threadId,
      )
      if (ok) {
        if (!approved) notify('Action rejected', 'error')
        else if (allow === 'always') notify('Approved; command added to the allowlist', 'success')
        else notify('Action approved and executed', 'success')
      } else {
        setApprovalDecisions((prev) => {
          const next = { ...prev }
          delete next[approvalId]
          return next
        })
        notify('Failed to resume the agent after the decision', 'error')
      }
    },
    [activeId, notify, runStream, streaming],
  )

  const newChat = useCallback(() => {
    resetSession()
    setActiveId(null)
    onNavigateChat()
  }, [onNavigateChat, resetSession])

  const selectThread = useCallback(
    async (threadId: string) => {
      resetSession()
      setActiveId(threadId)
      onNavigateChat()
      try {
        const detail = await fetchThread(threadId)
        setMessages(
          detail.messages
            .filter(
              (m): m is typeof m & { role: 'user' | 'assistant' } =>
                m.role === 'user' || m.role === 'assistant',
            )
            .map((m, i) => ({
              id: `${threadId}-${i}`,
              role: m.role,
              content: m.content,
              createdAt: m.created_at,
              meta:
                m.stream_elapsed_ms != null && m.stream_started_at
                  ? {
                      startedAt: new Date(m.stream_started_at).getTime(),
                      elapsedMs: m.stream_elapsed_ms,
                    }
                  : null,
            })),
        )
        setApprovals(
          detail.pending_approval ? [detail.pending_approval] : [],
        )
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load thread')
      }
    },
    [resetSession, onNavigateChat],
  )

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming || hasPendingApproval) return

    const now = new Date().toISOString()
    setInput('')
    setError(null)
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: text, createdAt: now },
    ])
    await runStream(
      (signal) => streamChat(text, activeId ?? undefined, signal),
      activeId,
    )
  }, [activeId, hasPendingApproval, input, runStream, streaming])

  return {
    activeId,
    setActiveId,
    messages,
    input,
    setInput,
    streaming,
    streamText,
    streamStartedAt,
    streamElapsedMs,
    toolActivity,
    error,
    approvals,
    approvalDecisions,
    newChat,
    selectThread,
    handleSend,
    handleStop,
    handleApproval,
    reportError,
  }
}