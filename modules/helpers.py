"""
╔══════════════════════════════════════════════════════════════════╗
║                    JvRemotPy — Helpers Module                    ║
║                                                                  ║
║  دوال مساعدة عامة يستخدمها hawkmoth_bot.py و main.py            ║
║                                                                  ║
║  الميزات:                                                        ║
║    • Thread-safe                                                 ║
║    • Type hints كاملة                                            ║
║    • معالجة أخطاء شاملة                                          ║
║    • بدون dependencies خارجية                                    ║
║    • متوافق مع Python 3.8+                                       ║
╚══════════════════════════════════════════════════════════════════╝
"""

import os
import re
import json
import time
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Dict, List, Union, Tuple


__version__ = "2.0.0"


# ═══════════════════════════════════════════════════════════════════
#                       TIME UTILITIES
# ═══════════════════════════════════════════════════════════════════

def get_timestamp() -> str:
    """يُرجع الوقت الحالي بصيغة ISO 8601 (UTC)."""
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return datetime.now().isoformat()


def get_local_timestamp() -> str:
    """يُرجع الوقت المحلي بصيغة ISO 8601."""
    try:
        return datetime.now().isoformat()
    except Exception:
        return ""


def get_unix_time() -> int:
    """يُرجع Unix timestamp (ثواني)."""
    try:
        return int(time.time())
    except Exception:
        return 0


def format_duration(seconds: Union[int, float]) -> str:
    """
    يحوّل الثواني إلى نص مقروء.
    مثال: 3665 → "1h 1m 5s"
    """
    try:
        seconds = int(seconds)
    except (ValueError, TypeError):
        return "0s"

    if seconds < 0:
        return "0s"

    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if minutes: parts.append(f"{minutes}m")
    parts.append(f"{secs}s")

    return " ".join(parts)


def parse_duration(text: str) -> int:
    """
    يحوّل نص مثل "1h 30m" إلى ثواني.
    يدعم: s, m, h, d
    """
    if not text:
        return 0

    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    total = 0

    try:
        text = text.lower().strip()
        matches = re.findall(r'(\d+)\s*([smhd])', text)
        for value, unit in matches:
            total += int(value) * units.get(unit, 0)
    except Exception:
        pass

    return total


def is_older_than(timestamp: float, seconds: int) -> bool:
    """هل الطابع الزمني أقدم من N ثانية؟"""
    try:
        return (time.time() - float(timestamp)) > seconds
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       NUMBER UTILITIES
# ═══════════════════════════════════════════════════════════════════

def safe_int(value: Any, default: int = 0) -> int:
    """يحوّل القيمة إلى int بأمان."""
    if value is None:
        return default
    try:
        if isinstance(value, bool):
            return int(value)
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """يحوّل القيمة إلى float بأمان."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_bool(value: Any, default: bool = False) -> bool:
    """يحوّل القيمة إلى bool بأمان."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "y", "t")
    return default


def clamp(value: Union[int, float], minimum: Union[int, float], maximum: Union[int, float]) -> Union[int, float]:
    """يحدد القيمة بين حدين."""
    try:
        if value < minimum:
            return minimum
        if value > maximum:
            return maximum
        return value
    except Exception:
        return minimum


def format_size(n: Union[int, float], precision: int = 1) -> str:
    """
    يحوّل الحجم بالبايت إلى نص مقروء.
    مثال: 1536 → "1.5KB"
    """
    try:
        n = float(n)
    except (ValueError, TypeError):
        return "?"

    if n < 0:
        return "?"

    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if n < 1024:
            return f"{n:.{precision}f}{unit}"
        n /= 1024

    return f"{n:.{precision}f}PB"


def format_number(n: Union[int, float]) -> str:
    """يُنسّق الأرقام بفواصل. مثال: 1234567 → "1,234,567"."""
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)


def percentage(part: Union[int, float], total: Union[int, float]) -> float:
    """يحسب النسبة المئوية بأمان."""
    try:
        if total == 0:
            return 0.0
        return (part / total) * 100.0
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════
#                       STRING UTILITIES
# ═══════════════════════════════════════════════════════════════════

