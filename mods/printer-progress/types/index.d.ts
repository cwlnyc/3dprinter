export type PrinterStatus = {
  state: 'printing' | 'waiting' | 'idle' | 'done' | 'cancelled' | 'connecting' | 'error' | 'unreachable'
  sent: number
  total: number
  minutes: number
  text: string
  last: string
  checkedAt: number
}

declare module 'claude-code' {
  interface PluginState {
    'printer-progress': { status: Shaped<PrinterStatus | null> }
  }
}
