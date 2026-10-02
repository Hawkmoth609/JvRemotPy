"""
╔══════════════════════════════════════════════════════════════════╗
║                     JvRemotPy — Entry Point v16.0               ║
║                                                                  ║
║  Thin wrapper delegating to hawkmoth_bot.py.                     ║
║  Stable interface for BotService.java.                           ║
║                                                                  ║
║  v16.0 Changes:                                                  ║
║    • cloud_agent integration                                     ║
║    • Auto set_context for bridge + cloud_agent                  ║
║    • device_id parameter support                                 ║
║    • Improved error handling                                     ║
║    • Health check API                                            ║
║    • Backward compatible 100%                                    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import json
import platform
import traceback
import threading
from typing import Optional, Dict, Any

# ═══════════════════════════════════════════════════════════════════
#                       Version
# ═══════════════════════════════════════════════════════════════════

MAIN_VERSION = "16.0.0"

# ═══════════════════════════════════════════════════════════════════
#                       Path Setup
# ═══════════════════════════════════════════════════════════════════

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


# ═══════════════════════════════════════════════════════════════════
#                       Lazy Imports (with error capture)
# ═══════════════════════════════════════════════════════════════════

_hawkmoth = None
_hawkmoth_import_error: Optional[str] = None
_import_lock = threading.RLock()
_import_attempted = False


def _try_import_hawkmoth() -> bool:
    """محاولة استيراد hawkmoth_bot (مرة واحدة)."""
    global _hawkmoth, _hawkmoth_import_error, _import_attempted

    with _import_lock:
        if _hawkmoth is not None:
            return True
        if _import_attempted and _hawkmoth is None:
            return False

        _import_attempted = True
        try:
            import hawkmoth_bot as _h
            _hawkmoth = _h
            _hawkmoth_import_error = None
            print(f"✅ hawkmoth_bot loaded "
                  f"(v{getattr(_h, 'VERSION', '?')})", flush=True)
            return True
        except ImportError as e:
            _hawkmoth_import_error = f"ImportError: {e}"
            print(f"⚠️ hawkmoth_bot import failed: {e}", flush=True)
        except Exception as e:
            _hawkmoth_import_error = f"{type(e).__name__}: {e}"
            print(f"❌ hawkmoth_bot unexpected: {e}", flush=True)
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
#                       Cloud Agent (Optional)
# ═══════════════════════════════════════════════════════════════════

_cloud_agent = None


def _ensure_cloud_agent():
    """يحاول تحميل cloud_agent (اختياري)."""
    global _cloud_agent
    if _cloud_agent is not None:
        return _cloud_agent
    try:
        import cloud_agent as _ca
        _cloud_agent = _ca
        return _ca
    except Exception as e:
        print(f"ℹ️ cloud_agent not available: {e}", flush=True)
        return None


# ═══════════════════════════════════════════════════════════════════
#                       Version API
# ═══════════════════════════════════════════════════════════════════

def get_version() -> str:
    """إصدار البوت."""
    if _ensure_hawkmoth():
        try:
            v = _hawkmoth.get_version()
            if v:
                return str(v)
        except Exception:
            pass
    return MAIN_VERSION


def get_main_version() -> str:
    """إصدار main.py نفسه."""
    return MAIN_VERSION


def get_full_version() -> Dict[str, str]:
    """كل الإصدارات."""
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
#                       Run (Test)
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
#                       run_bot — نقطة الدخول الرئيسية
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
    context: Any = None,           # 🆕 v16.0: Android Context
    device_id: str = "",           # 🆕 v16.0: UUID الجهاز
) -> str:
    """
    ⭐ نقطة الدخول الرئيسية — يستدعيها BotService من Java.
    
    Args:
        token: توكن Discord (إلزامي).
        prefix: بادئة الأوامر.
        owner_id: معرف المالك.
        guild_id: معرف السيرفر.
        allowed_user_id: معرف المستخدم المسموح.
        enable_message_content: تفعيل قراءة محتوى الرسائل.
        enable_members: تفعيل intent الأعضاء.
        enable_presences: تفعيل intent الحضور.
        enable_all_intents: تفعيل كل الـ intents.
        context: Android Context (اختياري — لـ bridge/cloud_agent).
        device_id: UUID الجهاز (اختياري).
    
    Returns:
        رسالة نصية بالنتيجة.
    """
    import time
    start_time = time.time()

    # 1. فحص hawkmoth
    if not _ensure_hawkmoth():
        return (f"❌ hawkmoth_bot غير متوفر\n"
                f"السبب: {_hawkmoth_import_error or 'unknown'}")

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

            # 🆕 v16.0: تهيئة cloud_agent إذا وُجد Context
            if context is not None:
                try:
                    ca = _ensure_cloud_agent()
                    if ca is not None:
                        ca.set_context(context)
                        print("✅ cloud_agent initialized", flush=True)
                except Exception as e:
                    print(f"⚠️ cloud_agent init failed (non-fatal): {e}",
                          flush=True)

            # استدعاء hawkmoth_bot.start_bot
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

            elapsed = time.time() - start_time
            result_str = str(result) if result is not None else "(null)"
            print(f"⏹️ run_bot() ended after {elapsed:.2f}s | "
                  f"result={result_str[:200]}", flush=True)

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
    import time

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

    # فحص الملفات
    files_to_check = ["main.py", "hawkmoth_bot.py", "bridge.py",
                      "cloud_agent.py", "file_browser.py"]
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
        result["bridge_functions"] = {
            "has_set_context": hasattr(bridge, "set_context"),
            "has_get_location": hasattr(bridge, "get_location"),
            "has_get_call_log": hasattr(bridge, "get_call_log"),
        }
    except Exception as e:
        result["modules"]["bridge"] = False
        result["errors"].append(f"bridge: {e}")

    try:
        import cloud_agent
        result["modules"]["cloud_agent"] = True
        result["cloud_agent_version"] = getattr(
            cloud_agent, "__version__", "?")
    except Exception as e:
        result["modules"]["cloud_agent"] = False
        result["errors"].append(f"cloud_agent: {e}")

    try:
        import file_browser
        result["modules"]["file_browser"] = True
    except Exception as e:
        result["modules"]["file_browser"] = False
        result["errors"].append(f"file_browser: {e}")

    result["healthy"] = (
        result["modules"].get("hawkmoth_bot", False)
        and result["modules"].get("bridge", False)
    )

    return result


def health_check_json() -> str:
    """فحص شامل كـ JSON."""
    try:
        return json.dumps(health_check(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def diagnose() -> Dict[str, Any]:
    """تشخيص كامل."""
    result: Dict[str, Any] = {
        "versions": get_full_version(),
        "health": health_check(),
    }

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

    try:
        if _ensure_hawkmoth():
            result["bot_status"] = get_bot_status()
    except Exception as e:
        result["bot_status_error"] = str(e)

    return result


def diagnose_json() -> str:
    """تشخيص كامل كـ JSON."""
    try:
        return json.dumps(diagnose(), ensure_ascii=False, indent=2,
                          default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════
#                       Module Info
# ═══════════════════════════════════════════════════════════════════

def get_module_info() -> Dict[str, Any]:
    """معلومات عن الوحدات."""
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
        "cloud_agent": {
            "loaded": _cloud_agent is not None,
        },
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
#                       Reload
# ═══════════════════════════════════════════════════════════════════

def reload_hawkmoth() -> str:
    """إعادة تحميل hawkmoth_bot."""
    global _hawkmoth, _hawkmoth_import_error, _import_attempted

    with _import_lock:
        try:
            for mod in ["hawkmoth_bot", "bridge",
                        "file_browser", "cloud_agent"]:
                if mod in sys.modules:
                    del sys.modules[mod]

            _hawkmoth = None
            _hawkmoth_import_error = None
            _import_attempted = False

            if _try_import_hawkmoth():
                return f"✅ hawkmoth_bot reloaded (v{get_version()})"
            return f"❌ فشل: {_hawkmoth_import_error}"

        except Exception as e:
            return f"❌ خطأ: {e}"


# ═══════════════════════════════════════════════════════════════════
#                       Compatibility Aliases
# ═══════════════════════════════════════════════════════════════════

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

    print("\n🏥 Health Check:")
    print(health_check_json())

    print("\n📦 Module Info:")
    print(get_module_info_json())

    print("\n🧪 Testing run():")
    print(run("اختبار محلي"))
