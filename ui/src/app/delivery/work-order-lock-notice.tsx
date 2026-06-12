export function WorkOrderLockNotice({ message }: { message: string | null }) {
  if (!message) {
    return null
  }
  return (
    <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
      {message} — actions are read-only until the lock is released.
    </p>
  )
}
