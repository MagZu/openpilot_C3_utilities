#!/usr/bin/env python3
"""
fix_panda_bootstub.py — NAP C3 panda repair tool

Detects bootstub/app address mismatch (sunnypilot 0x2001FFFC vs F413 0x2003FFFC)
and repairs via hardware DFU using C3 GPIO pins STM_BOOT0 / STM_RST_N.

This happens when the panda bootstub was compiled from sunnypilot (STM32F407,
128KB boundary) but the app firmware targets the real F413 (256KB boundary).
The softloader entry mechanism uses a RAM magic value; if bootstub and app
disagree on the address, the softloader check always fails → panda stays in
app mode → panda.flash() assert(self.bootstub) crashes pandad.

Run on C3:
    python3 /data/openpilot/fix_panda_bootstub.py

Requirements:
    - /data/openpilot/panda/board/obj/bootstub.panda.bin  (correct 0x2003FFFC)
    - /data/openpilot/panda/board/obj/panda.bin.signed    (matching app)
    - Run as root or user with GPIO access (normal C3 user is fine)
    - pandad must not be running (script stops it automatically)
"""

import os
import sys
import time
import struct
import subprocess

sys.path.insert(0, '/data/openpilot')

PANDA_DIR      = '/data/openpilot/panda'
BOOTSTUB_BIN   = os.path.join(PANDA_DIR, 'board/obj/bootstub.panda.bin')
APP_BIN        = os.path.join(PANDA_DIR, 'board/obj/panda.bin.signed')

GOOD_ADDR      = 0x2003FFFC   # STM32F413, 256KB — correct
BAD_ADDR       = 0x2001FFFC   # STM32F407/sunnypilot 128KB — wrong for F413


def log(msg):
    print(f"[fix_bootstub] {msg}", flush=True)


# ── helpers ──────────────────────────────────────────────────────────────────

def stop_pandad():
    """Kill pandad so it releases the panda USB connection."""
    r = subprocess.run(['pkill', '-f', 'pandad'], capture_output=True)
    if r.returncode == 0:
        log("pandad stopped")
        time.sleep(1.5)
    else:
        log("pandad was not running")


def check_binaries():
    """Verify firmware files exist and show their bootstub SP address."""
    for path in [BOOTSTUB_BIN, APP_BIN]:
        if not os.path.exists(path):
            log(f"ERROR: {path} not found")
            log("       Run compile_firmware.sh first, or git pull to get pre-built binaries.")
            sys.exit(1)

    with open(BOOTSTUB_BIN, 'rb') as f:
        sp = struct.unpack('<I', f.read(4))[0]

    size_bs  = os.path.getsize(BOOTSTUB_BIN)
    size_app = os.path.getsize(APP_BIN)
    log(f"bootstub: {size_bs} bytes, initial SP = 0x{sp:08X}")
    log(f"app:      {size_app} bytes")

    if sp == BAD_ADDR:
        log("WARNING: board/obj/bootstub.panda.bin is the OLD sunnypilot build (0x2001FFFC).")
        log("         Flashing it would keep the mismatch. Update the repo first.")
        sys.exit(1)
    elif sp != GOOD_ADDR:
        log(f"WARNING: bootstub SP is 0x{sp:08X} — unexpected. Proceeding anyway.")
    else:
        log("bootstub SP confirmed correct (0x2003FFFC)")


def wait_for_panda(timeout=10, want_bootstub=None):
    from panda import Panda
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            serials = Panda.list()
            if serials:
                p = Panda(serials[0])
                if want_bootstub is None or p.bootstub == want_bootstub:
                    return p
                p.close()
        except Exception:
            pass
        time.sleep(0.5)
    return None


def wait_for_dfu(timeout=12):
    from panda import PandaDFU
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            serials = PandaDFU.list()
            if serials:
                return serials[0]
        except Exception:
            pass
        time.sleep(0.5)
    return None


# ── detection ────────────────────────────────────────────────────────────────

