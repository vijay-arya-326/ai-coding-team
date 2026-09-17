interface MessageBubbleProps {
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
}

export default function MessageBubble({ role, content, streaming }: MessageBubbleProps) {
  const assistant = role === 'assistant'
  return (
    <div
      className={`max-w-[78%] whitespace-pre-wrap break-words rounded-[14px] border border-slate-200 px-3.5 py-3 text-[15px] leading-relaxed ${
        assistant ? 'self-start rounded-bl-[4px] bg-white' : 'self-end rounded-br-[4px] bg-indigo-50'
      }`}
    >
      <div className="mb-1 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
        {assistant ? 'Agent' : 'You'}
      </div>
      <div className="text-slate-800">{content}</div>
      {streaming && (
        <span
          className="bg-indigo-500 inline-block h-[15px] w-2 animate-blink align-text-bottom"
          aria-hidden="true"
        />
      )}
    </div>
  )
}