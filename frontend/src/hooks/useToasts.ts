import { useCallback, useRef, useState } from 'react'
import type { ToastItem } from '../components/Toasts'

export interface ToastsApi {
  toasts: ToastItem[]
  notify: (message: string, kind?: ToastItem['kind']) => void
  dismiss: (id: number) => void
}

export function useToasts(): ToastsApi {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const toastIdRef = useRef(0)

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const notify = useCallback((message: string, kind: ToastItem['kind'] = 'success') => {
    const id = ++toastIdRef.current
    setToasts((prev) => [...prev, { id, message, kind }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3000)
  }, [])

  return { toasts, notify, dismiss }
}