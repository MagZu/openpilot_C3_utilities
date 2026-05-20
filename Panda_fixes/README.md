# Panda Fixes

Scripts to detect and repair a panda firmware bootstub address mismatch on the Comma 3 internal panda (STM32F413, hw_type=0x06).

## Background

The STM32F413 has 256KB of RAM. The softloader entry mechanism works by writing a magic value to the last 4 bytes of RAM, which both the bootstub and the app must agree on. If the bootstub and app were compiled with different linker scripts, they use different addresses and the softloader check silently fails — the panda never enters bootstub mode, and `panda.flash()` crashes with `assert(self.bootstub)`.

Two linker address variants exist in the wild:

| Address | Source |
|---------|--------|
| `0x2001FFFC` | Sunnypilot-based build (STM32F407 boundary, used by MagZu `nap-C3-dev`) |
| `0x2003FFFC` | sveinmer fork (correct STM32F413 256KB boundary) |

The scripts here use C3's hardware GPIO pins (`STM_BOOT0=134`, `STM_RST_N=124`) to force DFU mode and flash the correct bootstub, bypassing the broken softloader entirely.

## Scripts

### `fix_panda_bootstub.py` — fixes `0x2003FFFC` → `0x2001FFFC`

Use this if your C3 panda has sveinmer's bootstub and you want to run the MagZu `nap-C3-dev` branch.

### `fix_panda_bootstub_to_0x2003.py` — fixes `0x2001FFFC` → `0x2003FFFC`

Use this if your C3 panda has the sunnypilot bootstub and you want to run sveinmer's `nap-c3-dev-upstream-port` branch.

## Usage

Run on the C3 via SSH:

```bash
# Copy the script to the C3 first, then:
python3 /data/fix_panda_bootstub.py
```

The script will:
1. Stop pandad
2. Check that the correct firmware binaries exist in `panda/board/obj/`
3. Test softloader entry — if it works, exits cleanly with no changes
4. If mismatch detected: enters DFU via hardware GPIO, flashes new bootstub, flashes app, verifies

Make sure `panda/board/obj/bootstub.panda.bin` matches the target address before running, or the script will reject it with a clear error message.
