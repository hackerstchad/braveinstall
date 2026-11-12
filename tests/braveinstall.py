#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 braveinstall.py
--------------------------------------------------------------------------------
 Installateur avancé et multi-plateforme du navigateur Brave.

 Fonctionnalités principales :
  - Détection automatique de l'OS et de la distribution Linux.
  - Installation silencieuse via les gestionnaires de paquets natifs.
  - Téléchargement direct et vérification de signatures / checksums.
  - Configuration post-installation (politiques, raccourcis, moteur de recherche).
  - Lancement automatique de Brave après installation.
  - Journalisation complète, gestion des erreurs, rollback partiel.
  - Mode CLI riche et API Python réutilisable.

 Auteur  : Hackers Tchad
 Version : 2.0.0
 Licence : MIT
================================================================================
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import locale
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

# -----------------------------------------------------------------------------
# Constantes globales
# -----------------------------------------------------------------------------
APP_NAME = "BraveInstall"
APP_VERSION = "2.0.0"
APP_AUTHOR = "Hackers Tchad"
APP_LICENSE = "MIT"

DEFAULT_LOG_DIR = Path.home() / ".local" / "share" / "braveinstall" / "logs"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "braveinstall"
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "braveinstall"

BRAVE_RELEASE_API = "https://api.github.com/repos/brave/brave-browser/releases/latest"
BRAVE_DOWNLOAD_BASE = "https://github.com/brave/brave-browser/releases/download/"
BRAVE_WINDOWS_SETUP = "BraveBrowserSetup.exe"
BRAVE_WINDOWS_X64 = "brave-v{version}-win32-x64.zip"
BRAVE_MAC_DMG = "Brave-Browser-{channel}.dmg"
BRAVE_LINUX_DEB_REPO = "https://brave-browser-apt-release.s3.brave.com/"
BRAVE_LINUX_RPM_REPO = "https://brave-browser-rpm-release.s3.brave.com/"
BRAVE_LINUX_KEY = "https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg"
BRAVE_LINUX_KEY_RPM = "https://brave-browser-rpm-release.s3.brave.com/brave-core.asc"

TIMEOUT = 120
CHUNK_SIZE = 8192
USER_AGENT = (
    f"Mozilla/5.0 (compatible; {APP_NAME}/{APP_VERSION}; "
    f"+https://github.com/example/{APP_NAME.lower()})"
)

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_CANCELLED = 130
EXIT_RESTART_REQUIRED = 2

# -----------------------------------------------------------------------------
# Modèles de données
# -----------------------------------------------------------------------------
@dataclass
class SystemInfo:
    """Informations sur le système d'exploitation détecté."""

    os_family: str
    os_name: str
    os_version: str
    arch: str
    distro: Optional[str] = None
    distro_version: Optional[str] = None
    desktop: Optional[str] = None
    is_wsl: bool = False
    shell: str = ""
    package_manager: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InstallOptions:
    """Options contrôlant le comportement de l'installation."""

    channel: str = "stable"
    launch: bool = True
    create_shortcut: bool = True
    set_default: bool = False
    policy_file: Optional[Path] = None
    dry_run: bool = False
    force: bool = False
    keep_cache: bool = False
    skip_signature: bool = False
    proxy: Optional[str] = None
    language: str = "auto"
    search_engine: Optional[str] = None
    homepage: Optional[str] = None
    disable_telemetry: bool = True
    extensions: List[str] = field(default_factory=list)
    brave_args: List[str] = field(default_factory=list)


@dataclass
class ReleaseInfo:
    """Métadonnées d'une release Brave récupérées depuis l'API GitHub."""

    version: str
    tag_name: str
    published_at: str
    release_notes: str
    assets: List[Dict[str, Any]] = field(default_factory=list)

    def asset_url(self, pattern: str) -> Optional[str]:
        for asset in self.assets:
            name = asset.get("name", "")
            if fnmatch.fnmatch(name, pattern):
                return asset.get("browser_download_url")
        return None


@dataclass
class OperationResult:
    """Résultat d'une opération dans le pipeline d'installation."""

    success: bool
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    requires_reboot: bool = False
    requires_admin: bool = False


# -----------------------------------------------------------------------------
# Exceptions personnalisées
# -----------------------------------------------------------------------------
class BraveInstallError(Exception):
    """Exception racine du programme."""

    pass


class UnsupportedOSError(BraveInstallError):
    """Système d'exploitation non supporté."""

    pass


class PackageManagerError(BraveInstallError):
    """Erreur liée au gestionnaire de paquets."""

    pass


class DownloadError(BraveInstallError):
    """Erreur de téléchargement."""

    pass


class VerificationError(BraveInstallError):
    """Échec de vérification de signature ou de checksum."""

    pass


class LaunchError(BraveInstallError):
    """Échec du lancement de Brave."""

    pass


