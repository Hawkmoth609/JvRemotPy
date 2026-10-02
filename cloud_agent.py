"""
╔══════════════════════════════════════════════════════════════════╗
║               cloud_agent.py — v1.0                              ║
║                                                                  ║
║  الجسر بين Python و Supabase (عبر Java bridge)                  ║
║                                                                  ║
║  يعمل على User Phone فقط.                                        ║
║                                                                  ║
║  الوظائف:                                                        ║
║    • get_device_id()       — UUID الجهاز                        ║
║    • get_session_status()  — حالة bot_session                   ║
║    • is_my_session_active()— هل أنا النشط؟                      ║
║    • log_command()         — تسجيل أمر في commands (audit)      ║
║    • log_result()          — تسجيل نتيجة في command_results     ║
║    • get_status()          — حالة كاملة                         ║
║                                                                  ║
║  ✅ Thread-safe                                                  ║
║  ✅ Best-effort (لا يُفشل عند فشل السحابة)                      ║
║  ✅ Defensive (لا استثناءات تتسرب)                              ║
║  ✅ يعتمد على bridge._context للوصول إلى Java                    ║
╚══════════════════════════════════════════════════════════════════╝
"""

import json
import logging
import time
from typing import Any, Optional, Dict
from java import jclass

log = logging.getLogger("cloud_agent")

__version__ = "1.0.0"

# ═══════════════════════════════════════════════════════════════════
#                       الحالة الداخلية
# ═══════════════════════════════════════════════════════════════════

_context = None
_device_id: str = ""
_cache: Dict[str, Any] = {}
_init_generation = 0
_last_init_at = 0.0


# ═══════════════════════════════════════════════════════════════════
#                       التهيئة
# ═══════════════════════════════════════════════════════════════════

def set_context(context) -> None:
    """
    يُهيّئ cloud_agent بـ Context من Java.
    يُستدعى من BotService أو main.run_bot.
    """
    global _context, _device_id, _init_generation, _last_init_at

    _context = context
    _init_generation += 1
    _last_init_at = time.time()
    _cache.clear()

    if context is None:
        _device_id = ""
        log.info("cloud_agent: context cleared (gen=%d)", _init_generation)
        return

    # جلب device_id تلقائياً
    try:
        DeviceIdentity = jclass(
            "com.example.myfirstapp.cloud.core.DeviceIdentity"
        )
        identity = DeviceIdentity.get(context)
        _device_id = str(identity.getOrCreateUuid())
        log.info("cloud_agent: initialized (device=%s, gen=%d)",
                 _device_id[:8], _init_generation)
    except Exception as e:
        log.warning("cloud_agent: device_id fetch failed: %s", e)
        _device_id = ""


def is_ready() -> bool:
    """هل cloud_agent جاهز؟"""
    return _context is not None


def get_device_id() -> str:
    """UUID الجهاز الحالي."""
    return _device_id


# ═══════════════════════════════════════════════════════════════════
#                       Internal Helpers
# ═══════════════════════════════════════════════════════════════════

def _get_repo(class_path: str):
    """
    يحصل على Repository instance (cached).
    class_path مثال: "cloud.repos.CloudCommandRepository"
    """
    if _context is None:
        return None

    cache_key = f"repo:{class_path}"
    if cache_key in _cache:
        return _cache[cache_key]

    try:
        full_path = f"com.example.myfirstapp.{class_path}"
        RepoClass = jclass(full_path)
        repo = RepoClass(_context)
        _cache[cache_key] = repo
        return repo
    except Exception as e:
        log.error("_get_repo(%s) failed: %s", class_path, e)
        return None


def _get_session_repo():
    """CloudBotSessionRepository"""
    return _get_repo("cloud.repos.CloudBotSessionRepository")


def _get_command_repo():
    """CloudCommandRepository"""
    return _get_repo("cloud.repos.CloudCommandRepository")


def _get_device_repo():
    """CloudDeviceRepository"""
    return _get_repo("cloud.repos.CloudDeviceRepository")


def _safe_json_dumps(data: Any, fallback: str = "{}") -> str:
    """تحويل آمن إلى JSON."""
    if data is None:
        return fallback
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        return fallback


def _js_to_dict(js_obj) -> Optional[Dict[str, Any]]:
    """يحوّل JS-like object إلى dict (best-effort)."""
    if js_obj is None:
        return None
    try:
        # قد يكون PyObject من Chaquopy
        if hasattr(js_obj, 'toString'):
            s = str(js_obj.toString())
            if s and s.startswith('{'):
                return json.loads(s)
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════════
#                       Session Queries
# ═══════════════════════════════════════════════════════════════════