def truncate(text: Optional[str], max_length: int = 100, suffix: str = "...") -> str:
    """يقصّر النص مع إضافة لاحقة."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def safe_str(value: Any, default: str = "") -> str:
    """يحوّل القيمة إلى str بأمان."""
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """
    ينظّف اسم الملف من الأحرف غير الآمنة.
    """
    if not name:
        return "unnamed"
    try:
        # إزالة الأحرف غير المسموحة
        sanitized = re.sub(r'[^\w\-_. ]', '_', name)
        # إزالة المسافات المتكررة
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        # قص الطول
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        return sanitized or "unnamed"
    except Exception:
        return "unnamed"


def slugify(text: str) -> str:
    """يحوّل النص إلى slug (lowercase + hyphens)."""
    if not text:
        return ""
    try:
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[\s_]+', '-', text)
        text = re.sub(r'-+', '-', text)
        return text.strip('-')
    except Exception:
        return ""


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """
    يرجع الكلمة بصيغة صحيحة حسب العدد.
    مثال: pluralize(1, "file") → "file"
          pluralize(2, "file") → "files"
    """
    if plural is None:
        plural = singular + "s"
    return singular if count == 1 else plural


# ═══════════════════════════════════════════════════════════════════
#                       DICT / JSON UTILITIES
# ═══════════════════════════════════════════════════════════════════

def format_result(data: Any) -> str:
    """
    يُنسّق dict أو قيمة للعرض.
    """
    if data is None:
        return "—"

    if isinstance(data, dict):
        if not data:
            return "{}"
        try:
            lines = [f"{k}: {v}" for k, v in data.items()]
            return "\n".join(lines)
        except Exception:
            return str(data)

    if isinstance(data, (list, tuple)):
        try:
            return "\n".join(f"• {item}" for item in data)
        except Exception:
            return str(data)

    return str(data)


def safe_get(data: Optional[Dict], key: str, default: Any = None) -> Any:
    """يحصل على قيمة من dict بأمان."""
    if not isinstance(data, dict):
        return default
    return data.get(key, default)


def safe_json_loads(text: Optional[str], default: Any = None) -> Any:
    """يُحمّل JSON بأمان."""
    if not text:
        return default if default is not None else {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def safe_json_dumps(data: Any, indent: Optional[int] = None) -> str:
    """يُصدّر JSON بأمان."""
    try:
        return json.dumps(data, ensure_ascii=False, indent=indent, default=str)
    except Exception:
        return "{}"


def deep_merge(base: Dict, override: Dict) -> Dict:
    """يدمج dict-ين بشكل عميق."""
    if not isinstance(base, dict):
        return override if isinstance(override, dict) else {}
    if not isinstance(override, dict):
        return base

    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def flatten_dict(data: Dict, parent_key: str = "", sep: str = ".") -> Dict:
    """يُسطّح dict متداخل. مثال: {a: {b: 1}} → {"a.b": 1}."""
    items = []
    try:
        for key, value in data.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else key
            if isinstance(value, dict):
                items.extend(flatten_dict(value, new_key, sep).items())
            else:
                items.append((new_key, value))
    except Exception:
        pass
    return dict(items)


# ═══════════════════════════════════════════════════════════════════
#                       FILE / PATH UTILITIES
# ═══════════════════════════════════════════════════════════════════

def get_extension(path: str) -> str:
    """يُرجع امتداد الملف بدون النقطة (lowercase)."""
    if not path:
        return ""
    try:
        return os.path.splitext(path)[1].lower().lstrip(".")
    except Exception:
        return ""


def get_filename(path: str) -> str:
    """يُرجع اسم الملف بدون المسار."""
    if not path:
        return ""
    try:
        return os.path.basename(path)
    except Exception:
        return ""


def get_parent_dir(path: str) -> str:
    """يُرجع المجلد الأب."""
    if not path:
        return ""
    try:
        return os.path.dirname(path)
    except Exception:
        return ""


def file_exists(path: str) -> bool:
    """هل الملف موجود؟"""
    try:
        return os.path.isfile(path)
    except Exception:
        return False


def dir_exists(path: str) -> bool:
    """هل المجلد موجود؟"""
    try:
        return os.path.isdir(path)
    except Exception:
        return False


def get_file_size(path: str) -> int:
    """يُرجع حجم الملف بالبايت (أو 0 عند الفشل)."""
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def ensure_dir(path: str) -> bool:
    """ينشئ المجلد إن لم يكن موجودًا."""
    try:
        if not path:
            return False
        os.makedirs(path, exist_ok=True)
        return True
    except Exception:
        return False


def is_safe_path(path: str, allowed_roots: List[str]) -> bool:
    """
    هل المسار داخل إحدى الجذور المسموحة؟
    (يمنع directory traversal)
    """
    if not path or not allowed_roots:
        return False
    try:
        real = os.path.realpath(path)
        for root in allowed_roots:
            rr = os.path.realpath(root)
            if real == rr or real.startswith(rr + os.sep):
                return True
        return False
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       HASH / CRYPTO UTILITIES
# ═══════════════════════════════════════════════════════════════════

def md5_hash(text: str) -> str:
    """يحسب MD5 hash للنص."""
    try:
        return hashlib.md5(text.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def sha256_hash(text: str) -> str:
    """يحسب SHA256 hash للنص."""
    try:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    except Exception:
        return ""


def file_md5(path: str, chunk_size: int = 8192) -> str:
    """يحسب MD5 hash لملف."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def short_hash(text: str, length: int = 8) -> str:
    """hash قصير للاستخدام في مفاتيح cache."""
    return sha256_hash(text)[:length]