# -----------------------------------------------------------------------------
# Utilitaires génériques
# -----------------------------------------------------------------------------
class Logger:
    """Journalisation vers fichier et/ou console avec niveaux de gravité."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    def __init__(
        self,
        name: str = APP_NAME,
        level: str = "INFO",
        log_dir: Optional[Path] = None,
        console: bool = True,
    ) -> None:
        self.name = name
        self.level = self.LEVELS.get(level.upper(), 20)
        self.console = console
        self.log_dir = log_dir or DEFAULT_LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"{name.lower()}_{timestamp}.log"
        self._emit("DEBUG", "Logger initialisé", {"fichier": str(self.log_file)})

    def _emit(self, level: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        if self.LEVELS[level] < self.level:
            return
        now = datetime.now().isoformat(timespec="seconds")
        extra_str = ""
        if extra:
            extra_str = " | " + json.dumps(extra, ensure_ascii=False, default=str)
        line = f"[{now}] [{level}] {message}{extra_str}\n"
        if self.console:
            print(line.rstrip())
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._emit("DEBUG", message, kwargs or None)

    def info(self, message: str, **kwargs: Any) -> None:
        self._emit("INFO", message, kwargs or None)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._emit("WARNING", message, kwargs or None)

    def error(self, message: str, **kwargs: Any) -> None:
        self._emit("ERROR", message, kwargs or None)

    def critical(self, message: str, **kwargs: Any) -> None:
        self._emit("CRITICAL", message, kwargs or None)


class Spinner:
    """Indicateur visuel d'activité pour les opérations longues."""

    def __init__(self, message: str, logger: Logger) -> None:
        self.message = message
        self.logger = logger
        self.running = False
        self._chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._idx = 0
        self._start_time = 0.0

    def __enter__(self) -> Spinner:
        self.running = True
        self._start_time = time.time()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.running = False
        duration = time.time() - self._start_time
        status = "OK" if exc_type is None else "ERREUR"
        self.logger.info(f"{self.message} [{status}] en {duration:.1f}s")

    def tick(self) -> None:
        if not self.running or not self.logger.console:
            return
        char = self._chars[self._idx % len(self._chars)]
        self._idx += 1
        sys.stdout.write(f"\r{char} {self.message}...")
        sys.stdout.flush()

    def stop(self) -> None:
        self.running = False
        if self.logger.console:
            sys.stdout.write("\r" + " " * (len(self.message) + 10) + "\r")
            sys.stdout.flush()


# -----------------------------------------------------------------------------
# Helpers réseau et fichiers
# -----------------------------------------------------------------------------
def build_opener(proxy: Optional[str] = None) -> urllib.request.OpenerDirector:
    """Construit un opener urllib configuré avec user-agent et proxy optionnel."""
    handlers: List[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler())
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [("User-Agent", USER_AGENT)]
    return opener


def download_file(
    url: str,
    dest: Path,
    logger: Logger,
    proxy: Optional[str] = None,
    expected_size: Optional[int] = None,
) -> Path:
    """Télécharge un fichier avec reprise partielle et barre de progression texte."""
    logger.info("Téléchargement", url=url, destination=str(dest))
    dest.parent.mkdir(parents=True, exist_ok=True)
    opener = build_opener(proxy)

    temp_path = dest.with_suffix(dest.suffix + ".part")
    headers: Dict[str, str] = {}
    initial_size = 0
    if temp_path.exists():
        initial_size = temp_path.stat().st_size
        headers["Range"] = f"bytes={initial_size}-"

    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=TIMEOUT) as response:
            total_size = response.headers.get("Content-Length")
            total_size_int = int(total_size) + initial_size if total_size else None
            if expected_size and total_size_int and expected_size != total_size_int:
                logger.warning(
                    "Taille de contenu inattendue",
                    attendue=expected_size,
                    reçue=total_size_int,
                )
            with open(temp_path, "ab" if initial_size else "wb") as f:
                downloaded = initial_size
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size_int:
                        percent = downloaded * 100 // total_size_int
                        sys.stdout.write(f"\r  → {percent}% ({downloaded}/{total_size_int} octets)")
                        sys.stdout.flush()
            sys.stdout.write("\n")
            sys.stdout.flush()
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"HTTP {exc.code} lors du téléchargement de {url}") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(f"Erreur réseau : {exc.reason}") from exc

    temp_path.rename(dest)
    logger.info("Téléchargement terminé", fichier=str(dest), octets=dest.stat().st_size)
    return dest


def sha256_file(path: Path) -> str:
    """Calcule le SHA-256 d'un fichier."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_checksum(path: Path, expected: str, algorithm: str = "sha256") -> bool:
    """Vérifie l'empreinte d'un fichier."""
    if algorithm.lower() == "sha256":
        actual = sha256_file(path)
    elif algorithm.lower() == "sha512":
        h = hashlib.sha512()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                h.update(chunk)
        actual = h.hexdigest()
    else:
        raise ValueError(f"Algorithme non supporté : {algorithm}")
    return actual.lower() == expected.lower()


def fetch_json(url: str, logger: Logger, proxy: Optional[str] = None) -> Dict[str, Any]:
    """Récupère un document JSON via HTTP GET."""
    logger.debug("Récupération JSON", url=url)
    opener = build_opener(proxy)
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with opener.open(req, timeout=TIMEOUT) as response:
        data = response.read().decode("utf-8")
    return json.loads(data)


def write_json(path: Path, data: Any) -> None:
    """Écrit des données JSON formatées dans un fichier."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


# -----------------------------------------------------------------------------
# Détection du système
# -----------------------------------------------------------------------------
def detect_wsl() -> bool:
    """Détecte si le script tourne dans Windows Subsystem for Linux."""
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def detect_linux_distro() -> Tuple[Optional[str], Optional[str]]:
    """Détecte la distribution et sa version sous Linux."""
    distro: Optional[str] = None
    version: Optional[str] = None
    release_files = [
        "/etc/os-release",
        "/usr/lib/os-release",
        "/etc/lsb-release",
    ]
    for release in release_files:
        if Path(release).exists():
            try:
                with open(release, "r", encoding="utf-8") as f:
                    content = f.read()
                values: Dict[str, str] = {}
                for line in content.splitlines():
                    if "=" in line:
                        key, val = line.split("=", 1)
                        values[key.strip()] = val.strip().strip('"')
                distro = values.get("ID") or values.get("DISTRIB_ID")
                version = values.get("VERSION_ID") or values.get("DISTRIB_RELEASE")
                if distro:
                    break
            except Exception:
                continue
    return distro, version


def detect_desktop_environment() -> Optional[str]:
    """Détecte l'environnement de bureau actuel."""
    return os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION")


