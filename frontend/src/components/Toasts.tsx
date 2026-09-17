export interface ToastItem {
  id: number
  message: string
  kind: 'success' | 'error'
}

interface ToastsProps {
  toasts: ToastItem[]
  onDismiss: (id: number) => void
}

function CheckIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`${className} shrink-0`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20 6 9 17l-5-5" />
    </svg>
  )
}

function AlertIcon({ className = '' }: { className?: string }) {
  return (
    <svg
      className={`${className} shrink-0`}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </svg>
  )
}

export default function Toasts({ toasts, onDismiss }: ToastsProps) {
  if (toasts.length === 0) return null
  return (
    <div className="fixed top-4 right-4 z-[60] flex w-72 flex-col gap-2">
      {toasts.map((toast) => {
        const success = toast.kind === 'success'
        return (
          <div
            key={toast.id}
            className={`animate-toast-in flex items-start gap-2.5 rounded-lg border p-3 text-sm shadow-lg backdrop-blur ${
              success
                ? 'border-emerald-200 bg-emerald-50/95 text-emerald-800'
                : 'border-red-200 bg-red-50/95 text-red-700'
            }`}
            role="status"
          >
            {success ? (
              <CheckIcon className="mt-0.5 h-4 w-4 text-emerald-500" />
            ) : (
              <AlertIcon className="mt-0.5 h-4 w-4 text-red-500" />
            )}
            <span className="min-w-0 flex-1">{toast.message}</span>
            <button
              className="cursor-pointer text-lg leading-none text-current opacity-50 hover:opacity-100"
              onClick={() => onDismiss(toast.id)}
              aria-label="Dismiss notification"
            >
              ×
            </button>
          </div>
        )
      })}
    </div>
  )
}