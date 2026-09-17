import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteThread,
  fetchThread,
  fetchThreads,
  streamChat,
} from './api'
import ChatView, { type ToolActivity, type UiMessage } from './components/ChatView'
import ConfirmDialog from './components/ConfirmDialog'
import Sidebar from './components/Sidebar'
import type { ThreadSummary } from './types'

export default function App() {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<UiMessage[]>([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamText, setStreamText] = useState('')
  const [toolActivity, setToolActivity] = useState<ToolActivity[]>([])
  const [error, setError] = useState<string | null>(null)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)

  const abortRef = useRef<AbortController | null>(null)

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

  const newChat = useCallback(() => {
    abortRef.current?.abort()
    setActiveId(null)
    setMessages([])
    setStreamText('')
    setToolActivity([])
    setError(null)
    setStreaming(false)
  }, [])

  const selectThread = useCallback(async (threadId: string) => {
    abortRef.current?.abort()
    setStreaming(false)
    setStreamText('')
    setToolActivity([])
    setError(null)
    setActiveId(threadId)
    try {
      const detail = await fetchThread(threadId)
      setMessages(
        detail.messages
          .filter(
            (m): m is typeof m & { role: 'user' | 'assistant' } =>
              m.role === 'user' || m.role === 'assistant',
          )
          .map((m, i) => ({ id: `${threadId}-${i}`, role: m.role, content: m.content })),
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
      void refreshThreads()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete thread')
    } finally {
      setPendingDelete(null)
    }
  }, [activeId, newChat, pendingDelete, refreshThreads])

  const pendingThread = threads.find((t) => t.thread_id === pendingDelete)

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || streaming) return

    setInput('')
    setError(null)
    setStreamText('')
    setToolActivity([])
    setMessages((prev) => [
      ...prev,
      { id: `u-${Date.now()}`, role: 'user', content: text },
    ])
    setStreaming(true)

    const controller = new AbortController()
    abortRef.current = controller
    let currentId = activeId
    let acc = ''

    try {
      for await (const evt of streamChat(text, currentId ?? undefined, controller.signal)) {
        switch (evt.event) {
          case 'start':
            if (!currentId) {
              currentId = evt.thread_id
              setActiveId(evt.thread_id)
            }
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

      setMessages((prev) => [
        ...prev,
        { id: `a-${Date.now()}`, role: 'assistant', content: acc || '…' },
      ])
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Chat failed')
      }
    } finally {
      setStreaming(false)
      setStreamText('')
      setToolActivity([])
      abortRef.current = null
      void refreshThreads()
    }
  }, [activeId, input, refreshThreads, streaming])

  return (
    <div className="flex h-screen">
      <Sidebar
        threads={threads}
        activeId={activeId}
        disabled={streaming}
        onSelect={(id) => void selectThread(id)}
        onNew={newChat}
        onDelete={(id) => void handleDelete(id)}
      />
      <ChatView
        messages={messages}
        streaming={streaming}
        stream={streamText}
        toolActivity={toolActivity}
        error={error}
        input={input}
        onInputChange={setInput}
        onSend={() => void handleSend()}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete conversation?"
        body={
          <>
            This will permanently delete
            {pendingThread?.last_message ? (
              <>
                {' '}
                &ldquo;{pendingThread.last_message.content}&rdquo;
              </>
            ) : (
              ' this conversation'
            )}{' '}
            and all of its messages. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => void confirmDelete()}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  )
}