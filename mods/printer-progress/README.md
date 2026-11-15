# printer-progress

A Claude Code mod: a "3D printer" panel with a live progress bar, time so far and
time left, plus the percentage in the status line and a pop-up when a print
finishes or fails. It asks the Pi's connector for `printer_status` every 20 seconds.

Run Claude Code from the 3dprinter folder, on the Mac that set up the connector
(its address and secret are read from `workspace/connector.json`):

    claude --plugin-dir mods/printer-progress

`/printer` opens the panel again if it was closed.
