"""Sending G-code to the printer over its USB cable, instead of carrying an SD card.

Marlin takes one line at a time and answers "ok" when it has room for the next,
so the sender waits for that before each line. Every line carries a number and
a checksum: if one arrives garbled the printer asks for it again ("Resend: N")
rather than acting on half a command, which matters when the command is
"move the pen down".

Opening the port resets the printer's board, so the first few seconds go to
letting it start up.
"""
from __future__ import annotations

import glob
import threading
import time
from dataclasses import dataclass, field

BAUD = 115200
# The Ender 3's USB chip shows up under one of these on a Mac (or Linux).
PORT_PATTERNS = ("/dev/cu.usbserial*", "/dev/cu.wchusbserial*", "/dev/cu.usbmodem*",
                 "/dev/ttyUSB*", "/dev/ttyACM*")


def find_port(preferred: str = "") -> str | None:
    if preferred:
        return preferred
    for pattern in PORT_PATTERNS:
        found = sorted(glob.glob(pattern))
        if found:
            return found[0]
    return None


def commands(gcode: str) -> list[str]:
    """The lines worth sending: comments and blank lines dropped."""
    out = []
    for line in gcode.splitlines():
        line = line.split(";", 1)[0].strip()
        if line:
            out.append(line)
    return out


def framed(n: int, cmd: str) -> str:
    """N<line> <cmd>*<checksum>, the form Marlin checks."""
    body = f"N{n} {cmd}"
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{body}*{cs}"


@dataclass
class Job:
    total: int = 0
    sent: int = 0
    state: str = "idle"  # idle, connecting, printing, waiting (for the knob), done, cancelled, error
    message: str = ""
    log: list[str] = field(default_factory=list)
    started: float = 0.0

    def summary(self) -> str:
        if self.state in ("printing", "waiting"):
            pct = 100 * self.sent / self.total if self.total else 0
            mins = (time.time() - self.started) / 60
            extra = " Waiting for the knob on the printer to be pressed." if self.state == "waiting" else ""
            return f"Printing: {self.sent}/{self.total} lines ({pct:.0f}%), {mins:.1f} min so far.{extra}"
        return {"idle": "Idle: nothing printing.", "connecting": "Connecting to the printer...",
                "done": "Done: the last job finished.", "cancelled": "Cancelled."}.get(
            self.state, f"Error: {self.message}")


class Sender:
    """Streams one job at a time on a background thread."""

    def __init__(self, port: str = "", open_serial=None):
        self.port = port
        self.job = Job()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._open = open_serial or self._default_open

    @staticmethod
    def _default_open(port: str):
        import serial  # pyserial; imported here so the rest works without it
        return serial.Serial(port, BAUD, timeout=1)

    @property
    def busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, gcode: str) -> str:
        if self.busy:
            return "The printer is already busy with a job."
        port = find_port(self.port)
        if not port:
            self.job = Job(state="error", message="no printer found on USB")
            return "No printer found on USB. Is the cable plugged in and the printer switched on?"
        self._stop.clear()
        self.job = Job(total=0, state="connecting", started=time.time())
        self._thread = threading.Thread(target=self._run, args=(port, commands(gcode)), daemon=True)
        self._thread.start()
        return f"Started on {port}."

    def cancel(self) -> None:
        self._stop.set()

    def _readline(self, ser) -> str:
        raw = ser.readline()
        line = raw.decode(errors="replace").strip()
        if line:
            self.job.log = (self.job.log + [line])[-20:]
        return line

    def _run(self, port: str, cmds: list[str]) -> None:
        job = self.job
        try:
            ser = self._open(port)
        except Exception as e:  # pyserial raises its own types; report any of them
            job.state, job.message = "error", f"couldn't open {port}: {e}"
            return
        try:
            # The board restarts when the port opens; wait until it has finished.
            deadline = time.time() + 12
            while time.time() < deadline and not self._stop.is_set():
                line = self._readline(ser)
                if line.startswith("start") or "echo:SD" in line or "Marlin" in line:
                    time.sleep(1.0)
                    break
            ser.reset_input_buffer()
            job.total, job.state = len(cmds), "printing"
            n = 1
            if not self._send(ser, 0, "M110 N0"):  # start line numbering from here
                return
            while n <= len(cmds):
                if self._stop.is_set():
                    break
                cmd = cmds[n - 1]
                job.state = "waiting" if cmd.startswith(("M0", "M1 ")) or cmd == "M1" else "printing"
                reply = self._send(ser, n, cmd)
                if reply is None:
                    return
                if reply is not True:  # a line number (bool is an int too, hence "is not True")
                    n = reply  # printer missed a line: go back to it
                    continue
                job.sent = n
                n += 1
            if self._stop.is_set():
                # Lift the pen clear and stop; the paper stays where it is.
                for i, cmd in enumerate(("M410", "G91", "G0 Z10 F900", "G90"), start=n):
                    ser.write((framed(i, cmd) + "\n").encode())
                job.state = "cancelled"
            else:
                job.state = "done"
        except Exception as e:  # never leave the job showing "printing" after the thread died
            job.state, job.message = "error", f"{type(e).__name__}: {e}"
        finally:
            try:
                ser.close()
            except Exception:
                pass

    def _send(self, ser, n: int, cmd: str):
        """Send one line; True when acknowledged, an int to resend from, None on failure."""
        ser.write((framed(n, cmd) + "\n").encode())
        quiet_since = time.time()
        while not self._stop.is_set():
            line = self._readline(ser)
            if not line:
                # Homing, levelling and waiting for the knob can each be silent for a while.
                if time.time() - quiet_since > 600:
                    self.job.state, self.job.message = "error", f"no reply from the printer after: {cmd}"
                    return None
                continue
            quiet_since = time.time()
            if line.startswith("ok"):
                return True
            if line.lower().startswith(("resend:", "rs:")):
                try:
                    again = int(line.split(":", 1)[1].strip().split()[0])
                except ValueError:
                    again = n
                # Marlin follows a resend request with an "ok" for the bad line; take it
                # here, or it would be counted as the acknowledgement of the resent one.
                for _ in range(20):
                    if self._readline(ser).startswith("ok"):
                        break
                return again
            if line.startswith("Error:") and "Line Number" not in line and "checksum" not in line.lower():
                if "Printer halted" in line or "kill" in line.lower():
                    self.job.state, self.job.message = "error", line
                    return None
        return True  # cancelled while waiting: the caller stops
