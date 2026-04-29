#!/usr/bin/env python3
"""
Windows-first bootstrap installer for RLBot GUI, RLBotPack, and Python deps.

This script is designed to be packaged as a standalone .exe with PyInstaller.
"""

from __future__ import annotations

import argparse
import configparser
import datetime as dt
import queue
import os
import json
import textwrap
import shutil
import subprocess
import sys
import threading
import tempfile
import urllib.request
import zipfile
import re
import traceback
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover - tkinter may be unavailable in some environments.
    tk = None
    messagebox = None
    ttk = None


DEFAULT_RLBOT_GUI_URL = "https://github.com/RLBot/RLBotGUI/releases/download/v1.0/RLBotGUI.msi"
DEFAULT_RLBOTPACK_ZIP_URL = "https://codeload.github.com/RLBot/RLBotPack/zip/refs/heads/master"
DEFAULT_PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
DEFAULT_EXTRA_PACKAGES: list[str] = []
DEFAULT_TRAINING_BRIDGE_PROTOCOL = "rocketcoach"
TARGET_BOT_CFG_HINTS: dict[str, list[str]] = {
    "aether": ["aether\\src\\bot.cfg", "aether/src/bot.cfg"],
    "botimus_prime": ["botimus&bumblebee\\botimus.cfg", "botimus&bumblebee/botimus.cfg"],
    "necto": ["necto\\necto\\bot.cfg", "necto/necto/bot.cfg"],
    "nexto": ["necto\\nexto\\bot.cfg", "necto/nexto/bot.cfg"],
    "noob_blue": ["noob_blue\\src\\bot.cfg", "noob_blue/src/bot.cfg"],
}
TARGET_BOTPACK_REQUIREMENT_HINTS: tuple[str, ...] = (
    "RLDojo\\Dojo\\requirements.txt",
    "RLDojo/Dojo/requirements.txt",
)
_LOG_FILE_PATH: Path | None = None


def log(message: str) -> None:
    line = f"[installer] {message}"
    if sys.stdout is not None:
        try:
            print(line, flush=True)
        except Exception:
            pass
    if _LOG_FILE_PATH is not None:
        _LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE_PATH.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(line + "\n")


def setup_logging(install_root: Path) -> Path:
    global _LOG_FILE_PATH
    logs_dir = install_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    _LOG_FILE_PATH = logs_dir / "rlbot_stack_installer.log"
    header = (
        "\n"
        f"=== RLBotStackInstaller run started {dt.datetime.now().isoformat(timespec='seconds')} ===\n"
    )
    with _LOG_FILE_PATH.open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(header)
    return _LOG_FILE_PATH


class InstallerProgressWindow:
    def __init__(self, enabled: bool) -> None:
        self.enabled = bool(enabled and os.name == "nt" and tk is not None and ttk is not None)
        self._queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._root = None
        self._title_var = None
        self._phase_var = None
        self._detail_var = None
        self._progress_var = None
        self._closing = False
        self._result = 0
        self._error: Exception | None = None
        self._error_text = ""

        if not self.enabled:
            return

        self._root = tk.Tk()
        self._root.title("RocketCoach Installer")
        self._root.geometry("560x240")
        self._root.minsize(560, 240)
        self._root.resizable(False, False)
        try:
            self._root.attributes("-topmost", True)
            self._root.after(500, lambda: self._root.attributes("-topmost", False))
        except Exception:
            pass

        self._title_var = tk.StringVar(value="Preparing RocketCoach installer...")
        self._phase_var = tk.StringVar(value="Starting")
        self._detail_var = tk.StringVar(value="Initializing installer...")
        self._progress_var = tk.DoubleVar(value=5.0)

        container = ttk.Frame(self._root, padding=18)
        container.pack(fill="both", expand=True)

        title_label = ttk.Label(container, textvariable=self._title_var, font=("Segoe UI", 12, "bold"))
        title_label.pack(anchor="w")
        ttk.Label(container, textvariable=self._phase_var).pack(anchor="w", pady=(8, 0))
        ttk.Label(container, textvariable=self._detail_var, wraplength=520, justify="left").pack(anchor="w", pady=(4, 10))

        progress = ttk.Progressbar(container, mode="determinate", maximum=100.0, variable=self._progress_var)
        progress.pack(fill="x")

        self._summary_var = tk.StringVar(value="Follow the progress below. Logs continue to write to the installer log file.")
        ttk.Label(container, textvariable=self._summary_var, wraplength=520, justify="left").pack(anchor="w", pady=(10, 0))

        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        if self._closing:
            return
        if self._error:
            self.close()

    def phase(self, name: str, detail: str = "", progress: float | None = None) -> None:
        if not self.enabled:
            return
        self._queue.put(("phase", (name, detail, progress)))

    def log_line(self, message: str) -> None:
        if not self.enabled:
            return
        self._queue.put(("log", message))

    def finish_success(self, message: str = "Install complete.") -> None:
        if not self.enabled:
            return
        self._queue.put(("success", message))

    def finish_warning(self, message: str) -> None:
        if not self.enabled:
            return
        self._queue.put(("warning", message))

    def finish_error(self, message: str, exc: Exception | None = None) -> None:
        if not self.enabled:
            return
        self._queue.put(("error", (message, exc)))

    def close(self) -> None:
        self._closing = True
        if self.enabled and self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    def _process_queue(self) -> None:
        if not self.enabled or self._root is None:
            return
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "phase":
                    name, detail, progress = payload  # type: ignore[misc]
                    if self._title_var is not None:
                        self._title_var.set(f"RocketCoach Installer - {name}")
                    if self._phase_var is not None:
                        self._phase_var.set(str(name))
                    if self._detail_var is not None:
                        self._detail_var.set(str(detail or ""))
                    if progress is not None and self._progress_var is not None:
                        self._progress_var.set(max(0.0, min(100.0, float(progress))))
                elif kind == "log":
                    if self._summary_var is not None:
                        self._summary_var.set(str(payload))
                elif kind == "success":
                    if self._title_var is not None:
                        self._title_var.set("RocketCoach Installer - Complete")
                    if self._phase_var is not None:
                        self._phase_var.set("Complete")
                    if self._detail_var is not None:
                        self._detail_var.set(str(payload))
                    if self._progress_var is not None:
                        self._progress_var.set(100.0)
                    self._result = 0
                    self._closing = True
                elif kind == "warning":
                    if self._detail_var is not None:
                        self._detail_var.set(str(payload))
                elif kind == "error":
                    message, exc = payload  # type: ignore[misc]
                    self._error = exc if isinstance(exc, Exception) else RuntimeError(str(message))
                    self._error_text = str(message)
                    if self._title_var is not None:
                        self._title_var.set("RocketCoach Installer - Error")
                    if self._phase_var is not None:
                        self._phase_var.set("Installation failed")
                    if self._detail_var is not None:
                        self._detail_var.set(str(message))
                    if self._progress_var is not None:
                        self._progress_var.set(min(100.0, float(self._progress_var.get() or 0)))
                    self._closing = True
        except queue.Empty:
            pass

        if self._closing:
            if self._error and messagebox is not None:
                try:
                    messagebox.showerror("RocketCoach Installer", self._error_text or str(self._error))
                except Exception:
                    pass
            try:
                self._root.destroy()
            except Exception:
                pass
            return

        self._root.after(100, self._process_queue)

    def run(self, worker) -> int:
        if not self.enabled or self._root is None:
            return worker()

        def _worker_wrapper() -> None:
            try:
                result = worker()
                self._result = int(result or 0)
            except Exception as exc:
                self._queue.put(("error", (str(exc), exc)))

        threading.Thread(target=_worker_wrapper, daemon=True).start()
        self._root.after(100, self._process_queue)
        self._root.mainloop()
        if self._error is not None:
            raise self._error
        return self._result