# ═══════════════════════════════════════════════════════════════════
#                       THREAD-SAFE COUNTER
# ═══════════════════════════════════════════════════════════════════

class Counter:
    """عدّاد thread-safe."""

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()

    def increment(self, amount: int = 1) -> int:
        with self._lock:
            self._value += amount
            return self._value

    def decrement(self, amount: int = 1) -> int:
        with self._lock:
            self._value -= amount
            return self._value

    def get(self) -> int:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    def set(self, value: int) -> None:
        with self._lock:
            self._value = value


# ═══════════════════════════════════════════════════════════════════
#                       STATUS / RESULT HELPERS
# ═══════════════════════════════════════════════════════════════════

def ok(message: str = "OK", **extra) -> str:
    """يرجع رسالة نجاح موحّدة."""
    result = {"status": "ok", "message": message}
    if extra:
        result.update(extra)
    return safe_json_dumps(result)


def error(message: str = "Error", **extra) -> str:
    """يرجع رسالة خطأ موحّدة."""
    result = {"status": "error", "message": message}
    if extra:
        result.update(extra)
    return safe_json_dumps(result)


def success_text(message: str = "") -> str:
    """نص نجاح مع أيقونة."""
    return f"✅ {message}" if message else "✅"


def error_text(message: str = "") -> str:
    """نص خطأ مع أيقونة."""
    return f"❌ {message}" if message else "❌"


def warning_text(message: str = "") -> str:
    """نص تحذير مع أيقونة."""
    return f"⚠️ {message}" if message else "⚠️"


def info_text(message: str = "") -> str:
    """نص معلومة مع أيقونة."""
    return f"ℹ️ {message}" if message else "ℹ️"


# ═══════════════════════════════════════════════════════════════════
#                       LIST / SEQUENCE UTILITIES
# ═══════════════════════════════════════════════════════════════════

def chunk_list(items: List, chunk_size: int) -> List[List]:
    """يقسّم قائمة إلى أجزاء."""
    if not items or chunk_size <= 0:
        return []
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def unique_list(items: List) -> List:
    """يزيل التكرار مع الحفاظ على الترتيب."""
    seen = set()
    result = []
    for item in items:
        try:
            if item not in seen:
                seen.add(item)
                result.append(item)
        except TypeError:
            # unhashable
            if item not in result:
                result.append(item)
    return result


def safe_first(items: List, default: Any = None) -> Any:
    """يُرجع أول عنصر بأمان."""
    if not items:
        return default
    try:
        return items[0]
    except (IndexError, TypeError):
        return default


# ═══════════════════════════════════════════════════════════════════
#                       EXPORTS
# ═══════════════════════════════════════════════════════════════════

__all__ = [
    # Version
    "__version__",
    # Time
    "get_timestamp", "get_local_timestamp", "get_unix_time",
    "format_duration", "parse_duration", "is_older_than",
    # Numbers
    "safe_int", "safe_float", "safe_bool", "clamp",
    "format_size", "format_number", "percentage",
    # Strings
    "truncate", "safe_str", "sanitize_filename", "slugify", "pluralize",
    # Dict / JSON
    "format_result", "safe_get", "safe_json_loads", "safe_json_dumps",
    "deep_merge", "flatten_dict",
    # Files
    "get_extension", "get_filename", "get_parent_dir",
    "file_exists", "dir_exists", "get_file_size", "ensure_dir", "is_safe_path",
    # Hash
    "md5_hash", "sha256_hash", "file_md5", "short_hash",
    # Classes
    "Counter",
    # Status
    "ok", "error", "success_text", "error_text", "warning_text", "info_text",
    # Lists
    "chunk_list", "unique_list", "safe_first",
]