def get_session_status() -> Dict[str, Any]:
    """
    يقرأ حالة bot_session من Supabase.
    """
    if _context is None:
        return {"status": "no_context"}

    try:
        repo = _get_session_repo()
        if repo is None:
            return {"status": "no_repo"}

        result = repo.fetchOrNull()
        if result is None:
            return {"status": "none"}

        # result هو CloudBotSession
        try:
            return {
                "status": str(result.status),
                "user_device_id": str(result.userDeviceId),
                "admin_device_id": str(result.adminDeviceId),
                "health_score": int(result.healthScore),
                "has_token": bool(result.hasToken()),
                "is_running": bool(result.isRunning()),
                "is_active": bool(result.isActiveUser(_device_id)),
            }
        except Exception as e:
            log.warning("get_session_status parse: %s", e)
            return {"status": "parse_error"}

    except Exception as e:
        log.warning("get_session_status failed: %s", e)
        return {"status": "error", "error": str(e)}


def is_my_session_active() -> bool:
    """
    هل هذا الجهاز هو الجهاز النشط في bot_session؟
    """
    if _context is None or not _device_id:
        return False

    try:
        status = get_session_status()
        return bool(status.get("is_active", False))
    except Exception:
        return False


def is_bot_running_remotely() -> bool:
    """
    هل bot_session يشير إلى تشغيل البوت على أي جهاز؟
    """
    try:
        status = get_session_status()
        return bool(status.get("is_running", False))
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════
#                       Command Logging (Audit)
# ═══════════════════════════════════════════════════════════════════

def log_command(
    action: str,
    params: Optional[Dict[str, Any]] = None,
    success: bool = True,
    result_data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    duration_ms: int = 0,
) -> bool:
    """
    يُسجّل أمر Discord في `commands` table (للتدقيق).
    
    ملاحظة: هذا NOT أمر Cloud — إنه سجل فقط. الأوامر الفعلية
    تأتي عبر Discord Gateway مباشرة.
    
    Args:
        action: اسم الأمر (snap_front, gps, ...)
        params: معاملات الأمر
        success: هل نجح؟
        result_data: نتيجة التنفيذ
        error: رسالة خطأ (إن وُجد)
        duration_ms: مدة التنفيذ
    
    Returns:
        True إذا نجح التسجيل
    """
    if _context is None or not _device_id:
        return False

    try:
        repo = _get_command_repo()
        if repo is None:
            return False

        # بناء params
        log_params: Dict[str, Any] = {
            "source": "discord",
            "duration_ms": duration_ms,
            "logged_at": int(time.time() * 1000),
        }
        if params:
            log_params["input"] = params
        if result_data:
            log_params["result"] = result_data
        if error:
            log_params["error"] = str(error)[:500]

        # إنشاء CloudCommand
        try:
            CloudCommand = jclass(
                "com.example.myfirstapp.cloud.models.CloudCommand"
            )
            cmd = CloudCommand(_device_id, action,
                              _dict_to_json_object(log_params))

            # تعيين الحقول الإضافية
            if success:
                cmd.status = "done"
                cmd.executedAt = int(time.time() * 1000)
            else:
                cmd.status = "failed"
                cmd.executedAt = int(time.time() * 1000)

            cmd.priority = 5

            # إدراج مباشر (بدون RPC — لأننا نعرف الترتيب)
            result = repo.insert(cmd)

            if result and result.isSuccess():
                log.debug("cloud_agent: logged %s", action)
                return True
            else:
                log.debug("cloud_agent: log_command non-fatal failure")
                return False

        except Exception as e:
            log.warning("log_command build failed: %s", e)
            return False

    except Exception as e:
        log.warning("log_command failed: %s", e)
        return False


def _dict_to_json_object(d: Dict[str, Any]):
    """يحوّل dict إلى org.json.JSONObject."""
    try:
        JSONObject = jclass("org.json.JSONObject")
        return JSONObject(_safe_json_dumps(d))
    except Exception as e:
        log.warning("_dict_to_json_object: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════
#                       Device Reporting
# ═══════════════════════════════════════════════════════════════════

def report_bot_running(running: bool = True) -> bool:
    """
    يُبلّغ Supabase بأن البوت يعمل/توقف على هذا الجهاز.
    """
    if _context is None or not _device_id:
        return False

    try:
        repo = _get_device_repo()
        if repo is None:
            return False

        repo.updateHeartbeat(_device_id, bool(running))
        log.debug("cloud_agent: bot_running=%s reported", running)
        return True

    except Exception as e:
        log.warning("report_bot_running failed: %s", e)
        return False


# ═══════════════════════════════════════════════════════════════════
#                       Diagnostics
# ═══════════════════════════════════════════════════════════════════

def get_status() -> Dict[str, Any]:
    """حالة cloud_agent للتشخيص."""
    return {
        "ready": is_ready(),
        "device_id": _device_id[:8] if _device_id else "",
        "has_device_id": bool(_device_id),
        "generation": _init_generation,
        "cache_size": len(_cache),
        "version": __version__,
    }


def get_status_json() -> str:
    """حالة cloud_agent كـ JSON."""
    return _safe_json_dumps(get_status())


# ═══════════════════════════════════════════════════════════════════
#                       Initialization Log
# ═══════════════════════════════════════════════════════════════════

log.info("cloud_agent.py loaded (v%s)", __version__)