#!/usr/bin/env python3
"""
install_link_checker.py — openpilot installer link inspector

Paste an installer.comma.ai link and get branch/commit/submodule info
fetched live from the GitHub API.

Usage:
    python3 install_link_checker.py
"""

import json
import sys
import urllib.request
import urllib.error
import base64
from urllib.parse import urlparse

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPalette
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTextEdit, QFrame,
    QSizePolicy,
)


# ── GitHub API helpers ────────────────────────────────────────────────────────

HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "openpilot-install-link-checker/1.0",
}


def gh_get(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_msg": e.reason}
    except Exception as e:
        return {"_error": 0, "_msg": str(e)}


def parse_install_url(url: str) -> tuple[str, str, str] | None:
    """
    Returns (user, repo, branch) from an installer.comma.ai URL.
    Supports:
      https://installer.comma.ai/User/branch
      installer.comma.ai/User/branch
      https://github.com/User/openpilot/tree/branch
    """
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    p = urlparse(url)

    if "installer.comma.ai" in p.netloc:
        parts = p.path.strip("/").split("/")
        if len(parts) >= 2:
            return parts[0], "openpilot", parts[1]

    if "github.com" in p.netloc:
        parts = p.path.strip("/").split("/")
        # github.com/user/repo/tree/branch
        if len(parts) >= 4 and parts[2] == "tree":
            return parts[0], parts[1], "/".join(parts[3:])
        if len(parts) >= 2:
            return parts[0], parts[1], "HEAD"

    return None


def fetch_info(user: str, repo: str, branch: str) -> dict:
    result = {}

    # ── Repo ─────────────────────────────────────────────────────────────────
    repo_data = gh_get(f"https://api.github.com/repos/{user}/{repo}")
    if isinstance(repo_data, dict) and "_error" in repo_data:
        result["error"] = f"Repo not found: {repo_data['_msg']} (HTTP {repo_data['_error']})"
        return result

    result["repo_desc"]    = repo_data.get("description") or "(no description)"
    result["repo_stars"]   = repo_data.get("stargazers_count", 0)
    result["repo_forks"]   = repo_data.get("forks_count", 0)
    result["repo_private"] = repo_data.get("private", False)
    result["repo_url"]     = repo_data.get("html_url", "")
    result["default_branch"] = repo_data.get("default_branch", "")

    parent = repo_data.get("parent")
    if parent:
        result["fork_of"] = parent.get("full_name", "")

    # ── Branch ───────────────────────────────────────────────────────────────
    branch_data = gh_get(f"https://api.github.com/repos/{user}/{repo}/branches/{branch}")
    if isinstance(branch_data, dict) and "_error" in branch_data:
        result["branch_error"] = f"Branch '{branch}' not found (HTTP {branch_data['_error']})"
        return result

    commit = branch_data.get("commit", {})
    result["branch"]        = branch
    result["commit_sha"]    = commit.get("sha", "")[:12]
    result["commit_sha_full"] = commit.get("sha", "")

    commit_detail = gh_get(commit.get("url", ""))
    if isinstance(commit_detail, dict) and "_error" not in commit_detail:
        ci = commit_detail.get("commit", {})
        result["commit_msg"]    = ci.get("message", "").split("\n")[0]
        result["commit_date"]   = ci.get("committer", {}).get("date", "")
        result["commit_author"]  = ci.get("author", {}).get("name", "")
        result["changed_files"] = commit_detail.get("stats", {}).get("total", "?")

    # ── .gitmodules ───────────────────────────────────────────────────────────
    gm = gh_get(
        f"https://api.github.com/repos/{user}/{repo}/contents/.gitmodules"
        f"?ref={result['commit_sha_full']}"
    )
    if isinstance(gm, dict) and "content" in gm:
        raw = base64.b64decode(gm["content"]).decode("utf-8", errors="replace")
        result["gitmodules_raw"] = raw
        result["submodules"] = _parse_gitmodules(raw)
    else:
        result["submodules"] = {}

    # ── Panda firmware size ───────────────────────────────────────────────────
    fw = gh_get(
        f"https://api.github.com/repos/{user}/{repo}/contents/panda/board/obj"
        f"?ref={result['commit_sha_full']}"
    )
    if isinstance(fw, list):
        for f in fw:
            if f.get("name") == "panda.bin.signed":
                result["fw_app_size"] = f.get("size", 0)
            if f.get("name") == "bootstub.panda.bin":
                result["fw_boot_size"] = f.get("size", 0)

    return result


def _parse_gitmodules(raw: str) -> dict:
    """Parse .gitmodules into {name: {path, url, branch}} dict."""
    mods = {}
    current = None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("[submodule"):
            name = line.split('"')[1] if '"' in line else line
            current = name
            mods[current] = {}
        elif current and "=" in line:
            k, _, v = line.partition("=")
            mods[current][k.strip()] = v.strip()
    return mods


# ── Worker thread ─────────────────────────────────────────────────────────────

class FetchWorker(QThread):
    done    = pyqtSignal(dict)
    error   = pyqtSignal(str)

    def __init__(self, user, repo, branch):
        super().__init__()
        self.user, self.repo, self.branch = user, repo, branch

    def run(self):
        try:
            result = fetch_info(self.user, self.repo, self.branch)
            self.done.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── GUI ───────────────────────────────────────────────────────────────────────

DARK_BG   = "#1e1e2e"
PANEL_BG  = "#2a2a3e"
ACCENT    = "#89b4fa"
GREEN     = "#a6e3a1"
YELLOW    = "#f9e2af"
RED       = "#f38ba8"
MUTED     = "#6c7086"
TEXT      = "#cdd6f4"
MONO      = "JetBrains Mono, Fira Mono, Consolas, monospace"


def qlabel(text="", color=TEXT, bold=False, size=10) -> QLabel:
    lbl = QLabel(text)
    weight = "bold" if bold else "normal"
    lbl.setStyleSheet(f"color: {color}; font-weight: {weight}; font-size: {size}px;")
    lbl.setWordWrap(True)
    return lbl


def separator() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {MUTED}; background: {MUTED};")
    f.setFixedHeight(1)
    return f


class InstallLinkChecker(QWidget):
    def __init__(self):
        super().__init__()
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        self.setWindowTitle("openpilot Install Link Checker")
        self.setMinimumWidth(680)
        self.setStyleSheet(f"background-color: {DARK_BG}; color: {TEXT};")

        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        # Title
        title = qlabel("openpilot Install Link Checker", ACCENT, bold=True, size=15)
        root.addWidget(title)
        root.addWidget(separator())

        # Input row
        input_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://installer.comma.ai/User/branch-name")
        self.url_input.setStyleSheet(
            f"background: {PANEL_BG}; color: {TEXT}; border: 1px solid {MUTED};"
            f"border-radius: 4px; padding: 6px; font-size: 11px;"
        )
        self.url_input.returnPressed.connect(self._check)
        input_row.addWidget(self.url_input)

        self.btn = QPushButton("Check")
        self.btn.setFixedWidth(80)
        self.btn.setStyleSheet(
            f"background: {ACCENT}; color: {DARK_BG}; border: none;"
            f"border-radius: 4px; padding: 6px; font-weight: bold; font-size: 11px;"
        )
        self.btn.clicked.connect(self._check)
        input_row.addWidget(self.btn)
        root.addLayout(input_row)

        # Status label
        self.status_lbl = qlabel("", MUTED, size=10)
        root.addWidget(self.status_lbl)

        root.addWidget(separator())

        # Results panel
        self.results = QVBoxLayout()
        self.results.setSpacing(6)
        root.addLayout(self.results)

        root.addStretch()

        # Pre-fill the test URL
        self.url_input.setText("https://installer.comma.ai/MagZu/nap-C3-release")

    def _check(self):
        url = self.url_input.text().strip()
        if not url:
            return

        parsed = parse_install_url(url)
        if not parsed:
            self.status_lbl.setStyleSheet(f"color: {RED}; font-size: 10px;")
            self.status_lbl.setText("Could not parse URL — expected installer.comma.ai/User/branch")
            return

        user, repo, branch = parsed
        self.status_lbl.setStyleSheet(f"color: {MUTED}; font-size: 10px;")
        self.status_lbl.setText(f"Fetching {user}/{repo}@{branch} ...")
        self.btn.setEnabled(False)
        self._clear_results()

        self.worker = FetchWorker(user, repo, branch)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _clear_results(self):
        while self.results.count():
            item = self.results.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_error(self, msg):
        self.btn.setEnabled(True)
        self.status_lbl.setText(f"Error: {msg}")
        self.status_lbl.setStyleSheet(f"color: {RED}; font-size: 10px;")

    def _on_done(self, data: dict):
        self.btn.setEnabled(True)

        if "error" in data:
            self.status_lbl.setText(data["error"])
            self.status_lbl.setStyleSheet(f"color: {RED}; font-size: 10px;")
            return

        self.status_lbl.setText("Done")
        self.status_lbl.setStyleSheet(f"color: {GREEN}; font-size: 10px;")

        r = self.results

        def row(label, value, val_color=TEXT):
            h = QHBoxLayout()
            lbl = qlabel(label, MUTED, size=10)
            lbl.setFixedWidth(140)
            val = qlabel(str(value), val_color, size=10)
            h.addWidget(lbl)
            h.addWidget(val)
            h.addStretch()
            w = QWidget()
            w.setLayout(h)
            r.addWidget(w)

        def section(title):
            r.addWidget(separator())
            r.addWidget(qlabel(title, ACCENT, bold=True, size=11))

        # ── Repo ─────────────────────────────────────────────────────────────
        section("Repository")
        row("URL", data.get("repo_url", ""))
        if data.get("fork_of"):
            row("Fork of", data["fork_of"], YELLOW)
        row("Description", data.get("repo_desc", ""))
        row("Stars / Forks", f"★ {data.get('repo_stars',0)}  ⑂ {data.get('repo_forks',0)}")
        visibility = "Private" if data.get("repo_private") else "Public"
        row("Visibility", visibility, YELLOW if data.get("repo_private") else GREEN)

        # ── Branch / Commit ───────────────────────────────────────────────────
        section("Branch & Commit")
        row("Branch", data.get("branch", ""), ACCENT)

        branch_err = data.get("branch_error")
        if branch_err:
            r.addWidget(qlabel(branch_err, RED, size=10))
        else:
            row("Commit", data.get("commit_sha", ""), YELLOW)
            row("Message", data.get("commit_msg", ""))
            row("Author", data.get("commit_author", ""))
            date = data.get("commit_date", "")
            if date:
                row("Date", date[:10] + "  " + date[11:19] + " UTC")

        # ── Panda firmware ────────────────────────────────────────────────────
        if "fw_app_size" in data or "fw_boot_size" in data:
            section("Panda Firmware")
            if "fw_boot_size" in data:
                size = data["fw_boot_size"]
                addr_hint = "0x2001FFFC" if size < 12000 else "0x2003FFFC (sveinmer)"
                row("bootstub.panda.bin", f"{size:,} bytes  ({addr_hint})", YELLOW)
            if "fw_app_size" in data:
                row("panda.bin.signed", f"{data['fw_app_size']:,} bytes")

        # ── Submodules ────────────────────────────────────────────────────────
        subs = data.get("submodules", {})
        if subs:
            section("Submodules")
            for name, info in subs.items():
                url  = info.get("url", "")
                brnch = info.get("branch", "")
                val = url
                if brnch:
                    val += f"  [{brnch}]"
                row(name, val, TEXT)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Dark palette base
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(DARK_BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT))
    pal.setColor(QPalette.Base, QColor(PANEL_BG))
    pal.setColor(QPalette.Text, QColor(TEXT))
    app.setPalette(pal)

    w = InstallLinkChecker()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