def run(
    command: list[str],
    *,
    check: bool = True,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    log("Running: " + " ".join(f'"{part}"' if " " in part else part for part in command))
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    output_chunks: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        output_chunks.append(line)
        if sys.stdout is not None:
            try:
                print(line, end="", flush=True)
            except Exception:
                pass
        if _LOG_FILE_PATH is not None:
            with _LOG_FILE_PATH.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(line)
    return_code = process.wait()
    stdout = "".join(output_chunks)
    completed = subprocess.CompletedProcess(command, return_code, stdout=stdout, stderr=None)
    if check and return_code != 0:
        raise subprocess.CalledProcessError(return_code, command, output=stdout)
    return completed


def bundled_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()
    return Path(__file__).resolve().parents[1]


def _windows_default_install_root() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return (Path(local_appdata) / "RocketCoach").resolve()
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        roaming_root = Path(appdata).resolve().parent
        return (roaming_root / "Local" / "RocketCoach").resolve()
    return (Path.home() / "AppData" / "Local" / "RocketCoach").resolve()


def discover_registered_protocol_install_root(protocol_name: str = DEFAULT_TRAINING_BRIDGE_PROTOCOL) -> Path | None:
    if os.name != "nt" or not protocol_name:
        return None
    command_key = rf"HKCU\Software\Classes\{protocol_name}\shell\open\command"
    try:
        probe = subprocess.run(
            ["reg", "query", command_key, "/ve"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=True,
        )
    except Exception:
        return None

    output = str(probe.stdout or "")
    match = re.search(r'wscript\.exe\s+"([^"]+RocketCoachProtocolLauncher\.vbs)"', output, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return Path(match.group(1)).resolve().parent
    except Exception:
        return None


def default_install_root() -> Path:
    registered_root = discover_registered_protocol_install_root()
    if registered_root is not None:
        return registered_root
    if os.name == "nt":
        return _windows_default_install_root()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "RocketCoach"
    return Path(__file__).resolve().parents[1]


def resolve_install_root(cli_value: str | None) -> Path:
    if cli_value:
        return Path(cli_value).resolve()
    return default_install_root().resolve()


def copytree_contents(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Bundled resource folder is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        # ignore_errors so files held briefly by an exiting bridge process don't
        # abort the whole install — they get retried below.
        shutil.rmtree(destination, ignore_errors=True)
        if destination.exists():
            # Second pass after a short pause so any straggler file handles
            # (e.g. Python .pyd / __pycache__ from a process we just killed) clear.
            import time as _time
            _time.sleep(1.0)
            shutil.rmtree(destination, ignore_errors=False)
    shutil.copytree(source, destination)


def stop_running_bridge_processes(install_root: Path | None = None) -> None:
    """Kill any python.exe running rocketcoach.training.launcher_server, plus
    anything still holding the bridge port. Called before file operations so a
    fresh installer cleanly overwrites the previous one without users having to
    touch the filesystem or Task Manager.
    """
    if os.name != "nt":
        return
    try:
        # Match by command line so we don't kill unrelated python processes.
        ps_script = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            "  ($_.Name -eq 'python.exe' -or $_.Name -eq 'pythonw.exe') -and "
            "  $_.CommandLine -like '*rocketcoach.training.launcher_server*' "
            "} | "
            "ForEach-Object { "
            "  Write-Output ('killing pid=' + $_.ProcessId + ' cmd=' + $_.CommandLine); "
            "  Stop-Process -Id $_.ProcessId -Force "
            "}"
        )
        result = run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            check=False,
        )
        if result.stdout:
            for line in str(result.stdout).splitlines():
                if line.strip():
                    log(f"Stopped previous bridge: {line.strip()}")
    except Exception as exc:
        log(f"Warning: could not enumerate running bridge processes: {exc}")

    # Also free the bridge port (8766) in case a crashed process left it bound.
    try:
        ps_port = (
            "$ErrorActionPreference = 'SilentlyContinue'; "
            "Get-NetTCPConnection -LocalPort 8766 -State Listen | "
            "ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }"
        )
        run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_port],
            check=False,
        )
    except Exception:
        pass

    # Give Windows a moment to release file handles before overwrites.
    import time as _time
    _time.sleep(0.5)


