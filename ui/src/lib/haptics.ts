/** Local-mode stub — haptics are unavailable in the Hermes plugin dashboard tab. */

export type HapticIntent =
  | 'cancel'
  | 'close'
  | 'crisp'
  | 'error'
  | 'open'
  | 'selection'
  | 'streamDone'
  | 'streamStart'
  | 'submit'
  | 'success'
  | 'tap'
  | 'warning'

export function registerHapticTrigger(_trigger: unknown): void {}

export function triggerHaptic(_intent: HapticIntent = 'selection'): void {}
