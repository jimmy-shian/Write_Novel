# -*- coding: utf-8 -*-
"""Port prompt for start.bat: visible countdown + pause-on-key input.

UI goes to STDERR (stays on the real console, refreshed in place with CR).
RESULT goes to STDOUT as exactly one line, e.g. ``8000``.

* No key within 5 seconds  -> 8000 (auto start).
* Digit key                 -> countdown pauses, user finishes typing + Enter.
* Enter key right away      -> 8000 immediately.
* No console available      -> 8000 immediately (non-interactive safe).

Stdlib only, Windows (msvcrt). Called by start.bat like::

    "%PYTHON%" "scripts\\prompt_port.py" > "%TEMP%\\AI_Novel_port.txt"
"""

import sys
import time

DEFAULT_PORT = "8000"
TOTAL_SECONDS = 5
WIPE = " " * 80


def ui_write(text):
    sys.stderr.write(text)
    sys.stderr.flush()


def emit_result(port):
    port = (port or "").strip() or DEFAULT_PORT
    sys.stdout.write(port + "\n")
    sys.stdout.flush()


def run_interactive(msvcrt):
    deadline = time.time() + TOTAL_SECONDS
    shown = -1
    first_digit = None
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch()
            if ch in ("\r", "\n"):
                ui_write("\n")
                emit_result(DEFAULT_PORT)
                return 0
            if "0" <= ch <= "9":
                first_digit = ch
                break
            if ch in ("\x00", "\xe0"):
                try:
                    msvcrt.getwch()  # eat second code of special key
                except Exception:
                    pass
            continue  # ignore anything else, keep counting down
        now = time.time()
        if now >= deadline:
            break
        import math
        remain = max(1, math.ceil(deadline - now))
        if remain != shown:
            shown = remain
            ui_write(
                "\r[?] 剩餘 %d 秒自動用 8000，按數字鍵自訂 "
                "(Enter 直接用 8000):   " % remain
            )
        time.sleep(0.05)

    if first_digit is None:  # timed out
        ui_write("\n")
        emit_result(DEFAULT_PORT)
        return 0

    # paused: wipe countdown line, then read the rest at leisure.
    # The input line redraws in place on every keystroke so the
    # "(Enter=...)" preview always matches the current buffer.
    buf = first_digit
    ui_write(
        "\r" + WIPE + "\r"
        "[*] 倒數暫停，請輸入完整 port 後按 Enter：\n"
    )

    def draw_input():
        preview = buf or DEFAULT_PORT
        ui_write("\r" + WIPE + "\rport=%s  (Enter=%s)" % (buf, preview))

    draw_input()
    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            break
        if ch in ("\x00", "\xe0"):
            try:
                msvcrt.getwch()  # eat second code of special key
            except Exception:
                pass
            continue
        if ch in ("\x08", "\x7f"):
            if buf:
                buf = buf[:-1]
                draw_input()
            continue
        buf += ch
        draw_input()
    ui_write("\n")
    emit_result(buf)
    return 0


def main():
    try:
        import msvcrt
        msvcrt.kbhit()  # probe: raises when there is no console
    except Exception:
        emit_result(DEFAULT_PORT)
        return 0
    try:
        return run_interactive(msvcrt)
    except Exception:
        try:
            ui_write("\n")
        except Exception:
            pass
        emit_result(DEFAULT_PORT)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