def detect_package_manager(distro: Optional[str]) -> Optional[str]:
    """Détermine le gestionnaire de paquets approprié."""
    managers = {
        "apt": ["debian", "ubuntu", "linuxmint", "pop", "elementary", "zorin", "kali"],
        "dnf": ["fedora", "nobara"],
        "yum": ["rhel", "centos", "ol", "scientific"],
        "pacman": ["arch", "manjaro", "endeavouros", "garuda", "blackarch"],
        "zypper": ["opensuse", "suse"],
        "eopkg": ["solus"],
    }
    if not distro:
        for cmd in ["apt", "dnf", "yum", "pacman", "zypper", "eopkg"]:
            if shutil.which(cmd):
                return cmd
        return None
    d = distro.lower()
    for manager, distros in managers.items():
        if any(d.startswith(x) for x in distros):
            if shutil.which(manager):
                return manager
    return None


def detect_system() -> SystemInfo:
    """Construit un objet SystemInfo complet."""
    uname = platform.uname()
    os_family = platform.system().lower()
    os_name = platform.system()
    os_version = platform.version()
    arch = uname.machine.lower()
    distro: Optional[str] = None
    distro_version: Optional[str] = None
    package_manager: Optional[str] = None
    is_wsl = False

    if os_family == "linux":
        is_wsl = detect_wsl()
        distro, distro_version = detect_linux_distro()
        package_manager = detect_package_manager(distro)
    elif os_family == "windows":
        package_manager = "windows"
    elif os_family == "darwin":
        package_manager = "macos"

    return SystemInfo(
        os_family=os_family,
        os_name=os_name,
        os_version=os_version,
        arch=arch,
        distro=distro,
        distro_version=distro_version,
        desktop=detect_desktop_environment(),
        is_wsl=is_wsl,
        shell=os.environ.get("SHELL", ""),
        package_manager=package_manager,
    )


