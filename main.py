"""
╔══════════════════════════════════════════════════════════════════╗
║                     JvRemotPy — Entry Point                      ║
║                                                                  ║
║  This is a thin wrapper that delegates to hawkmoth_bot.py.       ║
║  It provides a stable interface for BotService.java (Java).      ║
║                                                                  ║
║  المميزات:                                                       ║
║    • واجهة ثابتة للـ Java                                        ║
║    • تفويض كامل إلى hawkmoth_bot                                 ║
║    • لا يوجد توكن مدمج                                           ║
║    • Thread-safe                                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import traceback
import threading
from typing import Optional, Dict, Any

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


# ═══════════════════════════════════════════════════════════════════
#                       DELEGATE TO HAWKMOTH_BOT
# ═══════════════════════════════════════════════════════════════════

_hawkmoth = None
_hawkmoth_import_error = None

try:
    import hawkmoth_bot as _hawkmoth
except ImportError as e:
    _hawkmoth_import_error = str(e)
    print(f"⚠️ hawkmoth_bot import failed: {e}", flush=True)
except Exception as e:
    _hawkmoth_import_error = str(e)
    print(f"❌ hawkmoth_bot unexpected error: {e}", flush=True)


def get_version() -> str:
    if _hawkmoth:
        try:
            return _hawkmoth.get_version()
        except Exception:
            pass
    return "7.1.0"


# ═══════════════════════════════════════════════════════════════════
#                       PUBLIC API (for Java)
# ═══════════════════════════════════════════════════════════════════

def run(message: str = "") -> str:
    """دالة اختبار بسيطة (بدون Discord)."""
    return (
        f"🎉 JvRemotPy v{get_version()} يعمل!\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"📱 Platform: {sys.platform}\n"
        f"💬 رسالتك: {message}"
    )


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
    تُفوّض العمل إلى hawkmoth_bot.start_bot().
    """
    if _hawkmoth is None:
        return f"❌ hawkmoth_bot غير متوفر: {_hawkmoth_import_error}"

    if not token:
        return "❌ التوكن فارغ"

    try:
        return _hawkmoth.start_bot(
            token=token.strip(),
            prefix=prefix or "!",
            owner_id=int(owner_id) if owner_id else None,
            guild_id=int(guild_id) if guild_id else None,
            allowed_user_id=int(allowed_user_id) if allowed_user_id else None,
            enable_message_content=bool(enable_message_content),
            enable_members=bool(enable_members),
            enable_presences=bool(enable_presences),
            enable_all_intents=bool(enable_all_intents),
        )
    except Exception as e:
        try:
            print(traceback.format_exc(), flush=True)
        except Exception:
            pass
        return f"❌ فشل تشغيل البوت: {e}"


def stop_bot() -> str:
    """إيقاف البوت — يُستدعى من Java."""
    if _hawkmoth is None:
        return "⚠️ hawkmoth_bot غير متوفر"
    try:
        return _hawkmoth.stop_bot()
    except Exception as e:
        return f"❌ فشل الإيقاف: {e}"


def get_bot_status() -> Dict[str, Any]:
    """حالة البوت — تُستدعى من Java."""
    if _hawkmoth is None:
        return {"running": False, "reason": "hawkmoth_not_loaded"}
    try:
        return _hawkmoth.get_bot_status()
    except Exception as e:
        return {"running": False, "reason": str(e)}


def is_contacts_bridge_ready() -> bool:
    """هل ContactsBridge جاهز؟"""
    if _hawkmoth is None:
        return False
    try:
        return _hawkmoth.is_contacts_bridge_ready()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       LOCAL TEST
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"✅ main.py v{get_version()}")
    print(f"hawkmoth_bot: {'✅ loaded' if _hawkmoth else '❌ ' + str(_hawkmoth_import_error)}")
    print(run("اختبار"))
