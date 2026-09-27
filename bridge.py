"""
╔══════════════════════════════════════════════════════════════════╗
║                       bridge.py — v3.0                          ║
║                                                                  ║
║  الجسر بين Python و Java (Chaquopy)                              ║
║                                                                  ║
║  الميزات الجديدة:                                                ║
║    ✅ Thread-safe مع RLock لكل عملية                            ║
║    ✅ Cache يُمسح عند تغيير Context                             ║
║    ✅ try/except في كل دالة (لا crash)                          ║
║    ✅ تسجيل شامل لكل الأخطاء                                    ║
║    ✅ دوال جديدة: is_ready، get_status، get_android_*          ║
║    ✅ دعم كامل لـ Contacts، SMS، Camera، Notifications          ║
║    ✅ معالجة أفضل للأخطاء في بيئات غير Android                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import logging
import json
import threading
import time
from typing import Any, Optional, List, Dict

log = logging.getLogger("bridge")

# ═══════════════════════════════════════════════════════════════════
#                       استيراد java (محمي)
# ═══════════════════════════════════════════════════════════════════

try:
    from java import jclass
    JAVA_AVAILABLE = True
except ImportError as _e:
    JAVA_AVAILABLE = False
    jclass = None
    log.warning(f"⚠️ java module not available: {_e}")

# ═══════════════════════════════════════════════════════════════════
#                       الحالة الداخلية (Thread-Safe)
# ═══════════════════════════════════════════════════════════════════

_context = None          # Context الأساسي
_activity = None         # Activity (إن وُجد)
_service = None          # Service (إن وُجد)

# أقفال
_context_lock = threading.RLock()
_helper_cache_lock = threading.RLock()
_helper_cache: Dict[str, Any] = {}

# مسجل الأخطاء
_last_error: Optional[str] = None
_last_error_lock = threading.RLock()


def _set_last_error(err: str) -> None:
    global _last_error
    with _last_error_lock:
        _last_error = err


def get_last_error() -> Optional[str]:
    with _last_error_lock:
        return _last_error


# ═══════════════════════════════════════════════════════════════════
#                       ضبط السياق
# ═══════════════════════════════════════════════════════════════════

def set_context(context) -> None:
    """
    يحفظ Context من Java.
    يقبل: Application / Activity / Service.
    Thread-safe + يمسح الـ cache عند التغيير.
    """
    global _context, _activity, _service

    if context is None:
        log.warning("set_context(None) — ignored")
        return

    with _context_lock:
        _context = context
        _activity = None
        _service = None

        # محاولة تحديد النوع
        try:
            if hasattr(context, 'getParentActivityIntent'):
                _activity = context
                log.info("✅ Context type: Activity")
                _clear_cache_internal()
                return
        except Exception:
            pass

        try:
            if hasattr(context, 'onBind') and not hasattr(context, 'getParentActivityIntent'):
                _service = context
                log.info("✅ Context type: Service")
                _clear_cache_internal()
                return
        except Exception:
            pass

        log.info("✅ Context type: Application/Context")

    # مسح الـ cache عند تغيير السياق
    _clear_cache_internal()


def get_context():
    """يُرجع Context الأساسي."""
    with _context_lock:
        return _context


def get_activity():
    """يُرجع Activity إن وُجد، وإلا Context."""
    with _context_lock:
        return _activity if _activity else _context


def get_service():
    """يُرجع Service إن وُجد."""
    with _context_lock:
        return _service


def is_ready() -> bool:
    """هل الجسر جاهز؟"""
    with _context_lock:
        return _context is not None


def get_context_type() -> str:
    """يُرجع نوع السياق الحالي."""
    with _context_lock:
        if _activity is not None:
            return "Activity"
        if _service is not None:
            return "Service"
        if _context is not None:
            return "Application"
        return "None"


# ═══════════════════════════════════════════════════════════════════
#                       Helper Cache
# ═══════════════════════════════════════════════════════════════════

def _clear_cache_internal() -> None:
    """يمسح الـ cache (داخلي — يُفترض أن القفل مُحتجز)."""
    with _helper_cache_lock:
        _helper_cache.clear()
        log.info("🧹 Helper cache cleared")


def clear_helper_cache() -> None:
    """يمسح الـ cache (عام)."""
    _clear_cache_internal()


def _get_helper(class_name: str) -> Any:
    """
    يُنشئ أو يُعيد helper object من Java (thread-safe + cached).
    """
    if not JAVA_AVAILABLE:
        raise RuntimeError("Java module غير متاح (بيئة غير Android)")

    ctx = get_context()
    if ctx is None:
        raise RuntimeError("Context not set. Call set_context() first.")

    with _helper_cache_lock:
        cached = _helper_cache.get(class_name)
        if cached is not None:
            return cached

        try:
            HelperClass = jclass(f"com.example.myfirstapp.{class_name}")
            helper = HelperClass(ctx)
            _helper_cache[class_name] = helper
            log.debug(f"✅ Created helper: {class_name}")
            return helper
        except Exception as e:
            _set_last_error(f"{class_name}: {e}")
            log.error(f"❌ _get_helper({class_name}): {e}")
            raise


# ═══════════════════════════════════════════════════════════════════
#                       الملفات والمجلدات
# ═══════════════════════════════════════════════════════════════════

def get_files_dir() -> str:
    """مجلد الملفات الخاص بالتطبيق."""
    try:
        ctx = get_context()
        if ctx is not None:
            return str(ctx.getFilesDir().getAbsolutePath())
    except Exception as e:
        log.error(f"get_files_dir: {e}")
    return ""


def get_cache_dir() -> str:
    """مجلد الكاش."""
    try:
        ctx = get_context()
        if ctx is not None:
            return str(ctx.getCacheDir().getAbsolutePath())
    except Exception as e:
        log.error(f"get_cache_dir: {e}")
    return ""


def get_external_files_dir() -> str:
    """مجلد الملفات الخارجية."""
    try:
        ctx = get_context()
        if ctx is not None:
            ext = ctx.getExternalFilesDir(None)
            if ext:
                return str(ext.getAbsolutePath())
    except Exception as e:
        log.error(f"get_external_files_dir: {e}")
    return ""


# ═══════════════════════════════════════════════════════════════════
#                       التطبيقات والروابط
# ═══════════════════════════════════════════════════════════════════

def open_app(query: str) -> str:
    try:
        return str(_get_helper("AppLauncher").openApp(query or ""))
    except Exception as e:
        log.error(f"open_app: {e}")
        return f"❌ خطأ: {e}"


def open_url(url: str) -> str:
    try:
        return str(_get_helper("AppLauncher").openUrl(url or ""))
    except Exception as e:
        log.error(f"open_url: {e}")
        return f"❌ خطأ: {e}"


def open_whatsapp_chat(phone: str = "", text: str = "") -> str:
    try:
        return str(_get_helper("AppLauncher").openWhatsappChat(phone or "", text or ""))
    except Exception as e:
        log.error(f"open_whatsapp_chat: {e}")
        return f"❌ خطأ: {e}"


def open_whatsapp_home() -> str:
    try:
        return str(_get_helper("AppLauncher").openWhatsappHome())
    except Exception as e:
        log.error(f"open_whatsapp_home: {e}")
        return f"❌ خطأ: {e}"


def dial(phone: str) -> str:
    try:
        return str(_get_helper("AppLauncher").dial(phone or ""))
    except Exception as e:
        log.error(f"dial: {e}")
        return f"❌ خطأ: {e}"


def send_sms(phone: str, text: str) -> str:
    try:
        return str(_get_helper("AppLauncher").sendSms(phone or "", text or ""))
    except Exception as e:
        log.error(f"send_sms: {e}")
        return f"❌ خطأ: {e}"


def open_file(path: str) -> str:
    try:
        return str(_get_helper("AppLauncher").openFile(path or ""))
    except Exception as e:
        log.error(f"open_file: {e}")
        return f"❌ خطأ: {e}"


def list_installed_apps() -> List[str]:
    try:
        helper = _get_helper("AppLauncher")
        result = helper.listInstalledApps()
        return list(result) if result else []
    except Exception as e:
        log.error(f"list_installed_apps: {e}")
        return []


def open_camera_app() -> str:
    try:
        return str(_get_helper("AppLauncher").openCameraApp())
    except Exception as e:
        log.error(f"open_camera_app: {e}")
        return f"❌ خطأ: {e}"


# ═══════════════════════════════════════════════════════════════════
#                       الإشعارات
# ═══════════════════════════════════════════════════════════════════

def get_notifications(filter_pkg: str = "", limit: int = 30) -> str:
    try:
        if not JAVA_AVAILABLE:
            return "[]"
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return str(NotifReader.getActiveNotificationsJson(filter_pkg or "", int(limit)))
    except Exception as e:
        log.error(f"get_notifications: {e}")
        return "[]"


def is_notification_access_enabled() -> bool:
    try:
        if not JAVA_AVAILABLE:
            return False
        ctx = get_context()
        if ctx is None:
            return False
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return bool(NotifReader.isEnabled(ctx))
    except Exception as e:
        log.error(f"is_notification_access_enabled: {e}")
        return False


def open_notification_settings() -> str:
    try:
        return str(_get_helper("AppLauncher").openNotificationSettings())
    except Exception as e:
        log.error(f"open_notification_settings: {e}")
        return f"❌ {e}"


# ═══════════════════════════════════════════════════════════════════
#                       SMS
# ═══════════════════════════════════════════════════════════════════

def get_sms(limit: int = 10, search: str = "") -> str:
    try:
        helper = _get_helper("SmsReader")
        return str(helper.getSmsJson(int(limit), search or ""))
    except Exception as e:
        log.error(f"get_sms: {e}")
        return "[]"


def get_sms_count() -> int:
    try:
        helper = _get_helper("SmsReader")
        return int(helper.getSmsCount())
    except Exception as e:
        log.error(f"get_sms_count: {e}")
        return 0


# ═══════════════════════════════════════════════════════════════════
#                       جهات الاتصال
# ═══════════════════════════════════════════════════════════════════

def get_contacts(search: str = "") -> str:
    try:
        helper = _get_helper("ContactReader")
        return str(helper.getContactsJson(search or ""))
    except Exception as e:
        log.error(f"get_contacts: {e}")
        return "[]"


def get_contacts_count() -> int:
    try:
        helper = _get_helper("ContactReader")
        return int(helper.getContactsCount())
    except Exception as e:
        log.error(f"get_contacts_count: {e}")
        return 0


def contacts_bridge_ready() -> bool:
    """هل ContactsBridge (Java) جاهز؟"""
    try:
        if not JAVA_AVAILABLE:
            return False
        ContactsBridge = jclass("com.example.myfirstapp.ContactsBridge")
        return bool(ContactsBridge.isReady())
    except Exception as e:
        log.error(f"contacts_bridge_ready: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#                       البطارية
# ═══════════════════════════════════════════════════════════════════

def get_battery() -> str:
    try:
        return str(_get_helper("BatteryHelper").getBatteryJson())
    except Exception as e:
        log.error(f"get_battery: {e}")
        return "{}"


# ═══════════════════════════════════════════════════════════════════
#                       الحافظة
# ═══════════════════════════════════════════════════════════════════

def get_clipboard() -> str:
    try:
        return str(_get_helper("ClipboardHelper").getClipboardText() or "")
    except Exception as e:
        log.error(f"get_clipboard: {e}")
        return ""


def set_clipboard(text: str) -> bool:
    try:
        return bool(_get_helper("ClipboardHelper").setClipboardText(text or ""))
    except Exception as e:
        log.error(f"set_clipboard: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#                       Toast
# ═══════════════════════════════════════════════════════════════════

def show_toast(text: str) -> bool:
    try:
        _get_helper("ToastHelper").showToast(text or "")
        return True
    except Exception as e:
        log.error(f"show_toast: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#                       الكاميرا
# ═══════════════════════════════════════════════════════════════════

def capture_camera(camera_id: int = 0) -> str:
    """camera_id: 0 = خلفية، 1 = أمامية."""
    try:
        result = _get_helper("CameraHelper").capturePhoto(int(camera_id))
        return str(result) if result else ""
    except Exception as e:
        log.error(f"capture_camera: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════
#                       لقطة الشاشة
# ═══════════════════════════════════════════════════════════════════

def capture_screen() -> str:
    try:
        result = _get_helper("ScreenCapture").capture()
        return str(result) if result else ""
    except Exception as e:
        log.error(f"capture_screen: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════════
#                       الصلاحيات
# ═══════════════════════════════════════════════════════════════════

def get_permissions_json() -> str:
    """يُرجع كل الصلاحيات كـ JSON (يستخدمه /start)."""
    try:
        if not JAVA_AVAILABLE:
            return "{}"
        ctx = get_context()
        if ctx is None:
            return "{}"

        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(ctx)
        return str(helper.getPermissionsJson())
    except Exception as e:
        log.error(f"get_permissions_json: {e}")
        return "{}"


def has_all_files_access() -> bool:
    try:
        if not JAVA_AVAILABLE:
            return False
        ctx = get_context()
        if ctx is None:
            return False
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(ctx)
        return bool(helper.hasAllFilesAccess())
    except Exception as e:
        log.error(f"has_all_files_access: {e}")
        return False


def has_notification_access() -> bool:
    return is_notification_access_enabled()


# ═══════════════════════════════════════════════════════════════════
#                       معلومات الجهاز
# ═══════════════════════════════════════════════════════════════════

def get_device_info() -> Dict[str, Any]:
    """معلومات كاملة عن الجهاز."""
    info = {
        "model": "unknown",
        "manufacturer": "unknown",
        "brand": "unknown",
        "device": "unknown",
        "android": "unknown",
        "sdk": 0,
        "product": "unknown",
    }
    try:
        if JAVA_AVAILABLE:
            from android.os import Build
            info["model"] = str(Build.MODEL)
            info["manufacturer"] = str(Build.MANUFACTURER)
            info["brand"] = str(Build.BRAND)
            info["device"] = str(Build.DEVICE)
            info["android"] = str(Build.VERSION.RELEASE)
            info["sdk"] = int(Build.VERSION.SDK_INT)
            info["product"] = str(Build.PRODUCT)
    except Exception as e:
        log.error(f"get_device_info: {e}")
        info["error"] = str(e)
    return info


def get_device_info_json() -> str:
    try:
        return json.dumps(get_device_info(), ensure_ascii=False)
    except Exception:
        return "{}"


def get_android_version() -> int:
    """يُرجع SDK_INT."""
    try:
        if JAVA_AVAILABLE:
            from android.os import Build
            return int(Build.VERSION.SDK_INT)
    except Exception:
        pass
    return 0


def get_android_release() -> str:
    """يُرجع إصدار أندرويد كنص."""
    try:
        if JAVA_AVAILABLE:
            from android.os import Build
            return str(Build.VERSION.RELEASE)
    except Exception:
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════
#                       الحالة العامة
# ═══════════════════════════════════════════════════════════════════

def get_status() -> Dict[str, Any]:
    """حالة الجسر كـ dict."""
    with _helper_cache_lock:
        cached = list(_helper_cache.keys())

    return {
        "ready": is_ready(),
        "java_available": JAVA_AVAILABLE,
        "context_type": get_context_type(),
        "cached_helpers": cached,
        "last_error": get_last_error(),
        "android_sdk": get_android_version(),
        "android_release": get_android_release(),
    }


def get_status_json() -> str:
    try:
        return json.dumps(get_status(), ensure_ascii=False)
    except Exception:
        return "{}"


def get_version() -> str:
    return "3.0.0"


# ═══════════════════════════════════════════════════════════════════
#                       تسجيل أولي
# ═══════════════════════════════════════════════════════════════════

log.info(f"bridge.py loaded — v{get_version()} (java_available={JAVA_AVAILABLE})")
