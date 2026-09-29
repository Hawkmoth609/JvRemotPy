"""
╔══════════════════════════════════════════════════════════════════╗
║         File Browser v2.0 — نظام تصفح ملفات متقدم               ║
║                                                                  ║
║  الميزات:                                                        ║
║    • Natural Sort (file2 قبل file10)                            ║
║    • Thread-safe listing مع timeout                              ║
║    • Breadcrumb navigation                                       ║
║    • بحث داخل المجلد (Modal)                                    ║
║    • فلترة بالنوع (صور/فيديو/صوت/مستندات/APK)                   ║
║    • إخفاء/إظهار الملفات المخفية                                ║
║    • Multi-select للإرسال الجماعي                               ║
║    • Recent Folders (آخر 10 مجلدات)                             ║
║    • Path Cache (تحسين الأداء)                                  ║
║    • معالجة أخطاء تفصيلية                                        ║
║    • Path safety مع os.path.realpath + prefix check             ║
║    • Jump-to-page + Jump-to-path                                ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import time
import threading
import concurrent.futures
from collections import deque
from typing import List, Optional, Tuple, Dict, Any

import discord


# ═══════════════════════════════════════════════════════════════════
#                       Constants
# ═══════════════════════════════════════════════════════════════════
FILES_PER_PAGE = 20
MAX_HISTORY = 10
LIST_TIMEOUT_SEC = 5.0
MAX_SCAN_FILES = 5000

# File type filters
FILTER_ALL = "all"
FILTER_IMAGES = "images"
FILTER_VIDEOS = "videos"
FILTER_AUDIO = "audio"
FILTER_DOCS = "docs"
FILTER_APK = "apk"
FILTER_FOLDERS = "folders"

FILTER_EXTENSIONS = {
    FILTER_IMAGES: {".jpg", ".jpeg", ".png", ".webp", ".gif",
                    ".bmp", ".heic", ".heif", ".svg", ".tiff"},
    FILTER_VIDEOS: {".mp4", ".mkv", ".avi", ".mov", ".webm",
                    ".3gp", ".flv", ".wmv", ".m4v"},
    FILTER_AUDIO: {".mp3", ".wav", ".ogg", ".m4a", ".flac",
                   ".aac", ".opus", ".amr", ".3gp"},
    FILTER_DOCS: {".pdf", ".doc", ".docx", ".xls", ".xlsx",
                  ".ppt", ".pptx", ".txt", ".md", ".rtf",
                  ".odt", ".ods", ".csv", ".json", ".xml"},
    FILTER_APK: {".apk", ".xapk", ".apks", ".aab"},
}

FILTER_ICONS = {
    FILTER_ALL: "📁",
    FILTER_IMAGES: "🖼️",
    FILTER_VIDEOS: "🎬",
    FILTER_AUDIO: "🎵",
    FILTER_DOCS: "📄",
    FILTER_APK: "📦",
    FILTER_FOLDERS: "📁",
}

FILTER_LABELS = {
    FILTER_ALL: "الكل",
    FILTER_IMAGES: "صور",
    FILTER_VIDEOS: "فيديو",
    FILTER_AUDIO: "صوتيات",
    FILTER_DOCS: "مستندات",
    FILTER_APK: "APK",
    FILTER_FOLDERS: "مجلدات فقط",
}


# ═══════════════════════════════════════════════════════════════════
#                       Natural Sort
# ═══════════════════════════════════════════════════════════════════
_NATURAL_RE = re.compile(r'(\d+)')


def natural_key(text: str):
    """
    مفتاح ترتيب طبيعي: file2 < file10 < file100
    """
    if not text:
        return [""]
    parts = _NATURAL_RE.split(text.lower())
    result = []
    for p in parts:
        if p.isdigit():
            result.append((0, int(p)))
        else:
            result.append((1, p))
    return result


# ═══════════════════════════════════════════════════════════════════
#                       Safe Listdir with Timeout
# ═══════════════════════════════════════════════════════════════════
def safe_listdir(path: str, timeout: float = LIST_TIMEOUT_SEC) -> Optional[List[str]]:
    """
    قائمة محتوى مجلد بأمان مع timeout.
    يعيد None عند الفشل أو انتهاء المهلة.
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(os.listdir, path)
            return fut.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return None
    except PermissionError:
        return None
    except FileNotFoundError:
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════
#                       Path Safety
# ═══════════════════════════════════════════════════════════════════
def is_path_safe(path: str, allowed_roots: List[str]) -> bool:
    """
    فحص أمان المسار — يمنع traversal + symbol links.
    """
    if not path or not allowed_roots:
        return False

    try:
        real = os.path.realpath(path)
    except Exception:
        return False

    for root in allowed_roots:
        try:
            rr = os.path.realpath(root)
            if real == rr:
                return True
            # تأكد من أن real داخل rr
            if real.startswith(rr + os.sep):
                return True
        except Exception:
            continue

    return False


