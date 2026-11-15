import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { PrinterStatus } from '../types'

const PANE = 'printer-progress'
// Run from the 3dprinter folder: the connector's address and secret come from
// workspace/connector.json there, as `python3 -m hwplot remote` reads them.
const CHECK =
  'if [ -x .venv/bin/python3 ]; then P=.venv/bin/python3; else P=python3; fi; ' +
  'exec "$P" -m hwplot remote printer_status "{}"'
const EVERY_MS = 20_000

const status = atom({ plugin: 'printer-progress', key: 'status' } as const, null, { shape: 'status-1' })

// "Printing: 7670/58083 lines (13%), 85.7 min so far. Waiting for the knob..."
export function parse(out: string, now: number): PrinterStatus {
  const lines = out.trim().split('\n')
  const head = lines.find(l => /^(Printing|Idle|Done|Cancelled|Connecting|Error)/.test(l)) ?? ''
  const last = (lines.find(l => l.startsWith('Last from printer:')) ?? '').replace('Last from printer: ', '')
  const base = { sent: 0, total: 0, minutes: 0, text: head, last, checkedAt: now }
  const m = head.match(/^Printing: (\d+)\/(\d+) lines \(\d+%\), ([\d.]+) min/)
  if (m) {
    const state = head.includes('Waiting for the knob') ? 'waiting' : 'printing'
    return { ...base, state, sent: Number(m[1]), total: Number(m[2]), minutes: Number(m[3]) }
  }
  if (head.startsWith('Idle')) return { ...base, state: 'idle' }
  if (head.startsWith('Done')) return { ...base, state: 'done' }
  if (head.startsWith('Cancelled')) return { ...base, state: 'cancelled' }
  if (head.startsWith('Connecting')) return { ...base, state: 'connecting' }
  if (head.startsWith('Error')) return { ...base, state: 'error' }
  return { ...base, state: 'unreachable', text: 'Can’t reach the Pi right now.' }
}

function remaining(s: PrinterStatus): string {
  if (s.sent < 50 || s.minutes <= 0) return ''
  const left = (s.minutes * (s.total - s.sent)) / s.sent
  return left >= 60 ? `~${Math.floor(left / 60)} h ${Math.round(left % 60)} min left` : `~${Math.round(left)} min left`
}

let busy = false

async function poll($: EngineInterface) {
  if (busy) return
  busy = true
  try {
    const r = await $.process.run(
      ['sh', '-c', CHECK],
      { timeoutMs: 90_000 },
    )
    const s = parse(r.stdout + '\n' + r.stderr, await $.clock.now())
    const before = await read($, status)
    await update($, status, () => s)
    const pct = s.total ? Math.floor((100 * s.sent) / s.total) : 0
    $.ui.status(s.state === 'printing' || s.state === 'waiting' ? `🖨 ${pct}%` : undefined)
    if (before && before.state !== s.state && (s.state === 'done' || s.state === 'error')) {
      $.ui.toast(s.state === 'done' ? 'Printer: finished.' : `Printer: ${s.text}`)
    }
  } catch {
    await update($, status, (old): PrinterStatus => ({ ...(old ?? parse('', 0)), state: 'unreachable', text: 'Can’t reach the Pi right now.' }))
  } finally {
    busy = false
  }
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'printer', description: 'Show the 3D printer’s progress in a pane' })
    void $.ui.open({ id: PANE, title: '3D printer' })
    void poll($)
    $.clock.every(EVERY_MS, () => void poll($))
    return next(e)
  })

  on('command.run', { command: 'printer' }, async $ => {
    const opened = await $.ui.open({ id: PANE, title: '3D printer' })
    void poll($)
    return {
      text: opened.isPlaced
        ? 'Printer pane opened.'
        : 'reason' in opened && String(opened.reason).startsWith('no-surface')
          ? 'The app you are using does not draw mod panels or bars in this session; ask Claude "how\'s the print" instead.'
          : `This app doesn't show panes here (${'reason' in opened ? opened.reason : 'no room'}); the progress bar is above the message box instead.`,
    }
  })

  // The same bar, compact, above the message box: for apps that don't show panes.
  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const s = await read($, status)
    if (!s || !(s.state === 'printing' || s.state === 'waiting' || s.state === 'connecting')) return next(e)
    const { Box, Text, Progress } = $.ui.resolve(e)
    const pct = s.total ? Math.floor((100 * s.sent) / s.total) : 0
    const label = s.state === 'connecting' ? 'Printer: heating up' : s.state === 'waiting' ? 'Printer: press the knob' : `Printer ${pct}%`
    return (
      <Box flexDirection="row" gap={1}>
        <Text>{label}</Text>
        {s.state === 'connecting'
          ? <Progress label="Printer heating up" />
          : <Progress label="Print progress" value={s.sent} max={s.total} valueText={`${pct}%`} />}
        {remaining(s) ? <Text dimColor>{remaining(s)}</Text> : null}
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Progress } = $.ui.resolve(e)
    const s = await read($, status)
    if (!s) return <Box><Text dimColor>Checking the printer…</Text></Box>
    const active = s.state === 'printing' || s.state === 'waiting'
    const pct = s.total ? Math.floor((100 * s.sent) / s.total) : 0
    const checked = new Date(s.checkedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    const headline: Record<PrinterStatus['state'], string> = {
      printing: `Printing — ${pct}%`,
      waiting: 'Paused — press the knob on the printer',
      idle: 'Idle',
      done: 'Done ✓',
      cancelled: 'Cancelled',
      connecting: 'Connecting to the printer…',
      error: 'Problem',
      unreachable: 'Pi not answering',
    }
    return (
      <Box flexDirection="column" gap={1}>
        <Text bold color={s.state === 'error' ? 'red' : s.state === 'done' ? 'green' : undefined}>
          {headline[s.state]}
        </Text>
        {active && (
          <Progress label="Print progress" value={s.sent} max={s.total} valueText={`${pct}%`} />
        )}
        {s.state === 'connecting' && <Progress label="Heating up / connecting" />}
        {active && (
          <Text dimColor>
            {Math.round(s.minutes)} min so far{remaining(s) ? ` · ${remaining(s)}` : ''}
          </Text>
        )}
        {(s.state === 'error' || s.state === 'unreachable') && <Text>{s.text}</Text>}
        <Text dimColor>Checked {checked} · updates every 20 s</Text>
      </Box>
    )
  })
}