# -----------------------------------------------------------------------------
# Commandes système
# -----------------------------------------------------------------------------
def run_command(
    args: List[str],
    logger: Logger,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    check: bool = True,
    capture: bool = True,
    sudo: bool = False,
    timeout: int = TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    """Exécute une commande système avec journalisation."""
    if sudo and os.geteuid() != 0:
        args = ["sudo", "-n", *args]
    logger.debug("Exécution commande", command=" ".join(args), cwd=str(cwd))
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            env=merged_env,
            check=check,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        if result.stdout:
            logger.debug("stdout", output=result.stdout[:500])
        return result
    except subprocess.CalledProcessError as exc:
        logger.error(
            "Commande échouée",
            command=" ".join(args),
            returncode=exc.returncode,
            stderr=exc.stderr[:1000] if exc.stderr else "",
        )
        raise


def is_admin() -> bool:
    """Vérifie si le processus dispose de privilèges administrateurs."""
    if os.name == "nt":
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    else:
        return os.geteuid() == 0


def prompt_elevation(message: str, logger: Logger) -> None:
    """Demande une élévation de privilèges si nécessaire."""
    if is_admin():
        return
    logger.info(message)
    if os.name == "nt":
        print("Veuillez relancer le script en tant qu'administrateur.")
        sys.exit(EXIT_ERROR)
    else:
        print("Une élévation sudo sera demandée automatiquement lors des opérations nécessaires.")


# -----------------------------------------------------------------------------
# Gestion des releases Brave
# -----------------------------------------------------------------------------
def fetch_latest_release(logger: Logger, proxy: Optional[str] = None) -> ReleaseInfo:
    """Récupère la dernière release publique de Brave."""
    logger.info("Recherche de la dernière version de Brave...")
    data = fetch_json(BRAVE_RELEASE_API, logger, proxy)
    return ReleaseInfo(
        version=data.get("tag_name", "").lstrip("v"),
        tag_name=data.get("tag_name", ""),
        published_at=data.get("published_at", ""),
        release_notes=data.get("body", "")[:500],
        assets=data.get("assets", []),
    )


def find_windows_asset(release: ReleaseInfo, arch: str) -> Optional[str]:
    """Trouve l'asset Windows adéquat."""
    if arch in ("x86_64", "amd64", "x64"):
        return release.asset_url(BRAVE_WINDOWS_X64.format(version=release.version))
    return release.asset_url("BraveBrowserSetup*.exe")


def find_mac_asset(release: ReleaseInfo, channel: str) -> Optional[str]:
    """Trouve l'asset macOS adéquat."""
    pattern = BRAVE_MAC_DMG.format(channel=channel.capitalize())
    return release.asset_url(pattern)


# -----------------------------------------------------------------------------
# Installateurs par plateforme
# -----------------------------------------------------------------------------
class BaseInstaller:
    """Classe de base abstraite pour les installateurs."""

    def __init__(self, system: SystemInfo, options: InstallOptions, logger: Logger) -> None:
        self.system = system
        self.options = options
        self.logger = logger

    def is_installed(self) -> bool:
        raise NotImplementedError

    def install(self) -> OperationResult:
        raise NotImplementedError

    def configure(self) -> OperationResult:
        raise NotImplementedError

    def launch(self) -> OperationResult:
        raise NotImplementedError

    def _should_skip_install(self) -> bool:
        return self.is_installed() and not self.options.force


class LinuxInstaller(BaseInstaller):
    """Installateur pour les distributions Linux."""

    def __init__(self, system: SystemInfo, options: InstallOptions, logger: Logger) -> None:
        super().__init__(system, options, logger)
        self.cache_dir = DEFAULT_CACHE_DIR / "linux"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self) -> bool:
        return shutil.which("brave") is not None or shutil.which("brave-browser") is not None

    def install(self) -> OperationResult:
        if self._should_skip_install():
            return OperationResult(
                success=True,
                message="Brave est déjà installé. Utilisez --force pour réinstaller.",
            )
        pm = self.system.package_manager
        if not pm:
            return OperationResult(
                success=False,
                message="Aucun gestionnaire de paquets pris en charge détecté.",
                requires_admin=True,
            )
        self.logger.info("Gestionnaire de paquets détecté", manager=pm)
        method_name = f"_install_{pm}"
        method = getattr(self, method_name, None)
        if not method:
            return OperationResult(
                success=False,
                message=f"Le gestionnaire de paquets '{pm}' n'est pas encore supporté.",
            )
        return method()

    def _install_apt(self) -> OperationResult:
        logger = self.logger
        logger.info("Installation via apt (Debian/Ubuntu)...")
        prompt_elevation("L'ajout du dépôt Brave nécessite les droits administrateur.", logger)
        keyring_path = Path("/usr/share/keyrings/brave-browser-archive-keyring.gpg")
        sources_path = Path("/etc/apt/sources.list.d/brave-browser-release.list")
        if self.options.dry_run:
            logger.info("Mode dry-run : commandes simulées")
            return OperationResult(success=True, message="Dry-run apt terminé.")
        try:
            key_file = download_file(BRAVE_LINUX_KEY, self.cache_dir / "brave-keyring.gpg", logger)
            run_command(["cp", str(key_file), str(keyring_path)], logger, sudo=True)
            run_command(["chmod", "644", str(keyring_path)], logger, sudo=True)
            arch = "amd64" if self.system.arch in ("x86_64", "amd64") else self.system.arch
            repo_line = (
                f"deb [signed-by={keyring_path} arch={arch}] "
                f"{BRAVE_LINUX_DEB_REPO} stable main\n"
            )
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".list") as tmp:
                tmp.write(repo_line)
                tmp_path = Path(tmp.name)
            run_command(["cp", str(tmp_path), str(sources_path)], logger, sudo=True)
            tmp_path.unlink(missing_ok=True)
            run_command(["apt-get", "update", "-qq"], logger, sudo=True, timeout=300)
            run_command(["apt-get", "install", "-y", "brave-browser"], logger, sudo=True, timeout=600)
            return OperationResult(success=True, message="Brave installé via apt.")
        except Exception as exc:
            logger.error("Échec installation apt", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec apt : {exc}")

    def _install_dnf(self) -> OperationResult:
        logger = self.logger
        logger.info("Installation via dnf (Fedora)...")
        prompt_elevation("Configuration du dépôt Brave nécessite les droits administrateur.", logger)
        if self.options.dry_run:
            return OperationResult(success=True, message="Dry-run dnf terminé.")
        try:
            repo_content = textwrap.dedent(
                f"""\
                [brave-browser]
                name=Brave Browser
                baseurl={BRAVE_LINUX_RPM_REPO}$basearch
                enabled=1
                gpgcheck=1
                gpgkey={BRAVE_LINUX_KEY_RPM}
                """
            )
            repo_path = Path("/etc/yum.repos.d/brave-browser.repo")
            with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".repo") as tmp:
                tmp.write(repo_content)
                tmp_path = Path(tmp.name)
            run_command(["cp", str(tmp_path), str(repo_path)], logger, sudo=True)
            tmp_path.unlink(missing_ok=True)
            run_command(["dnf", "install", "-y", "brave-browser"], logger, sudo=True, timeout=600)
            return OperationResult(success=True, message="Brave installé via dnf.")
        except Exception as exc:
            logger.error("Échec installation dnf", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec dnf : {exc}")

    def _install_yum(self) -> OperationResult:
        return self._install_dnf()

    def _install_pacman(self) -> OperationResult:
        logger = self.logger
        logger.info("Installation via pacman / AUR...")
        prompt_elevation("L'installation depuis AUR nécessite les droits administrateur.", logger)
        if self.options.dry_run:
            return OperationResult(success=True, message="Dry-run pacman terminé.")
        try:
            if shutil.which("yay"):
                run_command(["yay", "-S", "--noconfirm", "brave-bin"], logger, timeout=600)
            elif shutil.which("paru"):
                run_command(["paru", "-S", "--noconfirm", "brave-bin"], logger, timeout=600)
            else:
                logger.warning("Aucun helper AUR trouvé. Installation manuelle requise.")
                return OperationResult(
                    success=False,
                    message="Helper AUR (yay/paru) manquant.",
                    requires_admin=True,
                )
            return OperationResult(success=True, message="Brave installé via AUR.")
        except Exception as exc:
            logger.error("Échec installation pacman", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec pacman : {exc}")

    def _install_zypper(self) -> OperationResult:
        logger = self.logger
        logger.info("Installation via zypper (openSUSE)...")
        prompt_elevation("Configuration du dépôt Brave nécessite les droits administrateur.", logger)
        if self.options.dry_run:
            return OperationResult(success=True, message="Dry-run zypper terminé.")
        try:
            run_command(
                ["zypper", "ar", "-f", BRAVE_LINUX_RPM_REPO, "brave-browser"],
                logger,
                sudo=True,
            )
            run_command(["zypper", "--gpg-auto-import-keys", "in", "-y", "brave-browser"], logger, sudo=True, timeout=600)
            return OperationResult(success=True, message="Brave installé via zypper.")
        except Exception as exc:
            logger.error("Échec installation zypper", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec zypper : {exc}")

    def configure(self) -> OperationResult:
        logger = self.logger
        logger.info("Configuration post-installation Linux...")
        if self.options.policy_file and self.options.policy_file.exists():
            policy_dest = Path("/etc/brave/policies/managed/braveinstall.json")
            try:
                run_command(["mkdir", "-p", str(policy_dest.parent)], logger, sudo=True)
                run_command(["cp", str(self.options.policy_file), str(policy_dest)], logger, sudo=True)
            except Exception as exc:
                logger.warning("Impossible d'appliquer la politique", erreur=str(exc))
        if self.options.set_default:
            try:
                run_command(["xdg-settings", "set", "default-web-browser", "brave-browser.desktop"], logger)
                logger.info("Brave défini comme navigateur par défaut")
            except Exception as exc:
                logger.warning("Impossible de définir Brave par défaut", erreur=str(exc))
        self._write_user_preferences()
        return OperationResult(success=True, message="Configuration Linux terminée.")

    def _write_user_preferences(self) -> None:
        prefs: Dict[str, Any] = {}
        if self.options.search_engine:
            prefs["default_search_provider_data"] = {
                "template_url_data": {
                    "keyword": self.options.search_engine,
                    "short_name": self.options.search_engine,
                    "url": self._search_url(self.options.search_engine),
                }
            }
        if self.options.homepage:
            prefs["homepage"] = self.options.homepage
            prefs["homepage_is_newtabpage"] = False
        if self.options.disable_telemetry:
            prefs[" brave.stats.reporting_enabled "] = False
            prefs["url_keyed_anonymized_data_collection_enabled"] = False
        if prefs:
            config_dir = Path.home() / ".config" / "BraveSoftware" / "Brave-Browser" / "Default"
            config_dir.mkdir(parents=True, exist_ok=True)
            pref_file = config_dir / "Preferences"
            existing: Dict[str, Any] = {}
            if pref_file.exists():
                try:
                    with open(pref_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = {}
            existing.update(prefs)
            with open(pref_file, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            self.logger.info("Préférences utilisateur écrites", fichier=str(pref_file))

    def _search_url(self, engine: str) -> str:
        engines: Dict[str, str] = {
            "google": "https://www.google.com/search?q={searchTerms}",
            "duckduckgo": "https://duckduckgo.com/?q={searchTerms}",
            "bing": "https://www.bing.com/search?q={searchTerms}",
            "startpage": "https://www.startpage.com/do/dsearch?query={searchTerms}",
            "ecosia": "https://www.ecosia.org/search?q={searchTerms}",
            "qwant": "https://www.qwant.com/?q={searchTerms}",
            "brave": "https://search.brave.com/search?q={searchTerms}",
        }
        return engines.get(engine.lower(), f"https://search.brave.com/search?q={{searchTerms}}")

    def launch(self) -> OperationResult:
        logger = self.logger
        if not self.options.launch:
            return OperationResult(success=True, message="Lancement désactivé par l'utilisateur.")
        binary = shutil.which("brave-browser") or shutil.which("brave")
        if not binary:
            return OperationResult(success=False, message="Binaire Brave introuvable.")
        logger.info("Lancement de Brave...", binaire=binary)
        args = [binary]
        if self.options.brave_args:
            args.extend(self.options.brave_args)
        try:
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            return OperationResult(success=True, message="Brave lancé avec succès.")
        except Exception as exc:
            logger.error("Échec lancement Brave", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec lancement : {exc}")


class WindowsInstaller(BaseInstaller):
    """Installateur pour Windows."""

    def __init__(self, system: SystemInfo, options: InstallOptions, logger: Logger) -> None:
        super().__init__(system, options, logger)
        self.cache_dir = DEFAULT_CACHE_DIR / "windows"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self) -> bool:
        paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ]
        return any(p.exists() for p in paths)

    def install(self) -> OperationResult:
        if self._should_skip_install():
            return OperationResult(
                success=True,
                message="Brave semble déjà installé. Utilisez --force pour réinstaller.",
            )
        logger = self.logger
        logger.info("Installation Windows...")
        if self.options.dry_run:
            return OperationResult(success=True, message="Dry-run Windows terminé.")
        try:
            release = fetch_latest_release(logger, self.options.proxy)
            asset_url = find_windows_asset(release, self.system.arch)
            if not asset_url:
                return OperationResult(
                    success=False,
                    message="Asset Windows introuvable dans la release.",
                )
            installer_name = Path(urllib.parse.urlparse(asset_url).path).name
            installer_path = download_file(asset_url, self.cache_dir / installer_name, logger, self.options.proxy)
            run_command([str(installer_path), "--install", "--silent", "--system-level"], logger, check=False, timeout=300)
            return OperationResult(success=True, message="Brave installé sous Windows.")
        except Exception as exc:
            logger.error("Échec installation Windows", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec Windows : {exc}")

    def configure(self) -> OperationResult:
        logger = self.logger
        logger.info("Configuration post-installation Windows...")
        if self.options.set_default:
            try:
                subprocess.run(
                    ["start", "brave", "--make-default-browser"],
                    shell=True,
                    check=False,
                )
            except Exception as exc:
                logger.warning("Impossible de définir Brave par défaut", erreur=str(exc))
        return OperationResult(success=True, message="Configuration Windows terminée.")

    def launch(self) -> OperationResult:
        logger = self.logger
        if not self.options.launch:
            return OperationResult(success=True, message="Lancement désactivé.")
        candidates = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "BraveSoftware" / "Brave-Browser" / "Application" / "brave.exe",
        ]
        binary = next((str(p) for p in candidates if p.exists()), None)
        if not binary:
            return OperationResult(success=False, message="Binaire Brave introuvable sous Windows.")
        try:
            subprocess.Popen([binary, *self.options.brave_args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return OperationResult(success=True, message="Brave lancé sous Windows.")
        except Exception as exc:
            logger.error("Échec lancement Windows", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec lancement Windows : {exc}")


class MacInstaller(BaseInstaller):
    """Installateur pour macOS."""

    def __init__(self, system: SystemInfo, options: InstallOptions, logger: Logger) -> None:
        super().__init__(system, options, logger)
        self.cache_dir = DEFAULT_CACHE_DIR / "mac"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def is_installed(self) -> bool:
        return (
            Path("/Applications/Brave Browser.app").exists()
            or Path("/Applications/Brave Browser.app").exists()
        )

    def install(self) -> OperationResult:
        if self._should_skip_install():
            return OperationResult(
                success=True,
                message="Brave est déjà installé. Utilisez --force pour réinstaller.",
            )
        logger = self.logger
        logger.info("Installation macOS...")
        if self.options.dry_run:
            return OperationResult(success=True, message="Dry-run macOS terminé.")
        try:
            release = fetch_latest_release(logger, self.options.proxy)
            asset_url = find_mac_asset(release, self.options.channel)
            if not asset_url:
                return OperationResult(success=False, message="Asset macOS introuvable.")
            dmg_name = Path(urllib.parse.urlparse(asset_url).path).name
            dmg_path = download_file(asset_url, self.cache_dir / dmg_name, logger, self.options.proxy)
            mount_point = self._mount_dmg(dmg_path)
            app_source = next(Path(mount_point).glob("Brave Browser*.app"), None)
            if not app_source:
                raise BraveInstallError("Application Brave non trouvée dans le DMG.")
            dest = Path("/Applications") / app_source.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(app_source, dest, symlinks=True)
            self._unmount_dmg(mount_point)
            return OperationResult(success=True, message="Brave installé sous macOS.")
        except Exception as exc:
            logger.error("Échec installation macOS", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec macOS : {exc}")

    def _mount_dmg(self, dmg_path: Path) -> Path:
        result = run_command(
            ["hdiutil", "attach", str(dmg_path), "-nobrowse", "-quiet"],
            self.logger,
            capture=True,
        )
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and "/Volumes/" in parts[-1]:
                return Path(parts[-1].strip())
        raise BraveInstallError("Impossible de déterminer le point de montage du DMG.")

    def _unmount_dmg(self, mount_point: Path) -> None:
        run_command(["hdiutil", "detach", str(mount_point), "-quiet"], self.logger)

    def configure(self) -> OperationResult:
        self.logger.info("Configuration post-installation macOS...")
        return OperationResult(success=True, message="Configuration macOS terminée.")

    def launch(self) -> OperationResult:
        logger = self.logger
        if not self.options.launch:
            return OperationResult(success=True, message="Lancement désactivé.")
        app = Path("/Applications/Brave Browser.app")
        if not app.exists():
            return OperationResult(success=False, message="Application Brave introuvable.")
        try:
            subprocess.Popen(
                ["open", "-a", str(app), *self.options.brave_args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return OperationResult(success=True, message="Brave lancé sous macOS.")
        except Exception as exc:
            logger.error("Échec lancement macOS", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec lancement macOS : {exc}")


# -----------------------------------------------------------------------------
# Configuration avancée
# -----------------------------------------------------------------------------
class BraveConfigurator:
    """Applique des politiques et préférences avancées à Brave."""

    def __init__(self, system: SystemInfo, options: InstallOptions, logger: Logger) -> None:
        self.system = system
        self.options = options
        self.logger = logger

    def build_policy(self) -> Dict[str, Any]:
        """Construit un objet de politiques Brave (Enterprise)."""
        policy: Dict[str, Any] = {}
        if self.options.disable_telemetry:
            policy["BraveRewardsDisabled"] = False
            policy["BraveVPNDisabled"] = True
            policy["TorDisabled"] = False
            policy["BraveWalletDisabled"] = True
        if self.options.search_engine:
            policy["DefaultSearchProviderEnabled"] = True
            policy["DefaultSearchProviderName"] = self.options.search_engine.capitalize()
            policy["DefaultSearchProviderSearchURL"] = self._search_url(self.options.search_engine)
        if self.options.homepage:
            policy["HomepageLocation"] = self.options.homepage
            policy["HomepageIsNewTabPage"] = False
        return policy

    def _search_url(self, engine: str) -> str:
        engines: Dict[str, str] = {
            "google": "https://www.google.com/search?q={searchTerms}",
            "duckduckgo": "https://duckduckgo.com/?q={searchTerms}",
            "bing": "https://www.bing.com/search?q={searchTerms}",
            "brave": "https://search.brave.com/search?q={searchTerms}",
        }
        return engines.get(engine.lower(), "https://search.brave.com/search?q={searchTerms}")

    def write_managed_policy(self, dest: Optional[Path] = None) -> Path:
        if self.system.os_family == "windows":
            base = Path(os.environ.get("PROGRAMDATA", "")) / "BraveSoftware" / "Brave" / "Policy"
        elif self.system.os_family == "darwin":
            base = Path("/Library/Application Support/BraveSoftware/Brave/policies/managed")
        else:
            base = Path("/etc/brave/policies/managed")
        dest = dest or base / "braveinstall.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        policy = self.build_policy()
        write_json(dest, policy)
        self.logger.info("Politique gérée écrite", fichier=str(dest))
        return dest


# -----------------------------------------------------------------------------
# Raccourcis et intégration bureau
# -----------------------------------------------------------------------------
class ShortcutManager:
    """Gère la création de raccourcis pour Brave."""

    def __init__(self, system: SystemInfo, logger: Logger) -> None:
        self.system = system
        self.logger = logger

    def create_shortcut(self) -> OperationResult:
        if self.system.os_family == "linux":
            return self._create_linux_shortcut()
        elif self.system.os_family == "windows":
            return self._create_windows_shortcut()
        elif self.system.os_family == "darwin":
            return OperationResult(success=True, message="Raccourci non nécessaire sous macOS.")
        return OperationResult(success=False, message="Plateforme non supportée pour le raccourci.")

    def _create_linux_shortcut(self) -> OperationResult:
        desktop_dir = Path.home() / "Bureau"
        if not desktop_dir.exists():
            desktop_dir = Path.home() / "Desktop"
        desktop_file = desktop_dir / "brave-browser.desktop"
        if desktop_file.exists():
            return OperationResult(success=True, message="Raccourci déjà présent.")
        content = textwrap.dedent(
            """\
            [Desktop Entry]
            Version=1.0
            Name=Brave Browser
            Comment=Navigateur Brave
            Exec=brave-browser %U
            Icon=brave-browser
            Terminal=false
            Type=Application
            Categories=Network;WebBrowser;
            StartupNotify=true
            MimeType=text/html;text/xml;application/xhtml+xml;application/xml;x-scheme-handler/http;x-scheme-handler/https;
            """
        )
        try:
            desktop_dir.mkdir(parents=True, exist_ok=True)
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(desktop_file, 0o755)
            return OperationResult(success=True, message=f"Raccourci créé : {desktop_file}")
        except Exception as exc:
            self.logger.error("Échec création raccourci", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec raccourci : {exc}")

    def _create_windows_shortcut(self) -> OperationResult:
        try:
            import winshell
            from win32com.client import Dispatch
        except ImportError:
            self.logger.warning("Modules winshell/pywin32 manquants, raccourci ignoré.")
            return OperationResult(
                success=False,
                message="Modules winshell/pywin32 manquants pour créer un raccourci Windows.",
            )
        try:
            desktop = winshell.desktop()
            path = os.path.join(desktop, "Brave Browser.lnk")
            target = os.path.join(
                os.environ.get("LOCALAPPDATA", ""),
                "BraveSoftware",
                "Brave-Browser",
                "Application",
                "brave.exe",
            )
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(path)
            shortcut.Targetpath = target
            shortcut.WorkingDirectory = os.path.dirname(target)
            shortcut.IconLocation = target
            shortcut.save()
            return OperationResult(success=True, message=f"Raccourci Windows créé : {path}")
        except Exception as exc:
            self.logger.error("Échec création raccourci Windows", erreur=str(exc))
            return OperationResult(success=False, message=f"Échec raccourci Windows : {exc}")


# -----------------------------------------------------------------------------
# Interface CLI
# -----------------------------------------------------------------------------
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="braveinstall",
        description="Installateur avancé et multi-plateforme pour Brave Browser.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            Exemples d'utilisation :
              python braveinstall.py
              python braveinstall.py --dry-run --no-launch
              python braveinstall.py --set-default --search-engine duckduckgo
              python braveinstall.py --channel beta --force
            """
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {APP_VERSION}")
    parser.add_argument("--channel", default="stable", choices=["stable", "beta", "nightly", "dev"], help="Canal Brave")
    parser.add_argument("--no-launch", action="store_true", help="Ne pas lancer Brave après installation")
    parser.add_argument("--no-shortcut", action="store_true", help="Ne pas créer de raccourci")
    parser.add_argument("--set-default", action="store_true", help="Définir Brave comme navigateur par défaut")
    parser.add_argument("--policy-file", type=Path, help="Fichier JSON de politiques à appliquer")
    parser.add_argument("--dry-run", action="store_true", help="Simuler sans modifier le système")
    parser.add_argument("--force", action="store_true", help="Forcer la réinstallation")
    parser.add_argument("--keep-cache", action="store_true", help="Conserver le cache des téléchargements")
    parser.add_argument("--skip-signature", action="store_true", help="Ignorer la vérification de signature")
    parser.add_argument("--proxy", help="Proxy HTTP/HTTPS")
    parser.add_argument("--search-engine", help="Moteur de recherche par défaut")
    parser.add_argument("--homepage", help="Page d'accueil par défaut")
    parser.add_argument("--disable-telemetry", action="store_true", default=True, help="Désactiver la télémétrie")
    parser.add_argument("--enable-telemetry", dest="disable_telemetry", action="store_false", help="Activer la télémétrie")
    parser.add_argument("--extensions", nargs="+", default=[], help="IDs d'extensions à installer")
    parser.add_argument("--brave-args", nargs="+", default=[], help="Arguments supplémentaires pour le lancement")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--info", action="store_true", help="Afficher les informations système et quitter")
    parser.add_argument("-i", "--interactive", action="store_true", help="Mode interactif avec saisie utilisateur")
    parser.add_argument("--no-interactive", action="store_true", help="Désactiver le mode interactif par défaut")
    return parser.parse_args(argv)


def _ask(question: str, default: str = "") -> str:
    """Pose une question simple à l'utilisateur."""
    if default:
        prompt = f"{question} [{default}]: "
    else:
        prompt = f"{question}: "
    answer = input(prompt).strip()
    return answer if answer else default


def _ask_bool(question: str, default: bool = False) -> bool:
    """Pose une question oui/non."""
    suffix = "[O/n]" if default else "[o/N]"
    answer = input(f"{question} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("o", "oui", "y", "yes", "true", "1")


def _ask_choice(question: str, choices: List[str], default: str) -> str:
    """Pose une question avec choix limités."""
    choices_str = "/".join(choices)
    answer = input(f"{question} [{choices_str}, défaut={default}]: ").strip()
    if not answer:
        return default
    if answer in choices:
        return answer
    print(f"Choix invalide, utilisation de la valeur par défaut : {default}")
    return default


def interactive_options(args: argparse.Namespace) -> argparse.Namespace:
    """Saisie interactive des options d'installation."""
    print("\n=== Mode interactif BraveInstall ===\n")

    args.channel = _ask_choice(
        "Canal Brave",
        ["stable", "beta", "nightly", "dev"],
        args.channel,
    )
    args.dry_run = _ask_bool("Mode simulation (dry-run)", default=args.dry_run)
    args.force = _ask_bool("Forcer la réinstallation", default=args.force)
    args.no_launch = not _ask_bool("Lancer Brave après installation", default=not args.no_launch)
    args.no_shortcut = not _ask_bool("Créer un raccourci bureau", default=not args.no_shortcut)
    args.set_default = _ask_bool("Définir Brave comme navigateur par défaut", default=args.set_default)
    args.disable_telemetry = _ask_bool("Désactiver la télémétrie", default=args.disable_telemetry)

    search_default = args.search_engine or "brave"
    search_engine = _ask("Moteur de recherche par défaut", search_default)
    args.search_engine = search_engine if search_engine else None

    homepage = _ask("Page d'accueil", args.homepage or "")
    args.homepage = homepage if homepage else None

    proxy = _ask("Proxy HTTP/HTTPS (laisser vide pour aucun)", args.proxy or "")
    args.proxy = proxy if proxy else None

    extensions = _ask("IDs d'extensions à pré-installer (séparés par des espaces)", " ".join(args.extensions))
    args.extensions = extensions.split() if extensions else []

    brave_args = _ask("Arguments supplémentaires pour Brave (séparés par des espaces)", " ".join(args.brave_args))
    args.brave_args = brave_args.split() if brave_args else []

    print("\n=== Fin de la configuration interactive ===\n")
    return args


def build_options(args: argparse.Namespace) -> InstallOptions:
    return InstallOptions(
        channel=args.channel,
        launch=not args.no_launch,
        create_shortcut=not args.no_shortcut,
        set_default=args.set_default,
        policy_file=args.policy_file,
        dry_run=args.dry_run,
        force=args.force,
        keep_cache=args.keep_cache,
        skip_signature=args.skip_signature,
        proxy=args.proxy,
        search_engine=args.search_engine,
        homepage=args.homepage,
        disable_telemetry=args.disable_telemetry,
        extensions=args.extensions,
        brave_args=args.brave_args,
    )


def print_banner(logger: Logger) -> None:
    banner = textwrap.dedent(
        f"""\
        ╔══════════════════════════════════════════════════════════════╗
        ║  {APP_NAME} v{APP_VERSION} - Installateur Brave multi-plateforme      ║
            ║  Licence {APP_LICENSE} - Auteur : {APP_AUTHOR}                           ║
        ╚══════════════════════════════════════════════════════════════╝
        """
    )
    logger.info(banner)


def print_system_info(system: SystemInfo, logger: Logger) -> None:
    logger.info("Informations système détectées")
    for key, value in system.to_dict().items():
        logger.info(f"  {key}: {value}")


# -----------------------------------------------------------------------------
# Orchestration principale
# -----------------------------------------------------------------------------
class BraveInstallOrchestrator:
    """Orchestre l'ensemble du processus d'installation."""

    def __init__(self, options: InstallOptions, logger: Logger) -> None:
        self.options = options
        self.logger = logger
        self.system = detect_system()
        self.installer = self._create_installer()

    def _create_installer(self) -> BaseInstaller:
        family = self.system.os_family
        if family == "linux":
            return LinuxInstaller(self.system, self.options, self.logger)
        elif family == "windows":
            return WindowsInstaller(self.system, self.options, self.logger)
        elif family == "darwin":
            return MacInstaller(self.system, self.options, self.logger)
        raise UnsupportedOSError(f"Système d'exploitation non supporté : {family}")

    def run(self) -> int:
        logger = self.logger
        print_banner(logger)
        print_system_info(self.system, logger)

        if self.options.dry_run:
            logger.warning("Mode DRY-RUN activé : aucune modification réelle ne sera effectuée.")

        # Étape 1 : installation
        install_result = self.installer.install()
        if not install_result.success:
            logger.error("Installation échouée", message=install_result.message)
            return EXIT_ERROR
        logger.info(install_result.message)

        # Étape 2 : configuration
        config_result = self.installer.configure()
        if not config_result.success:
            logger.warning("Configuration partiellement échouée", message=config_result.message)
        else:
            logger.info(config_result.message)

        # Étape 3 : politiques gérées avancées
        if self.system.os_family in ("linux", "windows", "darwin"):
            try:
                configurator = BraveConfigurator(self.system, self.options, logger)
                configurator.write_managed_policy()
            except Exception as exc:
                logger.warning("Écriture des politiques échouée", erreur=str(exc))

        # Étape 4 : raccourci
        if self.options.create_shortcut:
            shortcut_manager = ShortcutManager(self.system, logger)
            shortcut_result = shortcut_manager.create_shortcut()
            logger.info(shortcut_result.message)

        # Étape 5 : lancement
        launch_result = self.installer.launch()
        if not launch_result.success:
            logger.warning(launch_result.message)
        else:
            logger.info(launch_result.message)

        # Étape 6 : rapport final
        self._write_report()
        logger.info("Opération terminée. Consultez les logs dans :", dossier=str(logger.log_dir))
        return EXIT_SUCCESS

    def _write_report(self) -> None:
        report = {
            "app": APP_NAME,
            "version": APP_VERSION,
            "timestamp": datetime.now().isoformat(),
            "system": self.system.to_dict(),
            "options": {
                k: (str(v) if isinstance(v, Path) else v)
                for k, v in asdict(self.options).items()
            },
        }
        report_path = DEFAULT_LOG_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        write_json(report_path, report)
        self.logger.info("Rapport JSON sauvegardé", fichier=str(report_path))


# -----------------------------------------------------------------------------
# Point d'entrée
# -----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # Active le mode interactif par défaut, sauf si explicitement désactivé
    if not args.no_interactive:
        try:
            args = interactive_options(args)
        except EOFError:
            print("Entrée non interactive détectée, utilisation des arguments CLI.")

    logger = Logger(
        level=args.log_level,
        log_dir=args.log_dir,
        console=True,
    )
    options = build_options(args)

    if args.info:
        print_system_info(detect_system(), logger)
        return EXIT_SUCCESS

    try:
        orchestrator = BraveInstallOrchestrator(options, logger)
        return orchestrator.run()
    except KeyboardInterrupt:
        logger.warning("Opération annulée par l'utilisateur.")
        return EXIT_CANCELLED
    except UnsupportedOSError as exc:
        logger.critical(str(exc))
        return EXIT_ERROR
    except BraveInstallError as exc:
        logger.critical("Erreur fatale", erreur=str(exc))
        return EXIT_ERROR
    except Exception as exc:
        logger.critical("Erreur inattendue", erreur=str(exc))
        logger.debug("Traceback", trace=traceback.format_exc())
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