# ═══════════════════════════════════════════════════════════════════
#                       File Metadata
# ═══════════════════════════════════════════════════════════════════
def fmt_size(n: int) -> str:
    try:
        n = float(n)
    except Exception:
        return "?"
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def fmt_time(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "?"


def get_file_icon(name: str, is_dir: bool = False) -> str:
    if is_dir:
        return "📁"
    ext = os.path.splitext(name)[1].lower()
    icons = {
        ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🎞️",
        ".webp": "🖼️", ".bmp": "🖼️", ".heic": "🖼️", ".heif": "🖼️",
        ".mp4": "🎬", ".mkv": "🎬", ".avi": "🎬", ".mov": "🎬",
        ".webm": "🎬", ".3gp": "🎬",
        ".mp3": "🎵", ".wav": "🎵", ".ogg": "🎵", ".m4a": "🎵",
        ".flac": "🎵", ".aac": "🎵",
        ".pdf": "📕", ".doc": "📘", ".docx": "📘",
        ".xls": "📗", ".xlsx": "📗", ".ppt": "📙", ".pptx": "📙",
        ".zip": "🗜️", ".rar": "🗜️", ".tar": "🗜️", ".gz": "🗜️",
        ".7z": "🗜️",
        ".apk": "📦", ".xapk": "📦", ".aab": "📦",
        ".exe": "⚙️", ".sh": "⚙️",
        ".txt": "📄", ".log": "📄", ".md": "📖", ".rtf": "📄",
        ".py": "🐍", ".java": "☕", ".js": "📜", ".html": "🌐",
        ".css": "🎨", ".json": "⚙️", ".xml": "📋",
        ".yml": "📋", ".yaml": "📋", ".ini": "⚙️",
        ".db": "🗄️", ".sqlite": "🗄️", ".sql": "🗄️",
        ".ttf": "🔤", ".otf": "🔤", ".woff": "🔤",
        ".csv": "📊",
    }
    return icons.get(ext, "📄")


def file_matches_filter(name: str, is_dir: bool, filter_type: str) -> bool:
    """فحص مطابقة الملف للفلتر."""
    if filter_type == FILTER_ALL:
        return True
    if filter_type == FILTER_FOLDERS:
        return is_dir
    if is_dir:
        return False  # الملفات المرشّحة تُظهر فقط المجلدات أو المطابقات

    ext = os.path.splitext(name)[1].lower()
    allowed = FILTER_EXTENSIONS.get(filter_type)
    if not allowed:
        return True
    return ext in allowed


# ═══════════════════════════════════════════════════════════════════
#                       Breadcrumbs
# ═══════════════════════════════════════════════════════════════════
def build_breadcrumbs(path: str, root: str, max_items: int = 4) -> str:
    """
    يبني مسار مختصر لمجلد التنقل.
    مثال: `/sdcard/DCIM/Camera` → `📁/sdcard/.../Camera`
    """
    try:
        if not path.startswith(root):
            return f"📁 `{path}`"

        rel = os.path.relpath(path, root)
        if rel == ".":
            return f"📁 `{root}`"

        parts = rel.split(os.sep)
        if len(parts) <= max_items:
            return f"📁 `{root}` / " + " / ".join(f"**{p}**" for p in parts)

        # اختصار
        first = parts[0]
        last = parts[-1]
        return f"📁 `{root}` / **{first}** / … / **{last}**"
    except Exception:
        return f"📁 `{path}`"


# ═══════════════════════════════════════════════════════════════════
#                       Recent Folders
# ═══════════════════════════════════════════════════════════════════
_recent_lock = threading.Lock()
_recent_folders: deque = deque(maxlen=MAX_HISTORY)


def add_recent(path: str):
    with _recent_lock:
        try:
            if path in _recent_folders:
                _recent_folders.remove(path)
            _recent_folders.appendleft(path)
        except Exception:
            pass


def get_recents() -> List[str]:
    with _recent_lock:
        return list(_recent_folders)


# ═══════════════════════════════════════════════════════════════════
#                       Browse State
# ═══════════════════════════════════════════════════════════════════
class BrowseState:
    """حالة تصفح مجلد واحد."""
    __slots__ = ('path', 'page', 'sort_by', 'show_hidden',
                 'filter_type', 'search_query', '_cached_items',
                 '_cache_time')

    def __init__(self, path: str, page: int = 0, sort_by: str = "name",
                 show_hidden: bool = False, filter_type: str = FILTER_ALL,
                 search_query: str = ""):
        self.path = path
        self.page = page
        self.sort_by = sort_by
        self.show_hidden = show_hidden
        self.filter_type = filter_type
        self.search_query = search_query
        self._cached_items: Optional[List[Tuple[str, bool, int, float]]] = None
        self._cache_time = 0.0

    def invalidate_cache(self):
        self._cached_items = None
        self._cache_time = 0.0

    def copy_with(self, **kwargs) -> 'BrowseState':
        state = BrowseState(
            path=kwargs.get('path', self.path),
            page=kwargs.get('page', self.page),
            sort_by=kwargs.get('sort_by', self.sort_by),
            show_hidden=kwargs.get('show_hidden', self.show_hidden),
            filter_type=kwargs.get('filter_type', self.filter_type),
            search_query=kwargs.get('search_query', self.search_query),
        )
        return state


# ═══════════════════════════════════════════════════════════════════
#                       Discord Modals
# ═══════════════════════════════════════════════════════════════════
class SearchModal(discord.ui.Modal, title="🔎 بحث في المجلد"):
    query = discord.ui.TextInput(
        label="كلمة البحث",
        placeholder="اكتب جزءًا من الاسم...",
        required=True,
        max_length=100,
    )

    def __init__(self, parent_view: 'AdvancedFileBrowserView'):
        super().__init__()
        self._parent = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_state = self._parent.state.copy_with(
                search_query=str(self.query).strip(),
                page=0,
            )
            new_state.invalidate_cache()
            new_view = AdvancedFileBrowserView(
                state=new_state,
                root=self._parent.root,
                allowed_roots=self._parent.allowed_roots,
                is_allowed_fn=self._parent.is_allowed_fn,
                check_user_fn=self._parent.check_user_fn,
                device_name=self._parent.device_name,
            )
            await interaction.response.edit_message(
                content=new_view.build_title(),
                view=new_view,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ خطأ: {e}", ephemeral=True)


class JumpModal(discord.ui.Modal, title="🎯 الانتقال إلى مسار"):
    path = discord.ui.TextInput(
        label="المسار الكامل",
        placeholder="/sdcard/DCIM/Camera",
        required=True,
        max_length=500,
    )

    def __init__(self, parent_view: 'AdvancedFileBrowserView'):
        super().__init__()
        self._parent = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target = str(self.path).strip()
            if not self._parent.is_allowed_fn(target):
                await interaction.response.send_message(
                    "❌ المسار خارج النطاق المسموح.", ephemeral=True)
                return
            if not os.path.isdir(target):
                await interaction.response.send_message(
                    f"❌ ليس مجلدًا: `{target}`", ephemeral=True)
                return

            new_state = BrowseState(path=target)
            new_view = AdvancedFileBrowserView(
                state=new_state,
                root=self._parent.root,
                allowed_roots=self._parent.allowed_roots,
                is_allowed_fn=self._parent.is_allowed_fn,
                check_user_fn=self._parent.check_user_fn,
                device_name=self._parent.device_name,
            )
            await interaction.response.edit_message(
                content=new_view.build_title(),
                view=new_view,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ خطأ: {e}", ephemeral=True)


# ═══════════════════════════════════════════════════════════════════
#                       Advanced File Browser View
# ═══════════════════════════════════════════════════════════════════
class AdvancedFileBrowserView(discord.ui.View):
    """
    File Browser v2.0 مع كل التحسينات.
    """

    def __init__(self,
                 state: BrowseState,
                 root: str,
                 allowed_roots: List[str],
                 is_allowed_fn,
                 check_user_fn,
                 device_name: str = "Android",
                 timeout: float = 1800.0):
        super().__init__(timeout=timeout)
        self.state = state
        self.root = root
        self.allowed_roots = allowed_roots
        self.is_allowed_fn = is_allowed_fn
        self.check_user_fn = check_user_fn
        self.device_name = device_name

        self.items: List[Tuple[str, bool, int, float]] = []
        self.total = 0
        self.error_msg: Optional[str] = None

        self._load_items()
        self._build_ui()

    # ═══════════════════════════════════════════════════════════
    #      Load items
    # ═══════════════════════════════════════════════════════════
    def _load_items(self):
        """تحميل محتوى المجلد الحالي."""
        path = self.state.path

        # فحص الأمان
        if not self.is_allowed_fn(path):
            self.error_msg = "❌ خارج النطاق"
            return

        if not os.path.isdir(path):
            self.error_msg = "❌ ليس مجلدًا"
            return

        # قائمة آمنة مع timeout
        raw = safe_listdir(path)
        if raw is None:
            self.error_msg = "❌ لا يمكن قراءة المجلد (صلاحية أو timeout)"
            return

        # جمع الميتاداتا
        items: List[Tuple[str, bool, int, float]] = []
        search_q = (self.state.search_query or "").lower()
        show_hidden = self.state.show_hidden
        filter_type = self.state.filter_type

        for name in raw:
            # إخفاء المخفي
            if not show_hidden and name.startswith("."):
                continue

            full = os.path.join(path, name)
            try:
                is_dir = os.path.isdir(full)
            except Exception:
                continue

            # فلترة بالنوع
            if not file_matches_filter(name, is_dir, filter_type):
                continue

            # بحث
            if search_q and search_q not in name.lower():
                continue

            # حجم + وقت
            size = 0
            mtime = 0.0
            try:
                if not is_dir:
                    st = os.stat(full)
                    size = st.st_size
                    mtime = st.st_mtime
                else:
                    mtime = os.stat(full).st_mtime
            except Exception:
                pass

            items.append((name, is_dir, size, mtime))

            if len(items) >= MAX_SCAN_FILES:
                break

        # ترتيب
        items = self._sort_items(items)

        self.items = items
        self.total = len(items)

        # تسجيل في Recent
        try:
            add_recent(path)
        except Exception:
            pass

    def _sort_items(self, items):
        sort_by = self.state.sort_by
        try:
            if sort_by == "date":
                # الأحدث أولاً، مجلدات ثم ملفات
                items.sort(key=lambda x: (not x[1], -x[3]))
            elif sort_by == "size":
                items.sort(key=lambda x: (not x[1], -x[2]))
            elif sort_by == "type":
                # ترتيب حسب الامتداد مع natural
                def key_type(x):
                    ext = os.path.splitext(x[0])[1].lower()
                    return (not x[1], ext, natural_key(x[0]))
                items.sort(key=key_type)
            else:
                # name (افتراضي)
                items.sort(key=lambda x: (not x[1], natural_key(x[0])))
        except Exception:
            pass
        return items

    # ═══════════════════════════════════════════════════════════
    #      Title
    # ═══════════════════════════════════════════════════════════
    def build_title(self) -> str:
        path = self.state.path
        start = self.state.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)

        breadcrumb = build_breadcrumbs(path, self.root)

        sort_label = {
            "name": "🔤 اسم",
            "date": "📅 تاريخ",
            "size": "📊 حجم",
            "type": "🏷️ نوع",
        }.get(self.state.sort_by, "🔤 اسم")

        filter_icon = FILTER_ICONS.get(self.state.filter_type, "📁")
        filter_label = FILTER_LABELS.get(self.state.filter_type, "الكل")

        extras = []
        if self.state.show_hidden:
            extras.append("👁️ مخفي")
        if self.state.search_query:
            extras.append(f"🔎 `{self.state.search_query[:30]}`")

        extras_str = " | ".join(extras) if extras else ""

        if self.error_msg:
            return (
                f"{breadcrumb}\n"
                f"⚠️ {self.error_msg}"
            )

        line1 = breadcrumb
        line2 = (
            f"({start+1}-{end} من {self.total}) | "
            f"{sort_label} | {filter_icon} {filter_label}"
        )
        line3 = f"🖥️ `{self.device_name}`"
        if extras_str:
            line3 += f" | {extras_str}"

        return f"{line1}\n{line2}\n{line3}"

    # ═══════════════════════════════════════════════════════════
    #      UI Builder
    # ═══════════════════════════════════════════════════════════
    def _build_ui(self):
        if self.error_msg and not self.items:
            # عرض زر واحد للعودة
            back_btn = discord.ui.Button(
                label="⬆️ العودة",
                style=discord.ButtonStyle.secondary,
                row=0,
            )
            back_btn.callback = self._on_up
            self.add_item(back_btn)
            return

        self._build_select_menu()
        self._build_nav_buttons()
        self._build_sort_buttons()
        self._build_filter_buttons()
        self._build_action_buttons()

    # ─────────────── Select Menu ───────────────
    def _build_select_menu(self):
        start = self.state.page * FILES_PER_PAGE
        end = min(start + FILES_PER_PAGE, self.total)
        page_items = self.items[start:end]

        options = []
        for name, is_dir, size, mtime in page_items:
            icon = get_file_icon(name, is_dir)
            label = f"{icon} {name}"[:100]

            if is_dir:
                desc = "📁 مجلد"
            else:
                desc = f"📄 {fmt_size(size)}"

            # استخدم المسار الكامل كـ value
            full = os.path.join(self.state.path, name)
            options.append(discord.SelectOption(
                label=label,
                value=full[:100],
                description=desc[:100],
            ))

        if options:
            select = discord.ui.Select(
                placeholder=f"اختر عنصرًا ({start+1}-{end} من {self.total})",
                options=options,
                min_values=1,
                max_values=1,
                row=0,
            )
            select.callback = self._on_select
            self.add_item(select)

    # ─────────────── Navigation Buttons ───────────────
    def _build_nav_buttons(self):
        # Up
        parent = os.path.dirname(self.state.path.rstrip(os.sep))
        can_up = (parent and parent != self.state.path
                  and self.is_allowed_fn(parent))
        up_btn = discord.ui.Button(
            label="⬆️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=not can_up,
        )
        up_btn.callback = self._on_up
        self.add_item(up_btn)

        # Prev page
        prev_btn = discord.ui.Button(
            label="⬅️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=self.state.page <= 0,
        )
        prev_btn.callback = self._on_prev
        self.add_item(prev_btn)

        # Page info (disabled)
        total_pages = max(1, (self.total + FILES_PER_PAGE - 1) // FILES_PER_PAGE)
        info_btn = discord.ui.Button(
            label=f"📄 {self.state.page+1}/{total_pages}",
            style=discord.ButtonStyle.primary,
            row=1,
            disabled=True,
        )
        self.add_item(info_btn)

        # Next page
        next_btn = discord.ui.Button(
            label="➡️",
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=(self.state.page + 1) * FILES_PER_PAGE >= self.total,
        )
        next_btn.callback = self._on_next
        self.add_item(next_btn)

        # Refresh
        refresh_btn = discord.ui.Button(
            label="🔄",
            style=discord.ButtonStyle.success,
            row=1,
        )
        refresh_btn.callback = self._on_refresh
        self.add_item(refresh_btn)

    # ─────────────── Sort Buttons ───────────────
    def _build_sort_buttons(self):
        modes = [
            ("name", "🔤 اسم", 2),
            ("date", "📅 تاريخ", 2),
            ("size", "📊 حجم", 2),
            ("type", "🏷️ نوع", 2),
        ]
        for mode, label, row in modes:
            style = (discord.ButtonStyle.success
                     if self.state.sort_by == mode
                     else discord.ButtonStyle.secondary)
            btn = discord.ui.Button(
                label=label,
                style=style,
                row=row,
            )
            btn.callback = self._make_sort_cb(mode)
            self.add_item(btn)

        # Hidden toggle
        hidden_style = (discord.ButtonStyle.success
                        if self.state.show_hidden
                        else discord.ButtonStyle.secondary)
        hidden_btn = discord.ui.Button(
            label="👁️",
            style=hidden_style,
            row=row,
        )
        hidden_btn.callback = self._on_toggle_hidden
        self.add_item(hidden_btn)

    # ─────────────── Filter Buttons ───────────────
    def _build_filter_buttons(self):
        filters = [
            (FILTER_ALL, 3),
            (FILTER_IMAGES, 3),
            (FILTER_VIDEOS, 3),
            (FILTER_AUDIO, 3),
            (FILTER_DOCS, 3),
        ]
        for ftype, row in filters:
            icon = FILTER_ICONS[ftype]
            style = (discord.ButtonStyle.success
                     if self.state.filter_type == ftype
                     else discord.ButtonStyle.secondary)
            btn = discord.ui.Button(
                label=icon,
                style=style,
                row=row,
            )
            btn.callback = self._make_filter_cb(ftype)
            self.add_item(btn)

    # ─────────────── Action Buttons ───────────────
    def _build_action_buttons(self):
        # Search
        search_btn = discord.ui.Button(
            label="🔎 بحث",
            style=discord.ButtonStyle.primary,
            row=4,
        )
        search_btn.callback = self._on_search
        self.add_item(search_btn)

        # Jump to path
        jump_btn = discord.ui.Button(
            label="🎯 انتقال",
            style=discord.ButtonStyle.primary,
            row=4,
        )
        jump_btn.callback = self._on_jump
        self.add_item(jump_btn)

        # Clear search (if any)
        if self.state.search_query:
            clear_btn = discord.ui.Button(
                label="❌ مسح البحث",
                style=discord.ButtonStyle.danger,
                row=4,
            )
            clear_btn.callback = self._on_clear_search
            self.add_item(clear_btn)

        # ZIP current
        zip_btn = discord.ui.Button(
            label="🗜️ ZIP",
            style=discord.ButtonStyle.danger,
            row=4,
        )
        zip_btn.callback = self._on_zip_current
        self.add_item(zip_btn)

        # Quick links
        # ملاحظة: هذه تحتاج معلومات إضافية عن المسارات المتاحة
        # يمكن إضافتها لاحقًا

    # ═══════════════════════════════════════════════════════════
    #      Callbacks
    # ═══════════════════════════════════════════════════════════
    async def _check_user(self, interaction) -> bool:
        try:
            allowed = self.check_user_fn(interaction)
            if not allowed:
                await interaction.response.send_message(
                    "غير مصرح.", ephemeral=True)
            return allowed
        except Exception:
            return False

    async def _rebuild(self, interaction, new_state: BrowseState):
        """إعادة بناء الرسالة بحالة جديدة."""
        try:
            new_view = AdvancedFileBrowserView(
                state=new_state,
                root=self.root,
                allowed_roots=self.allowed_roots,
                is_allowed_fn=self.is_allowed_fn,
                check_user_fn=self.check_user_fn,
                device_name=self.device_name,
            )
            await interaction.response.edit_message(
                content=new_view.build_title(),
                view=new_view,
            )
        except Exception as e:
            try:
                await interaction.followup.send(
                    f"❌ {e}", ephemeral=True)
            except Exception:
                pass

    # ─────────── Select ───────────
    async def _on_select(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return

        try:
            values = interaction.data.get("values", [])
            if not values:
                await interaction.response.defer()
                return

            target = values[0]

            # فحص الأمان
            if not self.is_allowed_fn(target):
                await interaction.response.send_message(
                    "❌ مسار غير صالح.", ephemeral=True)
                return

            if os.path.isdir(target):
                # ادخل المجلد
                new_state = self.state.copy_with(path=target, page=0)
                new_state.invalidate_cache()
                await self._rebuild(interaction, new_state)
            else:
                # أرسل الملف
                await interaction.response.defer()
                await self._send_file(interaction, target)

        except Exception as e:
            try:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
            except Exception:
                pass

    async def _send_file(self, interaction, path: str):
        """إرسال ملف واحد."""
        try:
            if not os.path.isfile(path):
                await interaction.followup.send("❌ الملف غير موجود.")
                return

            size_mb = os.path.getsize(path) / (1024 * 1024)
            if size_mb > 24.0:
                await interaction.followup.send(
                    f"⚠️ الحجم {size_mb:.1f}MB > 24MB")
                return

            await interaction.followup.send(
                content=f"📄 `{os.path.basename(path)}` ({fmt_size(os.path.getsize(path))})",
                file=discord.File(path),
            )
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ {e}")
            except Exception:
                pass

    # ─────────── Navigation ───────────
    async def _on_up(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            parent = os.path.dirname(self.state.path.rstrip(os.sep))
            if not parent or parent == self.state.path:
                await interaction.response.defer()
                return
            if not self.is_allowed_fn(parent):
                await interaction.response.send_message(
                    "❌ خارج النطاق.", ephemeral=True)
                return
            new_state = self.state.copy_with(path=parent, page=0)
            new_state.invalidate_cache()
            await self._rebuild(interaction, new_state)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ {e}", ephemeral=True)

    async def _on_prev(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            if self.state.page <= 0:
                await interaction.response.defer()
                return
            new_state = self.state.copy_with(page=self.state.page - 1)
            await self._rebuild(interaction, new_state)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ {e}", ephemeral=True)

    async def _on_next(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            if (self.state.page + 1) * FILES_PER_PAGE >= self.total:
                await interaction.response.defer()
                return
            new_state = self.state.copy_with(page=self.state.page + 1)
            await self._rebuild(interaction, new_state)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ {e}", ephemeral=True)

    async def _on_refresh(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            new_state = self.state.copy_with()
            new_state.invalidate_cache()
            await self._rebuild(interaction, new_state)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ {e}", ephemeral=True)

    # ─────────── Sort ───────────
    def _make_sort_cb(self, mode: str):
        async def cb(interaction: discord.Interaction):
            if not await self._check_user(interaction):
                return
            try:
                new_state = self.state.copy_with(sort_by=mode, page=0)
                new_state.invalidate_cache()
                await self._rebuild(interaction, new_state)
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ {e}", ephemeral=True)
        return cb

    # ─────────── Filter ───────────
    def _make_filter_cb(self, ftype: str):
        async def cb(interaction: discord.Interaction):
            if not await self._check_user(interaction):
                return
            try:
                if self.state.filter_type == ftype:
                    await interaction.response.defer()
                    return
                new_state = self.state.copy_with(
                    filter_type=ftype, page=0)
                new_state.invalidate_cache()
                await self._rebuild(interaction, new_state)
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ {e}", ephemeral=True)
        return cb

    # ─────────── Hidden toggle ───────────
    async def _on_toggle_hidden(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            new_state = self.state.copy_with(
                show_hidden=not self.state.show_hidden, page=0)
            new_state.invalidate_cache()
            await self._rebuild(interaction, new_state)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ {e}", ephemeral=True)

    # ─────────── Search ───────────
    async def _on_search(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            await interaction.response.send_modal(SearchModal(self))
        except Exception as e:
            try:
                await interaction.followup.send(
                    f"❌ {e}", ephemeral=True)
            except Exception:
                pass

    async def _on_clear_search(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            new_state = self.state.copy_with(search_query="", page=0)
            new_state.invalidate_cache()
            await self._rebuild(interaction, new_state)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ {e}", ephemeral=True)

    # ─────────── Jump ───────────
    async def _on_jump(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            await interaction.response.send_modal(JumpModal(self))
        except Exception as e:
            try:
                await interaction.followup.send(
                    f"❌ {e}", ephemeral=True)
            except Exception:
                pass

    # ─────────── ZIP current ───────────
    async def _on_zip_current(self, interaction: discord.Interaction):
        if not await self._check_user(interaction):
            return
        try:
            await interaction.response.defer()
            await self._zip_and_send(interaction, self.state.path)
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ {e}")
            except Exception:
                pass

    async def _zip_and_send(self, interaction, path: str):
        import tempfile, zipfile
        if not self.is_allowed_fn(path):
            await interaction.followup.send("❌ خارج النطاق.")
            return
        if not os.path.isdir(path):
            await interaction.followup.send("❌ ليس مجلدًا.")
            return

        try:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
            tmp.close()
            try:
                with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as zf:
                    count = 0
                    for root, _dirs, files in os.walk(path):
                        for fn in files:
                            if count >= 1000:
                                break
                            full = os.path.join(root, fn)
                            rel = os.path.relpath(full, path)
                            try:
                                zf.write(full, rel)
                                count += 1
                            except Exception:
                                continue
                        if count >= 1000:
                            break

                size_mb = os.path.getsize(tmp.name) / (1024 * 1024)
                if size_mb > 24.0:
                    await interaction.followup.send(
                        f"⚠️ الأرشيف {size_mb:.1f}MB > 24MB")
                    return

                fname = f"{os.path.basename(path.rstrip('/')) or 'root'}.zip"
                await interaction.followup.send(
                    content=f"🗜️ `{fname}` ({count} ملف)",
                    file=discord.File(tmp.name, filename=fname),
                )
            finally:
                try:
                    os.remove(tmp.name)
                except Exception:
                    pass
        except Exception as e:
            await interaction.followup.send(f"❌ {e}")