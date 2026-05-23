# Install Link Checker

A small GUI tool for inspecting openpilot installer links before flashing a Comma device.

## Usage

```bash
python3 install_link_checker.py
```

Paste any installer link into the field and press **Check** (or Enter). Results are fetched live from the GitHub API.

## Supported URL formats

| Format | Example |
|--------|---------|
| `installer.comma.ai/User/branch` | `https://installer.comma.ai/MagZu/nap-C3-release` |
| `github.com/User/repo/tree/branch` | `https://github.com/MagZu/openpilot/tree/nap-C3-release` |

## What it shows

- **Repository** — description, fork parent, visibility (public/private), stars/forks
- **Branch & Commit** — branch name, short SHA, commit message, author, date
- **Panda Firmware** — sizes of `panda.bin.signed` and `bootstub.panda.bin` with a bootstub address hint (`0x2001FFFC` vs `0x2003FFFC`)
- **Submodules** — all submodule URLs and tracked branches from `.gitmodules`

## Requirements

- Python 3
- PyQt5 (`pip install PyQt5`)

## How installer.comma.ai works

The installer URL (`https://installer.comma.ai/User/branch`) is a device-only endpoint — regular browsers just see a placeholder page. When a Comma device visits it, the server returns a shell script that runs a `git clone` of `github.com/User/openpilot` on the specified branch. There is no separate validation; if the branch does not exist on GitHub the clone fails on the device.

This tool validates the branch via the GitHub API before you ever touch the device.
