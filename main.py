"""
╔══════════════════════════════════════════════════════════════════╗
║              JvRemotPy — Entry Point (main.py)                   ║
║                                                                  ║
║  Thin wrapper that delegates to hawkmoth_bot.py.                 ║
║  Provides a stable interface for BotService.java (Java).         ║
║                                                                  ║
║  المميزات:                                                       ║
║    • واجهة ثابتة للـ Java                                        ║
║    • تفويض كامل إلى hawkmoth_bot                                 ║
║    • لا يوجد توكن مدمج                                           ║
║    • Thread-safe                                                 ║
║    • Lazy loading للمكونات                                       ║
║    • Health check شامل                                          ║
║    • رسائل خطأ تفصيلية                                           ║
║    • Diagnose API                                                ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import json
import platform
import traceback
import threading
from typing import Optional, Dict, Any, List

# ═══════════════════════════════════════════════════════════════════
#                       Version
# ═══════════════════════════════════════════════════════════════════
MAIN_VERSION = "8.0.0"
FALLBACK_BOT_VERSION = "unknown"

# ═══════════════════════════════════════════════════════════════════
#                       Path Setup
# ═══════════════════════════════════════════════════════════════════
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# إضافة python_scripts (المسار الذي يُنزّل فيه SyncManager)
try:
    # ملفات التطبيق على أندرويد
    _ANDROID_FILES = None
    try:
        from java import jclass
        ActivityThread = jclass("android.app.ActivityThread")
        app = ActivityThread.currentApplication()
        if app:
            _ANDROID_FILES = app.getFilesDir().getAbsolutePath()
    except Exception:
        pass

    if _ANDROID_FILES:
        _SCRIPTS_DIR = os.path.join(_ANDROID_FILES, "python_scripts")
        if os.path.isdir(_SCRIPTS_DIR) and _SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, _SCRIPTS_DIR)
except Exception:
    pass


# ═══════════════════════════════════════════════════════════════════
#                       Lazy Import hawkmoth_bot
# ═══════════════════════════════════════════════════════════════════
_hawkmoth = None
_hawkmoth_import_error: Optional[str] = None
_hawkmoth_import_attempted = False
_import_lock = threading.RLock()


def _try_import_hawkmoth() -> bool:
    """
    محاولة استيراد hawkmoth_bot (lazy).
    تُرجع True عند النجاح.
    """
    global _hawkmoth, _hawkmoth_import_error, _hawkmoth_import_attempted

    with _import_lock:
        if _hawkmoth is not None:
            return True
        if _hawkmoth_import_attempted and _hawkmoth is None:
            # فشل سابقًا — أعد المحاولة فقط إذا مر وقت كافٍ
            return False

        _hawkmoth_import_attempted = True
        try:
            import hawkmoth_bot as _h
            _hawkmoth = _h
            _hawkmoth_import_error = None
            print(f"✅ hawkmoth_bot loaded (v{getattr(_h, 'VERSION', '?')})",
                  flush=True)
            return True
        except ImportError as e:
            _hawkmoth_import_error = f"ImportError: {e}"
            print(f"⚠️ hawkmoth_bot import failed: {e}", flush=True)
        except Exception as e:
            _hawkmoth_import_error = f"{type(e).__name__}: {e}"
            print(f"❌ hawkmoth_bot unexpected error: {e}", flush=True)
            try:
                print(traceback.format_exc(), flush=True)
            except Exception:
                pass

        return False


def _ensure_hawkmoth() -> bool:
    """يتأكد من تحميل hawkmoth_bot."""
    if _hawkmoth is not None:
        return True
    return _try_import_hawkmoth()


# ═══════════════════════════════════════════════════════════════════
#                       Version API
# ═══════════════════════════════════════════════════════════════════
def get_version() -> str:
    """يُرجع إصدار البوت (من hawkmoth_bot إن أمكن)."""
    if _ensure_hawkmoth():
        try:
            v = _hawkmoth.get_version()
            if v:
                return str(v)
        except Exception:
            pass
    return FALLBACK_BOT_VERSION


def get_main_version() -> str:
    """إصدار main.py نفسه."""
    return MAIN_VERSION


def get_full_version() -> Dict[str, str]:
    """كل الإصدارات في dict."""
    return {
        "main": MAIN_VERSION,
        "bot": get_version(),
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }


def get_full_version_json() -> str:
    """كل الإصدارات كـ JSON."""
    try:
        return json.dumps(get_full_version(), ensure_ascii=False)
    except Exception:
        return "{}"


# ═══════════════════════════════════════════════════════════════════
#                       Run (اختبار بسيط)
# ═══════════════════════════════════════════════════════════════════
def run(message: str = "") -> str:
    """دالة اختبار بسيطة (بدون Discord)."""
    return (
        f"🎉 JvRemotPy v{get_version()} يعمل!\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"📱 Platform: {sys.platform}\n"
        f"💬 رسالتك: {message}"
    )


# ═══════════════════════════════════════════════════════════════════
#                       run_bot (نقطة الدخول الرئيسية)
# ═══════════════════════════════════════════════════════════════════
_run_bot_lock = threading.RLock()


def run_bot(
    token: Optional[str] = None,
    prefix: str = "!",
    owner_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    allowed_user_id: Optional[int] = None,
    enable_message_content: bool = True,
    enable_members: bool = False,
    enable_presences: bool = False,
    enable_all_intents: bool = False,
) -> str:
    """
    ⭐ نقطة الدخول الرئيسية — يستدعيها BotService من Java.

    Args:
        token: توكن البوت (إلزامي).
        prefix: بادئة الأوامر.
        owner_id: معرف المالك.
        guild_id: معرف السيرفر.
        allowed_user_id: معرف المستخدم المسموح.
        enable_message_content: تفعيل قراءة محتوى الرسائل.
        enable_members: تفعيل intent الأعضاء.
        enable_presences: تفعيل intent الحضور.
        enable_all_intents: تفعيل كل الـ intents.

    Returns:
        رسالة نصية بالنتيجة.
    """
    log_start = time.time()

    # 1. فحص المكوّن
    if not _ensure_hawkmoth():
        return (
            f"❌ hawkmoth_bot غير متوفر\n"
            f"السبب: {_hawkmoth_import_error or 'unknown'}"
        )

    # 2. فحص التوكن
    if not token:
        return "❌ التوكن فارغ"

    token = str(token).strip()
    if len(token) < 20:
        return "❌ التوكن قصير جدًا"

    # 3. قفل لمنع التشغيل المتزامن
    with _run_bot_lock:
        try:
            print(f"▶️ run_bot() starting | token_len={len(token)}", flush=True)

            # استدعاء hawkmoth_bot.start_bot مع كل المعاملات
            result = _hawkmoth.start_bot(
                token=token,
                prefix=str(prefix or "!"),
                owner_id=int(owner_id) if owner_id else None,
                guild_id=int(guild_id) if guild_id else None,
                allowed_user_id=int(allowed_user_id) if allowed_user_id else None,
                enable_message_content=bool(enable_message_content),
                enable_members=bool(enable_members),
                enable_presences=bool(enable_presences),
                enable_all_intents=bool(enable_all_intents),
            )

            elapsed = time.time() - log_start
            result_str = str(result) if result is not None else "(null)"
            print(f"⏹️ run_bot() ended after {elapsed:.2f}s | result={result_str[:200]}",
                  flush=True)

            return result_str

        except AttributeError as e:
            err = f"❌ hawkmoth_bot.start_bot غير موجودة: {e}"
            print(err, flush=True)
            return err

        except TypeError as e:
            err = f"❌ خطأ في معاملات start_bot: {e}"
            print(err, flush=True)
            return err

        except Exception as e:
            err = f"❌ فشل تشغيل البوت: {type(e).__name__}: {e}"
            print(err, flush=True)
            try:
                print(traceback.format_exc(), flush=True)
            except Exception:
                pass
            return err


# ═══════════════════════════════════════════════════════════════════
#                       stop_bot
# ═══════════════════════════════════════════════════════════════════
def stop_bot() -> str:
    """إيقاف البوت — يُستدعى من Java."""
    if not _ensure_hawkmoth():
        return "⚠️ hawkmoth_bot غير متوفر"
    try:
        return str(_hawkmoth.stop_bot())
    except Exception as e:
        return f"❌ فشل الإيقاف: {e}"


# ═══════════════════════════════════════════════════════════════════
#                       Status APIs
# ═══════════════════════════════════════════════════════════════════
def get_bot_status() -> Dict[str, Any]:
    """حالة البوت — تُستدعى من Java."""
    if not _ensure_hawkmoth():
        return {
            "running": False,
            "reason": "hawkmoth_not_loaded",
            "error": _hawkmoth_import_error,
        }
    try:
        status = _hawkmoth.get_bot_status()
        if isinstance(status, dict):
            return status
        return {"running": False, "reason": "invalid_status"}
    except Exception as e:
        return {"running": False, "reason": str(e)}


def get_bot_status_json() -> str:
    """حالة البوت كـ JSON."""
    try:
        return json.dumps(get_bot_status(), ensure_ascii=False)
    except Exception:
        return "{}"


def is_contacts_bridge_ready() -> bool:
    """هل ContactsBridge جاهز؟"""
    if not _ensure_hawkmoth():
        return False
    try:
        return bool(_hawkmoth.is_contacts_bridge_ready())
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       Health Check
# ═══════════════════════════════════════════════════════════════════
def health_check() -> Dict[str, Any]:
    """فحص شامل لجاهزية التطبيق."""
    result: Dict[str, Any] = {
        "main_version": MAIN_VERSION,
        "timestamp": int(time.time()),
        "python": {
            "version": sys.version.split()[0],
            "platform": sys.platform,
            "executable": sys.executable,
        },
        "paths": {
            "script_dir": _SCRIPT_DIR,
            "script_dir_exists": os.path.isdir(_SCRIPT_DIR),
            "sys_path_len": len(sys.path),
        },
        "modules": {},
        "errors": [],
    }

    # فحص الملفات المهمة
    files_to_check = ["main.py", "hawkmoth_bot.py", "bridge.py", "file_browser.py"]
    result["files"] = {}
    for fname in files_to_check:
        fpath = os.path.join(_SCRIPT_DIR, fname)
        result["files"][fname] = {
            "exists": os.path.isfile(fpath),
            "size": os.path.getsize(fpath) if os.path.isfile(fpath) else 0,
        }

    # فحص الاستيرادات
    try:
        result["modules"]["hawkmoth_bot"] = _ensure_hawkmoth()
    except Exception as e:
        result["modules"]["hawkmoth_bot"] = False
        result["errors"].append(f"hawkmoth_bot: {e}")

    try:
        import bridge
        result["modules"]["bridge"] = True
        result["bridge_has_get_accounts"] = hasattr(bridge, "get_accounts")
        result["bridge_has_get_call_log"] = hasattr(bridge, "get_call_log")
        result["bridge_has_get_phone_info"] = hasattr(bridge, "get_phone_info")
        result["bridge_has_is_audio_recording"] = hasattr(bridge, "is_audio_recording")
    except Exception as e:
        result["modules"]["bridge"] = False
        result["errors"].append(f"bridge: {e}")

    try:
        import file_browser
        result["modules"]["file_browser"] = True
        result["file_browser_has_advanced"] = hasattr(
            file_browser, "AdvancedFileBrowserView")
    except Exception as e:
        result["modules"]["file_browser"] = False
        result["errors"].append(f"file_browser: {e}")

    result["healthy"] = (
        result["modules"].get("hawkmoth_bot", False)
        and result["modules"].get("bridge", False)
        and not result["errors"]
    )

    return result


def health_check_json() -> str:
    """فحص شامل كـ JSON."""
    try:
        return json.dumps(health_check(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def diagnose() -> Dict[str, Any]:
    """
    تشخيص كامل للتطبيق.
    يشمل: الإصدارات، الصلاحيات، الميزات.
    """
    result: Dict[str, Any] = {
        "versions": get_full_version(),
        "health": health_check(),
    }

    # محاولة الحصول على تشخيص bridge
    try:
        import bridge
        if hasattr(bridge, "diagnose"):
            diag_raw = bridge.diagnose()
            try:
                result["bridge_diagnose"] = json.loads(diag_raw)
            except Exception:
                result["bridge_diagnose"] = diag_raw
    except Exception as e:
        result["bridge_diagnose_error"] = str(e)

    # محاولة الحصول على حالة hawkmoth_bot
    try:
        if _ensure_hawkmoth():
            result["bot_status"] = get_bot_status()
    except Exception as e:
        result["bot_status_error"] = str(e)

    return result


def diagnose_json() -> str:
    """تشخيص كامل كـ JSON."""
    try:
        return json.dumps(diagnose(), ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════
#                       Module Info
# ═══════════════════════════════════════════════════════════════════
def get_module_info() -> Dict[str, Any]:
    """معلومات عن الوحدات المتوفرة."""
    return {
        "main": {
            "version": MAIN_VERSION,
            "script_dir": _SCRIPT_DIR,
        },
        "hawkmoth_bot": {
            "loaded": _hawkmoth is not None,
            "version": get_version() if _hawkmoth else None,
            "import_error": _hawkmoth_import_error,
        },
        "sys_path": list(sys.path[:5]),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }


def get_module_info_json() -> str:
    """معلومات الوحدات كـ JSON."""
    try:
        return json.dumps(get_module_info(), ensure_ascii=False)
    except Exception:
        return "{}"


# ═══════════════════════════════════════════════════════════════════
#                       Force Reload (لتحديث)
# ═══════════════════════════════════════════════════════════════════
def reload_hawkmoth() -> str:
    """
    إعادة تحميل hawkmoth_bot (للاستخدام بعد تحديث الملفات).
    """
    global _hawkmoth, _hawkmoth_import_error, _hawkmoth_import_attempted

    with _import_lock:
        try:
            # إزالة الوحدة من sys.modules
            if "hawkmoth_bot" in sys.modules:
                del sys.modules["hawkmoth_bot"]
            if "bridge" in sys.modules:
                del sys.modules["bridge"]
            if "file_browser" in sys.modules:
                del sys.modules["file_browser"]

            # إعادة تعيين الحالة
            _hawkmoth = None
            _hawkmoth_import_error = None
            _hawkmoth_import_attempted = False

            # إعادة الاستيراد
            if _try_import_hawkmoth():
                return f"✅ hawkmoth_bot reloaded (v{get_version()})"
            return f"❌ فشل إعادة التحميل: {_hawkmoth_import_error}"

        except Exception as e:
            return f"❌ خطأ: {e}"


# ═══════════════════════════════════════════════════════════════════
#                       Compatibility Aliases
# ═══════════════════════════════════════════════════════════════════
# أسماء بديلة للتوافق مع إصدارات قديمة من Java
def get_status() -> Dict[str, Any]:
    return get_bot_status()


def get_status_json() -> str:
    return get_bot_status_json()


# ═══════════════════════════════════════════════════════════════════
#                       Local Test
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print(f"✅ main.py v{MAIN_VERSION}")
    print(f"🐍 Python {sys.version.split()[0]}")
    print(f"📁 Script dir: {_SCRIPT_DIR}")
    print("=" * 60)

    # فحص الصحة
    print("\n🏥 Health Check:")
    print(health_check_json())

    # معلومات الوحدات
    print("\n📦 Module Info:")
    print(get_module_info_json())

    # اختبار run
    print("\n🧪 Testing run():")
    print(run("اختبار محلي"))
