# Auto High Beam (AHB)

Automatic high beam control for pre-Autopilot Tesla Model S using the Comma 3 road camera and a FOMO headlight detector running natively on the C3.

> **Status: In development — code coming soon**

## How It Works

### Detection

A FOMO (Faster Objects More Objects) neural network model runs as a native C++ process (`ahb_fomo_runner`) on the C3, continuously analyzing the road camera feed for oncoming headlights and vehicles ahead. The model outputs detection results with confidence scores via a PTY (pseudo-terminal) socket at `/tmp/ahb_fomo_pty`.

openpilot's carcontroller polls this PTY at 10Hz and applies time-based hysteresis to filter out brief false positives:

- **Suppress delay:** 300ms of continuous detections before lowering beams
- **Clear delay:** 3500ms of continuous clear readings before restoring beams
- **Instant suppress:** High-confidence detections (≥99.6%) lower beams immediately

openpilot's own lead vehicle detection is also factored in — beams lower whenever a lead car is visible in the model output OR the FOMO detector fires.

### Detection Protocol (PTY)

| Message | Meaning |
|---------|---------|
| `O <conf>\n` | Oncoming headlight detected, confidence 0.0–1.0 |
| `T\n` | Trigger suppress (toggle event) |
| `N\n` | No detection — road is clear |

If no message is received for >2 seconds, the system treats the road as clear (fail-safe).

### Control

High beam state is controlled by spoofing the steering wheel stalk signal (`STW_ACTN_RQ`, `HiBmLvr_Stat=1`) at 100Hz on the chassis CAN bus — the same signal the driver produces when holding the high beam stalk. No hardware modifications required.

`DAS_bodyControls` (0x3E9) carries the beam decision/reason fields for logging, but the BCM on pre-AP cars only responds to the stalk spoof.

### Manual Toggle

Double-flash the high beam stalk twice within 2 seconds to enable or disable AHB. A feedback blink (HIGH → LOW → HIGH, 500ms each) confirms the toggle. State persists across reboots via `tinkla_params.json`. AHB can also be toggled in the NAP settings UI.

### Patch Mechanism

AHB is applied to a running openpilot installation via `ahb_patch.py` (in the root of this project). The script SSH's to the C3 and applies surgical text patches to:

| File | What changes |
|------|-------------|
| `carstate.py` | Adds `loBeamOn`/`hiBeamOn` from BODY_R1 (0x283) |
| `carcontroller.py` | AHB init, 10Hz update loop, PTY poll, 100Hz stalk spoof |
| `teslacan_legacy.py` | Adds `create_body_controls()` for DAS_bodyControls CAN message |
| `tinkla_conf.py` | Adds `ahb_enabled`/`ahb_feature_enabled` persistent config |
| `nap.py` | AHB toggle in NAP settings UI |

The native FOMO runner and its systemd service are installed separately via `AHB_FOMO/ahb_fomo_install.py`.

A persistence service (`ahb_persist.service`) restores the patches automatically after openpilot auto-updates.

## Hardware

- Comma 3 — road camera + C3 CPU runs the FOMO model natively
- 2014 Tesla Model S pre-AP — CAN bus access via openpilot harness
- No external hardware required

## Directory

| Path | Description |
|------|-------------|
| `model/` | Edge Impulse FOMO model files |
