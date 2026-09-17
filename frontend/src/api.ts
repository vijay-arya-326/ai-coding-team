import type { StreamEvent, ThreadDetail, ThreadSummary } from './types'

const BASE = '/api'

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

export function fetchThreads(): Promise<ThreadSummary[]> {
  return jsonFetch<ThreadSummary[]>(`${BASE}/threads`)
}

export function fetchThread(threadId: string): Promise<ThreadDetail> {
  return jsonFetch<ThreadDetail>(`${BASE}/threads/${encodeURIComponent(threadId)}`)
}

export function deleteThread(threadId: string): Promise<void> {
  return jsonFetch<void>(`${BASE}/threads/${encodeURIComponent(threadId)}`, {
    method: 'DELETE',
  })
}

function parseEvent(raw: string): StreamEvent | null {
  let type = 'message'
  let data = ''
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) type = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  let payload: unknown
  try {
    payload = JSON.parse(data)
  } catch {
    return null
  }
  switch (type) {
    case 'start':
      return { event: 'start', thread_id: (payload as { thread_id: string }).thread_id }
    case 'token':
      return { event: 'token', delta: (payload as { delta: string }).delta }
    case 'tool_start':
      return { event: 'tool_start', tool: payload as string }
    case 'tool_end':
      return {
        event: 'tool_end',
        tool: (payload as { name: string }).name,
        output: (payload as { output: string }).output,
      }
    case 'end':
      return { event: 'end' }
    case 'error':
      return { event: 'error', detail: (payload as { detail: string }).detail }
    default:
      return null
  }
}

export async function* streamChat(
  message: string,
  threadId?: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal,
  })
  if (!res.ok || !res.body) {
    throw new Error(`Chat request failed: ${res.status}`)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true }).replace(/\r/g, '')
    let index: number
    while ((index = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      const evt = parseEvent(raw)
      if (evt) yield evt
    }
  }
}