def download_file(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading {url} -> {destination}")
    with urllib.request.urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def install_rlbot_gui(msi_path: Path, interactive: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("RLBot GUI MSI install is only supported on Windows.")

    ui_flag = "/passive" if interactive else "/qn"
    run(["msiexec", "/i", str(msi_path), ui_flag, "/norestart"])


def resolve_venv_python(venv_root: Path) -> Path:
    candidates = [
        venv_root / "Scripts" / "python.exe",
        venv_root / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find Python inside virtual environment: {venv_root}")


def _check_python_candidate(command: list[str]) -> Path | None:
    try:
        probe = subprocess.run(
            command + ["-c", "import json, sys; print(json.dumps({'exe': sys.executable, 'version': list(sys.version_info[:3])}))"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        payload = json.loads(str(probe.stdout or "").strip() or "{}")
        version = tuple(int(x) for x in payload.get("version", [])[:3])
        exe = Path(str(payload.get("exe", "") or "")).resolve()
        if exe.exists() and version[:2] in {(3, 11), (3, 12)}:
            return exe
    except Exception:
        return None
    return None


def resolve_host_python(requested_python: str | None) -> Path | None:
    candidates: list[list[str]] = []
    if requested_python:
        candidates.append([requested_python])
    candidates.extend(
        [
            ["py", "-3.11"],
            ["py", "-3"],
            ["python"],
            ["python3"],
        ]
    )
    seen: set[str] = set()
    for candidate in candidates:
        key = " ".join(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        resolved = _check_python_candidate(candidate)
        if resolved:
            return resolved
    return None


def install_python_windows(installer_path: Path) -> None:
    if os.name != "nt":
        raise RuntimeError("Automatic Python installation is only supported on Windows.")
    attempts = [
        (
            "machine-wide",
            [
                str(installer_path),
                "/quiet",
                "InstallAllUsers=1",
                "PrependPath=1",
                "Include_test=0",
                "SimpleInstall=1",
            ],
        ),
        (
            "per-user",
            [
                str(installer_path),
                "/quiet",
                "InstallAllUsers=0",
                "PrependPath=1",
                "Include_test=0",
                "SimpleInstall=1",
            ],
        ),
    ]
    last_exc: Exception | None = None
    for mode_name, command in attempts:
        try:
            log(f"Attempting {mode_name} Python install.")
            run(command)
            return
        except Exception as exc:
            last_exc = exc
            log(f"Warning: {mode_name} Python install failed: {exc}")
    raise RuntimeError("Automatic Python installation failed for both machine-wide and per-user modes.") from last_exc


def ensure_host_python(install_root: Path, requested_python: str | None, installer_url: str) -> Path:
    existing = resolve_host_python(requested_python)
    if existing:
        log(f"Using host Python interpreter at {existing}")
        return existing

    downloads_dir = install_root / "artifacts" / "installer_downloads"
    installer_path = download_file(installer_url, downloads_dir / "python-3.11.9-amd64.exe")
    log("No suitable Python 3.11 or 3.12 interpreter was found. Installing Python automatically.")
    install_python_windows(installer_path)

    installed = resolve_host_python(requested_python)
    if installed:
        log(f"Using installed host Python interpreter at {installed}")
        return installed
    raise RuntimeError("Python installed, but no usable Python 3.11 or 3.12 interpreter was found afterwards.")


def ensure_project_venv(install_root: Path, host_python: Path) -> Path:
    venv_root = install_root / "venv"
    recreate = False
    if venv_root.exists():
        try:
            venv_python = resolve_venv_python(venv_root)
            probe = run([str(venv_python), "-m", "pip", "--version"], check=False)
            if probe.returncode != 0:
                log(f"Removing virtual environment with broken pip at {venv_root}")
                shutil.rmtree(venv_root, ignore_errors=True)
                recreate = True
        except FileNotFoundError:
            log(f"Removing incomplete virtual environment at {venv_root}")
            shutil.rmtree(venv_root, ignore_errors=True)
            recreate = True
    else:
        recreate = True

    if recreate:
        log(f"Creating project virtual environment at {venv_root}")
        run([str(host_python), "-m", "venv", str(venv_root)])

    venv_python = resolve_venv_python(venv_root)
    return venv_python


def rebuild_project_venv(install_root: Path, host_python: Path) -> Path:
    venv_root = install_root / "venv"
    if venv_root.exists():
        log(f"Rebuilding project virtual environment at {venv_root}")
        shutil.rmtree(venv_root, ignore_errors=True)
    log(f"Creating project virtual environment at {venv_root}")
    run([str(host_python), "-m", "venv", str(venv_root)])
    return resolve_venv_python(venv_root)


def install_bundled_project_files(resource_root: Path, install_root: Path) -> None:
    for folder_name in ("rocketcoach", "configs"):
        source = resource_root / folder_name
        destination = install_root / folder_name
        copytree_contents(source, destination)
        log(f"Installed bundled {folder_name} into {destination}")


def install_rldojo_playlists() -> None:
    try:
        from generate_rldojo_mechanic_playlists import write_playlists

        written = write_playlists()
        log(f"Installed/updated {len(written)} RocketCoach RLDojo playlists.")
    except Exception as exc:
        log(f"Warning: could not install RocketCoach RLDojo playlists: {exc}")


def install_python_requirements(resource_root: Path, python_exe: Path, extra_packages: list[str]) -> None:
    requirements_file = resource_root / "requirements" / "base.txt"
    if not requirements_file.exists():
        requirements_file = resource_root / "requirements.txt"

    pip_check = run([str(python_exe), "-m", "pip", "--version"], check=False)
    if pip_check.returncode != 0:
        log("pip is missing or unhealthy in the project venv. Repairing with ensurepip...")
        run([str(python_exe), "-m", "ensurepip", "--upgrade"])
        run([str(python_exe), "-m", "pip", "--version"])

    pip_upgrade = run(
        [str(python_exe), "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip", "setuptools", "wheel"],
        check=False,
    )
    if pip_upgrade.returncode != 0:
        log("Warning: pip upgrade failed. Continuing with the existing pip because requirements installation can still succeed.")
        run([str(python_exe), "-m", "pip", "--version"])

    run([str(python_exe), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(requirements_file)])

    if extra_packages:
        run([str(python_exe), "-m", "pip", "install", "--disable-pip-version-check", *extra_packages])


def write_training_bridge_launcher(install_root: Path) -> tuple[Path, Path]:
    launcher_script = install_root / "RocketCoachTrainingBridgeLauncher.ps1"
    launcher_vbs = install_root / "RocketCoachProtocolLauncher.vbs"
    escaped_launcher_script = str(launcher_script).replace('"', '""')
    launcher_script.write_text(
        textwrap.dedent(
            f"""\
            param(
                [string]$ProtocolUrl = ""
            )

            $ErrorActionPreference = "Stop"
            $installRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
            $logDir = Join-Path $installRoot "logs"
            $stdoutLog = Join-Path $logDir "training_bridge_stdout.log"
            $stderrLog = Join-Path $logDir "training_bridge_stderr.log"
            $callbackLog = Join-Path $logDir "training_bridge_callback.log"
            $pythonExe = Join-Path $installRoot "venv\\Scripts\\python.exe"

            function Write-CallbackLog([string]$Message) {{
                New-Item -ItemType Directory -Force -Path $logDir | Out-Null
                $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
                Add-Content -Path $callbackLog -Value "[$timestamp] $Message"
            }}

            function Test-BridgeHealth {{
                try {{
                    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8766/api/health" -UseBasicParsing -TimeoutSec 2
                    return ($response.StatusCode -eq 200)
                }}
                catch {{
                    return $false
                }}
            }}

            function Stop-DuplicateBridgeProcesses {{
                $escapedPythonExe = [Regex]::Escape($pythonExe)
                $bridgeProcesses = @(Get-CimInstance Win32_Process | Where-Object {{
                    $_.Name -eq 'python.exe' -and
                    $_.CommandLine -like '*rocketcoach.training.launcher_server*' -and
                    $_.CommandLine -like '*--port 8766*'
                }})
                if (-not $bridgeProcesses -or $bridgeProcesses.Count -le 0) {{
                    return
                }}
                foreach ($proc in $bridgeProcesses) {{
                    if ($proc.CommandLine -notmatch $escapedPythonExe) {{
                        try {{
                            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                            Write-CallbackLog ("Stopped stale bridge process from older install pid=" + $proc.ProcessId)
                        }}
                        catch {{
                            Write-CallbackLog ("Could not stop stale bridge process pid=" + $proc.ProcessId + ": " + $_.Exception.Message)
                        }}
                    }}
                }}
                $bridgeProcesses = @(Get-CimInstance Win32_Process | Where-Object {{
                    $_.Name -eq 'python.exe' -and
                    $_.CommandLine -like '*rocketcoach.training.launcher_server*' -and
                    $_.CommandLine -like '*--port 8766*'
                }})
                if (-not $bridgeProcesses -or $bridgeProcesses.Count -le 1) {{
                    return
                }}
                $preferred = $bridgeProcesses |
                    Where-Object {{ $_.CommandLine -match $escapedPythonExe }} |
                    Sort-Object CreationDate -Descending |
                    Select-Object -First 1
                if (-not $preferred) {{
                    $preferred = $bridgeProcesses | Sort-Object CreationDate -Descending | Select-Object -First 1
                }}
                foreach ($proc in $bridgeProcesses) {{
                    if ($preferred -and $proc.ProcessId -eq $preferred.ProcessId) {{
                        continue
                    }}
                    try {{
                        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                        Write-CallbackLog ("Stopped duplicate bridge process pid=" + $proc.ProcessId)
                    }}
                    catch {{
                        Write-CallbackLog ("Could not stop duplicate bridge process pid=" + $proc.ProcessId + ": " + $_.Exception.Message)
                    }}
                }}
            }}

            function Get-ProtocolParams([string]$Url) {{
                $result = @{{
                    Action = ""
                    Callback = ""
                    Payload = ""
                }}
                if ([string]::IsNullOrWhiteSpace($Url)) {{
                    return $result
                }}
                Add-Type -AssemblyName System.Web
                $uri = [System.Uri]$Url
                $query = [System.Web.HttpUtility]::ParseQueryString($uri.Query)
                $action = $query.Get("action")
                if ([string]::IsNullOrWhiteSpace($action)) {{
                    $action = $uri.Host
                }}
                $callback = $query.Get("callback")
                if ($null -eq $callback) {{ $callback = "" }}
                $payload = $query.Get("payload")
                if ($null -eq $payload) {{ $payload = "" }}
                $result.Action = [string]$action
                $result.Callback = [string]$callback
                $result.Payload = [string]$payload
                return $result
            }}

            function Send-Callback([string]$CallbackUrl, [hashtable]$Body) {{
                if ([string]::IsNullOrWhiteSpace($CallbackUrl)) {{
                    Write-CallbackLog "Skipping callback because callback URL was empty."
                    return
                }}
                $json = $Body | ConvertTo-Json -Depth 8 -Compress
                $lastError = ""
                for ($attempt = 0; $attempt -lt 6; $attempt++) {{
                    try {{
                        Invoke-RestMethod -Method Post -Uri $CallbackUrl -ContentType "application/json" -Body $json -TimeoutSec 15 | Out-Null
                        Write-CallbackLog ("Callback succeeded on attempt " + ($attempt + 1) + " to " + $CallbackUrl)
                        return
                    }}
                    catch {{
                        $lastError = $_.Exception.Message
                        Write-CallbackLog ("Callback attempt " + ($attempt + 1) + " failed: " + $lastError)
                        Start-Sleep -Seconds ([Math]::Min(8, ($attempt + 1) * 2))
                    }}
                }}
                throw "RocketCoach callback failed after multiple attempts. Last error: $lastError"
            }}

            function Get-LogTail([string]$Path, [int]$LineCount = 120) {{
                try {{
                    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path $Path)) {{
                        return ""
                    }}
                    return ((Get-Content -Path $Path -Tail $LineCount -ErrorAction Stop) -join "`n")
                }}
                catch {{
                    return ""
                }}
            }}

            function Get-BridgeLogPayload() {{
                return @{{
                    callback_log = Get-LogTail $callbackLog
                    stdout_log = Get-LogTail $stdoutLog
                    stderr_log = Get-LogTail $stderrLog
                }}
            }}

            function Get-ReplayFolderPath([string]$Platform) {{
                $documentsRoots = @()
                if (-not [string]::IsNullOrWhiteSpace($env:OneDriveConsumer)) {{
                    $documentsRoots += (Join-Path $env:OneDriveConsumer "Documents")
                }}
                if (-not [string]::IsNullOrWhiteSpace($env:OneDrive)) {{
                    $documentsRoots += (Join-Path $env:OneDrive "Documents")
                }}
                $documentsRoots += [Environment]::GetFolderPath("MyDocuments")

                $platformValue = ""
                if ($null -ne $Platform) {{
                    $platformValue = [string]$Platform
                }}
                $normalizedPlatform = $platformValue.Trim().ToLowerInvariant()
                foreach ($documentsRoot in ($documentsRoots | Where-Object {{ -not [string]::IsNullOrWhiteSpace($_) }} | Select-Object -Unique)) {{
                    $basePath = Join-Path $documentsRoot "My Games\\Rocket League\\TAGame"
                    $epicPath = Join-Path $basePath "DemosEpic"
                    $standardPath = Join-Path $basePath "Demos"
                    if (($normalizedPlatform -eq "epic" -or $normalizedPlatform -eq "epic games") -and (Test-Path $epicPath)) {{
                        return $epicPath
                    }}
                    if (Test-Path $standardPath) {{
                        return $standardPath
                    }}
                    if (Test-Path $epicPath) {{
                        return $epicPath
                    }}
                }}
                throw "Rocket League replay folder was not found in Documents or OneDrive Documents."
            }}

            function Handle-ProtocolAction([string]$Url) {{
                $protocol = Get-ProtocolParams $Url
                if ($protocol.Action -eq "open-replay-folder") {{
                    try {{
                        Write-CallbackLog "Handling open-replay-folder protocol action."
                        $platform = ""
                        if (-not [string]::IsNullOrWhiteSpace($protocol.Payload)) {{
                            $decoded = [System.Uri]::UnescapeDataString($protocol.Payload)
                            $payload = ConvertFrom-Json $decoded
                            if ($null -ne $payload.platform) {{
                                $platform = [string]$payload.platform
                            }}
                        }}
                        $folderPath = Get-ReplayFolderPath $platform
                        Start-Process explorer.exe -ArgumentList $folderPath | Out-Null
                        Write-CallbackLog ("Opened replay folder: " + $folderPath)
                    }}
                    catch {{
                        Write-CallbackLog ("Failed to open replay folder: " + $_.Exception.Message)
                        throw
                    }}
                    return
                }}
                if ($protocol.Action -eq "verify-deps" -or $protocol.Action -eq "verify") {{
                    try {{
                        Write-CallbackLog "Handling verify-deps protocol action."
                        $preflight = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8766/api/training/preflight" -TimeoutSec 20
                        Send-Callback $protocol.Callback @{{
                            ok = $true
                            payload = @{{
                                preflight = $preflight.data
                            }}
                        }}
                    }}
                    catch {{
                        Send-Callback $protocol.Callback @{{
                            ok = $false
                            error = $_.Exception.Message
                            payload = @{{
                                logs = Get-BridgeLogPayload
                            }}
                        }}
                    }}
                    return
                }}
                if ($protocol.Action -eq "train") {{
                    try {{
                        Write-CallbackLog "Handling train protocol action."
                        $launchBody = @{{}}
                        if (-not [string]::IsNullOrWhiteSpace($protocol.Payload)) {{
                            $decoded = [System.Uri]::UnescapeDataString($protocol.Payload)
                            $launchBody = ConvertFrom-Json $decoded
                        }}
                        $launchResp = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8766/api/training/launch" -ContentType "application/json" -Body (($launchBody | ConvertTo-Json -Depth 8 -Compress)) -TimeoutSec 120
                        Send-Callback $protocol.Callback @{{
                            ok = $true
                            payload = @{{
                                launch = $launchResp.data
                            }}
                        }}
                    }}
                    catch {{
                        Send-Callback $protocol.Callback @{{
                            ok = $false
                            error = $_.Exception.Message
                            payload = @{{
                                logs = Get-BridgeLogPayload
                            }}
                        }}
                    }}
                }}
            }}

            $mutex = New-Object System.Threading.Mutex($false, "Local\\RocketCoachTrainingBridgeBootstrap")
            $hasMutex = $false
            $protocol = Get-ProtocolParams $ProtocolUrl
            try {{
                $hasMutex = $mutex.WaitOne(15000)
                if (-not $hasMutex) {{
                    throw "RocketCoach training bridge bootstrap was busy. Please try again."
                }}

                if (-not (Test-Path $pythonExe)) {{
                    throw "RocketCoach training runtime was not found at $pythonExe"
                }}

                Stop-DuplicateBridgeProcesses

                if (Test-BridgeHealth) {{
                    Write-CallbackLog "Bridge already healthy; handling protocol action immediately."
                    Handle-ProtocolAction $ProtocolUrl
                    exit 0
                }}

                New-Item -ItemType Directory -Force -Path $logDir | Out-Null
                $argumentList = @(
                    '-m',
                    'rocketcoach.training.launcher_server',
                    '--host',
                    '127.0.0.1',
                    '--port',
                    '8766',
                    '--launcher',
                    'auto'
                )

                Start-Process -FilePath $pythonExe -ArgumentList $argumentList -WorkingDirectory $installRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog | Out-Null
                Write-CallbackLog "Started background training bridge process."

                for ($i = 0; $i -lt 120; $i++) {{
                    Start-Sleep -Milliseconds 750
                    if (Test-BridgeHealth) {{
                        Write-CallbackLog ("Bridge became healthy after " + ($i + 1) + " polls.")
                        Handle-ProtocolAction $ProtocolUrl
                        exit 0
                    }}
                }}

                Write-CallbackLog "Training bridge did not become healthy after launch."
                throw "RocketCoach training bridge did not become healthy after launch."
            }}
            catch {{
                Write-CallbackLog ("Training bridge bootstrap failed: " + $_.Exception.Message)
                try {{
                    Send-Callback $protocol.Callback @{{
                        ok = $false
                        error = $_.Exception.Message
                        payload = @{{
                            logs = Get-BridgeLogPayload
                        }}
                    }}
                }}
                catch {{
                    Write-CallbackLog ("Failed to send bootstrap error callback: " + $_.Exception.Message)
                }}
                throw
            }}
            finally {{
                if ($hasMutex) {{
                    $mutex.ReleaseMutex() | Out-Null
                }}
                $mutex.Dispose()
            }}
            """
        ),
        encoding="utf-8",
    )
    launcher_vbs_content = "\n".join(
        [
            "Dim shell, args, command, i",
            'Set shell = CreateObject("WScript.Shell")',
            f'command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""{escaped_launcher_script}"""',
            "Set args = WScript.Arguments",
            "For i = 0 To args.Count - 1",
            '    command = command & " " & Chr(34) & Replace(args.Item(i), Chr(34), """""") & Chr(34)',
            "Next",
            "shell.Run command, 0, False",
            "",
        ]
    )
    launcher_vbs.write_text(launcher_vbs_content, encoding="utf-8")
    return launcher_script, launcher_vbs


def register_training_bridge_protocol(protocol_name: str, launcher_vbs: Path) -> None:
    if os.name != "nt":
        return
    if not protocol_name:
        return
    key = rf"HKCU\Software\Classes\{protocol_name}"
    command_key = rf"{key}\shell\open\command"
    run(["reg", "add", key, "/ve", "/d", "URL:RocketCoach Protocol", "/f"])
    run(["reg", "add", key, "/v", "URL Protocol", "/d", "", "/f"])
    command_value = f'wscript.exe "{launcher_vbs}" "%1"'
    run(["reg", "add", command_key, "/ve", "/d", command_value, "/f"])
    log(f"Registered {protocol_name}:// protocol handler")


def default_botpack_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "RLBot" / "RLBotPack"
    return Path.home() / "AppData" / "Roaming" / "RLBot" / "RLBotPack"


def download_and_extract_botpack(destination: Path, zip_url: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="rlbotpack_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        archive_path = temp_dir / "RLBotPack.zip"
        download_file(zip_url, archive_path)

        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp_dir)

        extracted_roots = [path for path in temp_dir.iterdir() if path.is_dir()]
        pack_root = None
        for root in extracted_roots:
            candidate = root / "RLBotPack"
            if candidate.exists():
                pack_root = candidate
                break
            if (root / "README.md").exists():
                pack_root = root
        if pack_root is None:
            raise RuntimeError("Unable to locate extracted RLBotPack contents.")

        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(pack_root, destination)

    return destination


def _find_first_matching_path(root: Path, candidates: list[str]) -> Path | None:
    lowered = [item.lower() for item in candidates]
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        normalized = str(path.relative_to(root)).replace("/", "\\").lower()
        if normalized in lowered:
            return path.resolve()
    return None


def _resolve_cfg_requirement_file(cfg_file: Path) -> Path | None:
    parser = configparser.RawConfigParser()
    try:
        parser.read(cfg_file, encoding="utf-8")
    except Exception:
        return None

    if parser.has_option("Locations", "requirements_file"):
        rel_path = str(parser.get("Locations", "requirements_file") or "").strip()
        if not rel_path:
            return None
        candidate = Path(rel_path)
        if not candidate.is_absolute():
            candidate = (cfg_file.parent / candidate).resolve()
        if candidate.exists():
            return candidate.resolve()
    return None


def collect_target_botpack_requirement_files(botpack_root: Path) -> list[Path]:
    requirement_files: set[Path] = set()

    for rel_hint in TARGET_BOTPACK_REQUIREMENT_HINTS:
        candidate = _find_first_matching_path(botpack_root, [rel_hint])
        if candidate is not None and candidate.exists():
            requirement_files.add(candidate)

    for config_hints in TARGET_BOT_CFG_HINTS.values():
        cfg_path = _find_first_matching_path(botpack_root, config_hints)
        if cfg_path is None:
            continue
        requirement_file = _resolve_cfg_requirement_file(cfg_path)
        if requirement_file is not None and requirement_file.exists():
            requirement_files.add(requirement_file.resolve())

    return sorted(requirement_files)


def install_botpack_requirements(
    python_exe: Path,
    botpack_root: Path,
    *,
    continue_on_error: bool,
) -> list[str]:
    failures: list[str] = []
    for requirement_file in collect_target_botpack_requirement_files(botpack_root):
        try:
            log(f"Installing bot requirements from {requirement_file}")
            run([str(python_exe), "-m", "pip", "install", "-r", str(requirement_file)])
        except subprocess.CalledProcessError as exc:
            message = f"{requirement_file}: exit code {exc.returncode}"
            failures.append(message)
            if not continue_on_error:
                raise
            log(f"Warning: {message}")
    return failures


def run_install_preflight(python_exe: Path, install_root: Path, botpack_root: Path) -> dict[str, object] | None:
    probe_script = textwrap.dedent(
        """
        import json
        import sys
        from pathlib import Path

        install_root = Path(sys.argv[1]).resolve()
        sys.path.insert(0, str(install_root))
        from rocketcoach.training.rldojo_catalog import build_preflight  # noqa: E402

        payload = dict(build_preflight(live_host="127.0.0.1", live_port=8766, service_label="local training launcher") or {})
        blocked_bots = [status for status in list(payload.get("bot_statuses", []) or []) if not bool(status.get("ready"))]
        summary = {
            "shared_dependency_ready": bool(payload.get("shared_dependency_ready")),
            "rocket_league_detected": bool(payload.get("rocket_league_detected")),
            "dojo_source_detected": bool(payload.get("dojo_source_detected")),
            "missing_playlists": list(payload.get("missing_playlists", []) or []),
            "runtime_missing_modules": list(payload.get("runtime_missing_modules", []) or []),
            "blocked_bots": [
                {
                    "bot_profile_id": str(status.get("bot_profile_id", "") or ""),
                    "bot_name": str(status.get("bot_name", "") or ""),
                    "missing_modules": list(status.get("missing_modules", []) or []),
                    "messages": list(status.get("messages", []) or []),
                }
                for status in blocked_bots
            ],
            "messages": list(payload.get("messages", []) or []),
        }
        print(json.dumps(summary))
        """
    )
    env = os.environ.copy()
    env["RLBOTPACK_ROOT"] = str(botpack_root)
    try:
        completed = run(
            [str(python_exe), "-c", probe_script, str(install_root)],
            cwd=install_root,
            env=env,
        )
        output = str(completed.stdout or "").strip().splitlines()
        if not output:
            return None
        return json.loads(output[-1])
    except Exception as exc:
        log(f"Warning: post-install training preflight probe failed: {exc}")
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install RLBot GUI, RLBotPack, and Python requirements for RocketCoach workflows."
    )
    parser.add_argument("--repo-root", default="", help="Install root for the RocketCoach environment.")
    parser.add_argument("--python", default="", help="Reserved for future custom-Python support.")
    parser.add_argument("--rlbot-gui-url", default=DEFAULT_RLBOT_GUI_URL)
    parser.add_argument("--rlbotpack-zip-url", default=DEFAULT_RLBOTPACK_ZIP_URL)
    parser.add_argument("--python-installer-url", default=DEFAULT_PYTHON_INSTALLER_URL)
    parser.add_argument("--botpack-dir", default="", help="Install directory for RLBotPack.")
    parser.add_argument("--skip-rlbot-gui", action="store_true", help="Skip RLBot GUI installation.")
    parser.add_argument("--skip-botpack", action="store_true", help="Skip RLBotPack download and dependency install.")
    parser.add_argument("--skip-project-python", action="store_true", help="Skip repo virtual environment setup and pip installs.")
    parser.add_argument("--interactive-msi", action="store_true", help="Use a visible MSI progress UI instead of a silent install.")
    parser.add_argument(
        "--extra-package",
        action="append",
        default=[],
        help="Additional pip package to install into the project venv. Can be provided multiple times.",
    )
    parser.add_argument(
        "--strict-botpack-requirements",
        action="store_true",
        help="Stop on the first bot requirement install failure instead of continuing.",
    )
    parser.add_argument(
        "--skip-protocol-registration",
        action="store_true",
        help="Skip Windows custom protocol registration for rocketcoach:// helper launches.",
    )
    parser.add_argument(
        "--skip-stop-bridge",
        action="store_true",
        help="Do not kill any running training bridge before installing. By default the installer stops the previous bridge so a re-install cleanly overwrites it.",
    )
    parser.add_argument(
        "--protocol-name",
        default=DEFAULT_TRAINING_BRIDGE_PROTOCOL,
        help="Custom protocol name to register for starting the local RocketCoach helper.",
    )
    return parser.parse_args()


def run_installation(args: argparse.Namespace, ui: InstallerProgressWindow | None = None) -> int:
    resource_root = bundled_resource_root()
    install_root = resolve_install_root(args.repo_root or None)
    install_root.mkdir(parents=True, exist_ok=True)
    log_path = setup_logging(install_root)
    log(f"Writing installer log to {log_path}")
    log(f"Using bundled resources from {resource_root}")
    log(f"Installing RocketCoach runtime into {install_root}")

    if not getattr(args, "skip_stop_bridge", False):
        if ui:
            ui.phase("Cleanup", "Stopping any running RocketCoach training bridge so files can be overwritten...", 4)
        stop_running_bridge_processes(install_root)

    if ui:
        ui.phase("Bundled Files", "Copying the bundled RocketCoach runtime into the install root...", 8)
    install_bundled_project_files(resource_root, install_root)
    install_rldojo_playlists()

    extra_packages = list(DEFAULT_EXTRA_PACKAGES)
    extra_packages.extend(args.extra_package)

    # pathlib is part of the Python standard library on supported runtimes.
    log("Skipping separate pathlib install because it is built into Python 3.")

    venv_python: Path | None = None
    if not args.skip_project_python:
        if ui:
            ui.phase("Python Setup", "Finding or installing Python 3.11+, then creating the project virtual environment...", 22)
        host_python = ensure_host_python(
            install_root,
            args.python or None,
            str(args.python_installer_url or DEFAULT_PYTHON_INSTALLER_URL),
        )
        if ui:
            ui.phase("Python Setup", "Creating the project virtual environment and installing Python packages...", 38)
        venv_python = ensure_project_venv(install_root, host_python)
        try:
            install_python_requirements(resource_root, venv_python, extra_packages)
        except subprocess.CalledProcessError as exc:
            log(f"Project Python setup failed with exit code {exc.returncode}. Rebuilding the virtual environment and retrying once...")
            venv_python = rebuild_project_venv(install_root, host_python)
            install_python_requirements(resource_root, venv_python, extra_packages)

    failures: list[str] = []
    botpack_root: Path | None = None

    if not args.skip_rlbot_gui:
        if ui:
            ui.phase("RLBot GUI", "Downloading and installing RLBot GUI...", 58)
        downloads_dir = install_root / "artifacts" / "installer_downloads"
        msi_path = download_file(args.rlbot_gui_url, downloads_dir / "RLBotGUI.msi")
        try:
            install_rlbot_gui(msi_path, interactive=args.interactive_msi)
        except subprocess.CalledProcessError as exc:
            message = (
                "RLBot GUI MSI install failed. The RocketCoach companion was still installed, "
                "but RLBot GUI may need to be installed manually on this machine. "
                f"(exit code {exc.returncode})"
            )
            failures.append(message)
            log(f"Warning: {message}")

    if not args.skip_botpack:
        if ui:
            ui.phase("RLBotPack", "Downloading RLBotPack and installing bot-specific requirements...", 74)
        botpack_dir = Path(args.botpack_dir).resolve() if args.botpack_dir else default_botpack_dir()
        botpack_root = download_and_extract_botpack(botpack_dir, args.rlbotpack_zip_url)
        log(f"Installed RLBotPack to {botpack_root}")

        if venv_python is not None:
            failures = install_botpack_requirements(
                venv_python,
                botpack_root,
                continue_on_error=not args.strict_botpack_requirements,
            )
        else:
            log("Skipping bot pack pip requirements because project Python setup was skipped.")

    if ui:
        ui.phase("Protocol", "Generating the RocketCoach bridge launcher and registering the protocol handler...", 88)
    _, launcher_vbs = write_training_bridge_launcher(install_root)
    if not args.skip_protocol_registration:
        register_training_bridge_protocol(str(args.protocol_name or DEFAULT_TRAINING_BRIDGE_PROTOCOL), launcher_vbs)

    if venv_python is not None and botpack_root is not None:
        if ui:
            ui.phase("Preflight", "Checking the installed training setup and replay dependencies...", 95)
        preflight_summary = run_install_preflight(venv_python, install_root, botpack_root)
        if preflight_summary is not None:
            if preflight_summary.get("shared_dependency_ready"):
                log("Post-install training preflight: shared dependencies look ready on this machine.")
            else:
                messages = list(preflight_summary.get("messages", []) or [])
                blocked_bots = list(preflight_summary.get("blocked_bots", []) or [])
                if messages:
                    failures.extend(f"Post-install preflight: {message}" for message in messages)
                if blocked_bots:
                    for bot_status in blocked_bots:
                        bot_name = str(bot_status.get("bot_name", "") or bot_status.get("bot_profile_id", "bot"))
                        missing = ", ".join(list(bot_status.get("missing_modules", []) or [])[:5])
                        detail = f"{bot_name} is not launch-ready"
                        if missing:
                            detail += f" (missing {missing})"
                        failures.append(f"Post-install preflight: {detail}.")

    log("Install flow complete.")
    if failures:
        log("Some install steps completed with warnings:")
        for failure in failures:
            log(f"  - {failure}")
        if ui:
            ui.finish_warning("Install completed with warnings. See the log for details.")
            ui.finish_success("Install completed with warnings. You can now press Train Against Bot.")
        return 0

    if ui:
        ui.finish_success("Install complete. You can now press Train Against Bot.")
    return 0


def main() -> int:
    args = parse_args()
    ui = InstallerProgressWindow(enabled=os.name == "nt")
    if ui.enabled:
        return ui.run(lambda: run_installation(args, ui))
    return run_installation(args, None)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"Fatal error: {exc}")
        if messagebox is not None and os.name == "nt":
            try:
                messagebox.showerror("RocketCoach Installer", str(exc))
            except Exception:
                pass
        raise
