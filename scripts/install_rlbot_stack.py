#!/usr/bin/env python3
"""
Windows-first bootstrap installer for RLBot GUI, RLBotPack, and Python deps.

This script is designed to be packaged as a standalone .exe with PyInstaller.
"""

from __future__ import annotations

import argparse
import configparser
import os
import json
import textwrap
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


DEFAULT_RLBOT_GUI_URL = "https://github.com/RLBot/RLBotGUI/releases/download/v1.0/RLBotGUI.msi"
DEFAULT_RLBOTPACK_ZIP_URL = "https://codeload.github.com/RLBot/RLBotPack/zip/refs/heads/master"
DEFAULT_PYTHON_INSTALLER_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
DEFAULT_EXTRA_PACKAGES = [
    "stable-baselines3==1.7.0",
    "pygame",
]
DEFAULT_TRAINING_BRIDGE_PROTOCOL = "rocketcoach"


def log(message: str) -> None:
    print(f"[installer] {message}", flush=True)


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    log("Running: " + " ".join(f'"{part}"' if " " in part else part for part in command))
    return subprocess.run(command, check=check, text=True)


def bundled_resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent)).resolve()
    return Path(__file__).resolve().parents[1]


def default_install_root() -> Path:
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
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


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
        if exe.exists() and version >= (3, 11):
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
    run(
        [
            str(installer_path),
            "/quiet",
            "InstallAllUsers=1",
            "PrependPath=1",
            "Include_test=0",
            "SimpleInstall=1",
        ]
    )


def ensure_host_python(install_root: Path, requested_python: str | None, installer_url: str) -> Path:
    existing = resolve_host_python(requested_python)
    if existing:
        log(f"Using host Python interpreter at {existing}")
        return existing

    downloads_dir = install_root / "artifacts" / "installer_downloads"
    installer_path = download_file(installer_url, downloads_dir / "python-3.11.9-amd64.exe")
    log("No suitable Python 3.11+ interpreter was found. Installing Python automatically.")
    install_python_windows(installer_path)

    installed = resolve_host_python(requested_python)
    if installed:
        log(f"Using installed host Python interpreter at {installed}")
        return installed
    raise RuntimeError("Python installed, but no usable Python 3.11+ interpreter was found afterwards.")


def ensure_project_venv(install_root: Path, host_python: Path) -> Path:
    venv_root = install_root / "venv"
    recreate = False
    if venv_root.exists():
        try:
            resolve_venv_python(venv_root)
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


def install_bundled_project_files(resource_root: Path, install_root: Path) -> None:
    for folder_name in ("rocketcoach", "configs"):
        source = resource_root / folder_name
        destination = install_root / folder_name
        copytree_contents(source, destination)
        log(f"Installed bundled {folder_name} into {destination}")


def install_python_requirements(resource_root: Path, python_exe: Path, extra_packages: list[str]) -> None:
    requirements_file = resource_root / "requirements" / "base.txt"
    if not requirements_file.exists():
        requirements_file = resource_root / "requirements.txt"

    run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python_exe), "-m", "pip", "install", "-r", str(requirements_file)])
    run([str(python_exe), "-m", "pip", "install", "flatbuffers>=24.3.25"])

    if extra_packages:
        run([str(python_exe), "-m", "pip", "install", *extra_packages])


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
            $pythonExe = Join-Path $installRoot "venv\\Scripts\\python.exe"
            if (-not (Test-Path $pythonExe)) {{
                throw "RocketCoach training runtime was not found at $pythonExe"
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

            if (Test-BridgeHealth) {{
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

            for ($i = 0; $i -lt 20; $i++) {{
                Start-Sleep -Milliseconds 750
                if (Test-BridgeHealth) {{
                    exit 0
                }}
            }}

            throw "RocketCoach training bridge did not become healthy after launch."
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


def collect_requirement_files(botpack_root: Path) -> list[Path]:
    requirement_files: set[Path] = set()

    for requirements_file in botpack_root.rglob("requirements*.txt"):
        if requirements_file.is_file():
            requirement_files.add(requirements_file.resolve())

    for cfg_file in botpack_root.rglob("*.cfg"):
        parser = configparser.RawConfigParser()
        try:
            parser.read(cfg_file, encoding="utf-8")
        except Exception:
            continue

        for section in parser.sections():
            if parser.has_option(section, "requirements_file"):
                rel_path = parser.get(section, "requirements_file").strip()
                if not rel_path:
                    continue
                resolved = (cfg_file.parent / rel_path).resolve()
                if resolved.exists():
                    requirement_files.add(resolved)

    return sorted(requirement_files)


def install_botpack_requirements(
    python_exe: Path,
    botpack_root: Path,
    *,
    continue_on_error: bool,
) -> list[str]:
    failures: list[str] = []
    for requirement_file in collect_requirement_files(botpack_root):
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
        "--protocol-name",
        default=DEFAULT_TRAINING_BRIDGE_PROTOCOL,
        help="Custom protocol name to register for starting the local RocketCoach helper.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    resource_root = bundled_resource_root()
    install_root = resolve_install_root(args.repo_root or None)
    install_root.mkdir(parents=True, exist_ok=True)
    log(f"Using bundled resources from {resource_root}")
    log(f"Installing RocketCoach runtime into {install_root}")

    install_bundled_project_files(resource_root, install_root)

    extra_packages = list(DEFAULT_EXTRA_PACKAGES)
    extra_packages.extend(args.extra_package)

    # pathlib is part of the Python standard library on supported runtimes.
    log("Skipping separate pathlib install because it is built into Python 3.")

    venv_python: Path | None = None
    if not args.skip_project_python:
        host_python = ensure_host_python(
            install_root,
            args.python or None,
            str(args.python_installer_url or DEFAULT_PYTHON_INSTALLER_URL),
        )
        venv_python = ensure_project_venv(install_root, host_python)
        install_python_requirements(resource_root, venv_python, extra_packages)

    if not args.skip_rlbot_gui:
        downloads_dir = install_root / "artifacts" / "installer_downloads"
        msi_path = download_file(args.rlbot_gui_url, downloads_dir / "RLBotGUI.msi")
        install_rlbot_gui(msi_path, interactive=args.interactive_msi)

    failures: list[str] = []
    if not args.skip_botpack:
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

    _, launcher_vbs = write_training_bridge_launcher(install_root)
    if not args.skip_protocol_registration:
        register_training_bridge_protocol(str(args.protocol_name or DEFAULT_TRAINING_BRIDGE_PROTOCOL), launcher_vbs)

    log("Install flow complete.")
    if failures:
        log("Some bot requirement files failed to install:")
        for failure in failures:
            log(f"  - {failure}")
        return 1

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"Fatal error: {exc}")
        raise
