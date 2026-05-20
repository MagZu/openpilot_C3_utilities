# openpilot C3 Utilities

Tools and patches for running openpilot on a **Comma 3 with a pre-Autopilot Tesla Model S** (2014 P85, STM32F413 internal panda).

This repository collects standalone utilities that sit outside the main openpilot fork — repair scripts, hardware tools, and driver-assistance features specific to this platform.

## Contents

| Directory | Description |
|-----------|-------------|
| [Panda_fixes](Panda_fixes/) | Scripts to detect and repair panda firmware/bootstub address mismatches |
| [AutoHighBeam](AutoHighBeam/) | Automatic high beam control using the C3 road camera |

## Platform

- **Car:** 2014 Tesla Model S P85 (pre-Autopilot)
- **Device:** Comma 3 (STM32F413 internal panda, hw_type=0x06, DOS)
- **Branch:** [MagZu/openpilot](https://github.com/MagZu/openpilot) `nap-C3-dev`
- **Upstream:** [NotAutopilot/openpilot](https://github.com/NotAutopilot/openpilot)
