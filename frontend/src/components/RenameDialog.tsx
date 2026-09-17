import { useEffect, useRef, useState } from 'react'

interface RenameDialogProps {
  open: boolean
  currentTitle: string
  onSave: (title: string) => void
  onCancel: () => void
}

export default function RenameDialog({ open, currentTitle, onSave, onCancel }: RenameDialogProps) {
  const [value, setValue] = useState(currentTitle)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!open) return
    const focusTimer = setTimeout(() => inputRef.current?.select(), 0)
    const escHandler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel()
    }
    window.addEventListener('keydown', escHandler)
    return () => {
      clearTimeout(focusTimer)
      window.removeEventListener('keydown', escHandler)
    }
  }, [open, onCancel])

  if (!open) return null

  const submit = () => {
    if (value.trim()) onSave(value.trim())
    else onCancel()
  }

  return (
    <div
      className="bg-black/40 fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="rename-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="rename-title" className="mb-2 text-lg font-semibold text-slate-800">
          Rename conversation
        </h2>
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit()
          }}
          maxLength={120}
          className="w-full rounded-lg border border-slate-200 px-3.5 py-2.5 text-sm text-slate-800 outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/15"
        />
        <div className="mt-6 flex justify-end gap-2">
          <button
            className="cursor-pointer rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button
            className="cursor-pointer rounded-lg bg-indigo-500 px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-indigo-600"
            onClick={submit}
          >
            Save
          </button>
        </div>
      </div>
    </div>
  )
}