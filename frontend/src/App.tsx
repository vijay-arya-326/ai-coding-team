import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteThread, fetchThread, fetchThreads, stopChat, streamChat, updateThread } from './api'
import ChatView, { type ToolActivity, type UiMessage } from './components/ChatView'
import ConfirmDialog from './components/ConfirmDialog'
import RenameDialog from './components/RenameDialog'
import Sidebar from './components/Sidebar'
import Toasts, { type ToastItem } from './components/Toasts'
import type { ThreadSummary } from './types'

export default function App() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null)
  const [streamElapsedMs, setStreamElapsedMs] = useState(0)
  const [toolActivity, setToolActivity] = useState<ToolActivity[]>([])
  const [error, setError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<{ id: string; title: string } | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const abortRef = useRef<AbortController | null>(null)
  const toastIdRef = useRef(0)
  const stoppedRef = useRef(false)
  const streamThreadIdRef = useRef<string | null>(null)

  const handleStop = useCallback(() => {
    stoppedRef.current = true
    if (streamThreadIdRef.current) void stopChat(streamThreadIdRef.current)
    abortRef.current?.abort()
  }, [])

  const notify = useCallback((message: string, kind: ToastItem['kind'] = 'success') => {
    const id = ++toastIdRef.current
    setToasts((prev) => [...prev, { id, message, kind }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3000)
  }, [])

  useEffect(() => {
    if (streamStartedAt === null) return
    const timer = setInterval(() => setStreamElapsedMs(Date.now() - streamStartedAt), 250)
    return () => clearInterval(timer)
  }, [streamStartedAt])

  const refreshThreads = useCallback(async () => {
    try {
      setThreads(await fetchThreads())
    } catch {
      /* keep previous list */
    }
  }, [])

  useEffect(() => {
    void refreshThreads()
    return () => abortRef.current?.abort()
  }, [refreshThreads])

  const threadLabel = useCallback(
    (threadId: string): string => {
      const t = threads.find((x) => x.thread_id === threadId)
      return t?.title ?? t?.first_user_message ?? ''
    },
    [threads],
  )

  const newChat = useCallback(() => {
    abortRef.current?.abort()
    setActiveId(null)
    setMessages([])
    setStreamText('')
    setToolActivity([])
    setError(null)
    setStreaming(false)
    setStreamStartedAt(null)
    setStreamElapsedMs(0)
  }, [])

  const selectThread = useCallback(async (threadId: string) => {
    abortRef.current?.abort()
    setStreaming(false)
    setStreamText('')
    setToolActivity([])
    setError(null)
    setStreamStartedAt(null)
    setStreamElapsedMs(0)
    setActiveId(threadId)
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
          })),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load thread')
    }
  }, [])

  const handleDelete = useCallback((threadId: string) => {
    setPendingDelete(threadId)
  }, [])

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return
    const threadId = pendingDelete
    try {
      await deleteThread(threadId)
      if (threadId === activeId) newChat()
      await refreshThreads()
      notify('Conversation deleted')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete thread')
      notify('Failed to delete conversation', 'error')
    } finally {
      setPendingDelete(null)
    }
  }, [activeId, newChat, notify, pendingDelete, refreshThreads])

  const pendingThread = threads.find((t) => t.thread_id === pendingDelete)

  const handleRename = useCallback(
    (threadId: string) => {
      setRenaming({ id: threadId, title: threadLabel(threadId) })
    },
    [threadLabel],
  )

  const submitRename = useCallback(
    async (title: string) => {
      if (!renaming) return
      try {
        await updateThread(renaming.id, { title })
        await refreshThreads()
        notify('Conversation renamed')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to rename thread')
        notify('Failed to rename conversation', 'error')
      } finally {
        setRenaming(null)
      }
    },
    [refreshThreads, renaming, notify],
  )

  const toggleArchive = useCallback(
    async (threadId: string) => {
      const thread = threads.find((t) => t.thread_id === threadId)
      try {
        await updateThread(threadId, { archived: !thread?.archived })
        await refreshThreads()
        notify(!thread?.archived ? 'Conversation archived' : 'Conversation restored')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update thread')
        notify('Failed to update conversation', 'error')
      }
    },
    [notify, refreshThreads, threads],
  )

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming) return

    const now = new Date().toISOString()
    setInput('')
    setError(null)
    setStreamText('')
    setToolActivity([])
    setStreamStartedAt(null)
    setStreamElapsedMs(0)
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: text, createdAt: now },
    ])
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller
    let currentId = activeId
    let acc = ''
    let startedAt = 0
    stoppedRef.current = false
    streamThreadIdRef.current = null

    try {
      for await (const evt of streamChat(text, currentId ?? undefined, controller.signal)) {
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
                i === prev.length - 1 && t.name === evt.tool
                  ? { ...t, output: evt.output }
                  : t,
              ),
            )
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
    } catch (err) {
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
      }
    } finally {
      setStreaming(false)
      setStreamText('')
      setToolActivity([])
      setStreamStartedAt(null)
      setStreamElapsedMs(0)
      streamThreadIdRef.current = null
      abortRef.current = null
      void refreshThreads()
    }
  }, [activeId, input, refreshThreads, streaming])

  return (
    <div className="flex h-screen">
      <Toasts toasts={toasts} onDismiss={(id) => setToasts((prev) => prev.filter((t) => t.id !== id))} />
      <Sidebar
        threads={threads}
        activeId={activeId}
        disabled={streaming}
        showArchived={showArchived}
        onToggleArchived={() => setShowArchived((v) => !v)}
        onSelect={(id) => void selectThread(id)}
        onNew={newChat}
        onRename={handleRename}
        onArchive={(id) => void toggleArchive(id)}
        onDelete={(id) => void handleDelete(id)}
      />
      <ChatView
        messages={messages}
        streaming={streaming}
        stream={streamText}
        streamStartedAt={streamStartedAt}
        streamElapsedMs={streamElapsedMs}
        toolActivity={toolActivity}
        error={error}
        input={input}
        onInputChange={setInput}
        onSend={() => void handleSend()}
        onStop={handleStop}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete conversation?"
        body={
          <>
            This will permanently delete{' '}
            {pendingThread
              ? `“${pendingThread.title ?? pendingThread.last_message?.content ?? 'this conversation'}”`
              : 'this conversation'}{' '}
            and all of its messages. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
      <RenameDialog
        key={renaming?.id ?? 'closed'}
        open={renaming !== null}
        currentTitle={renaming?.title ?? ''}
        onSave={(title) => void submitRename(title)}
        onCancel={() => setRenaming(null)}
      />
    </div>
  )
}