def detect_mismatch():
    """
    Returns True if softloader entry is broken (bootstub/app address mismatch).
    Tries reset(enter_bootstub=True) and checks if panda comes back in bootstub mode.
    """
    log("Connecting to panda ...")
    p = wait_for_panda(timeout=6)
    if p is None:
        log("No panda found. Is the C3 panda powered? (check USB)")
        sys.exit(1)

    ver = p.get_version()
    log(f"Panda version: {ver!r}, bootstub={p.bootstub}")

    if p.bootstub:
        log("Panda is stuck in bootstub/softloader mode — fix needed")
        p.close()
        return True

    log("Testing softloader entry (reset + enter_bootstub) ...")
    try:
        p.reset(enter_bootstub=True)
    except Exception:
        pass   # USB disconnect during reset is normal
    p.close()
    time.sleep(2.0)

    p2 = wait_for_panda(timeout=8)
    if p2 is None:
        log("Panda not found after softloader reset — assuming mismatch")
        return True

    mismatch = not p2.bootstub
    if mismatch:
        log(f"MISMATCH: panda came back in app mode (bootstub=False) → address mismatch confirmed")
    else:
        ver2 = p2.get_version()
        log(f"Softloader entry OK (bootstub=True, version={ver2!r}) — no fix needed")
        try:
            p2.reset()   # back to app
        except Exception:
            pass
    p2.close()
    return mismatch


# ── fix ───────────────────────────────────────────────────────────────────────

def do_dfu_fix():
    from panda import Panda, PandaDFU
    from openpilot.system.hardware import HARDWARE

    # Step 1 — Hardware DFU via GPIO
    log("Step 1/4: Hardware DFU entry (GPIO STM_BOOT0=134 + STM_RST_N=124) ...")
    HARDWARE.recover_internal_panda()
    time.sleep(2.5)

    serial = wait_for_dfu(timeout=12)
    if serial is None:
        r = subprocess.run(['lsusb'], capture_output=True, text=True)
        log(f"ERROR: DFU device (0483:df11) not found after GPIO recovery.")
        log(f"lsusb:\n{r.stdout}")
        sys.exit(1)
    log(f"DFU device ready: {serial}")

    # Step 2 — Flash new bootstub
    log("Step 2/4: Flashing bootstub via DFU ...")
    PandaDFU(serial).recover()
    log("Bootstub flashed OK")
    time.sleep(3.0)

    # Step 3 — Flash app
    log("Step 3/4: Connecting and flashing app firmware ...")
    p = wait_for_panda(timeout=10)
    if p is None:
        log("ERROR: Panda not found after bootstub flash")
        sys.exit(1)
    log(f"Connected: version={p.get_version()!r}, bootstub={p.bootstub}")
    p.flash()
    log("App flashed OK")
    p.close()
    time.sleep(2.5)

    # Step 4 — Verify
    log("Step 4/4: Verifying ...")
    p = wait_for_panda(timeout=8)
    if p is None:
        log("ERROR: Panda not found after app flash")
        sys.exit(1)
    log(f"Running: version={p.get_version()!r}, bootstub={p.bootstub}")

    try:
        p.reset(enter_bootstub=True)
    except Exception:
        pass
    p.close()
    time.sleep(2.0)

    p2 = wait_for_panda(timeout=8)
    if p2 is None:
        log("WARNING: Panda not found on verification reset — but app flash succeeded")
        return

    if p2.bootstub:
        log(f"SUCCESS: Softloader entry working. version={p2.get_version()!r}")
        try:
            p2.reset()   # back to normal app mode
        except Exception:
            pass
    else:
        log(f"WARNING: Softloader re-test inconclusive (bootstub={p2.bootstub})")
    p2.close()


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    log("=== NAP panda bootstub repair ===")
    log(f"Firmware path: {PANDA_DIR}/board/obj/")

    stop_pandad()
    check_binaries()

    if not detect_mismatch():
        log("No fix needed. You can restart pandad.")
        return

    log("")
    log("Address mismatch detected — proceeding with DFU repair ...")
    log("")
    do_dfu_fix()
    log("")
    log("Done. You can now start openpilot normally.")


if __name__ == '__main__':
    main()
