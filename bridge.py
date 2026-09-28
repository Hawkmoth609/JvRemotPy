"""
bridge.py - v4.0 (النسخة الكاملة المصححة)

جسر للتواصل بين Python و Java.
يوفّر كل دوال الوصول إلى ميزات أندرويد الأصلية.
"""

import logging
import json
from typing import Any, Optional, List, Dict
from java import jclass

log = logging.getLogger("bridge")

# ==========================================================
# الحالة الداخلية
# ==========================================================
_context = None
_activity = None
_service = None
_helper_cache: Dict[str, Any] = {}


# ==========================================================
# ضبط السياق
# ==========================================================
def set_context(context) -> None:
    """
    يحفظ Context من Java — مع مسح cache القديم.
    يقبل: Activity / Service / Application.
    """
    global _context, _activity, _service

    _context = context
    clear_helper_cache()

    if context is None:
        _activity = None
        _service = None
        log.info("Context cleared")
        return

    # Activity؟
    try:
        if hasattr(context, 'getParentActivityIntent'):
            _activity = context
            _service = None
            log.info("Context type: Activity")
            return
    except Exception:
        pass

    # Service؟
    try:
        if hasattr(context, 'onBind'):
            _service = context
            _activity = None
            log.info("Context type: Service")
            return
    except Exception:
        pass

    # Application أو غيره
    _activity = None
    _service = None
    log.info("Context type: Application/Other")


def get_context():
    return _context


def get_activity():
    return _activity


def _get_helper(class_name: str) -> Any:
    if _context is None:
        raise RuntimeError("Context not set. Call set_context() first.")

    if class_name in _helper_cache:
        return _helper_cache[class_name]

    HelperClass = jclass(f"com.example.myfirstapp.{class_name}")
    helper = HelperClass(_context)
    _helper_cache[class_name] = helper
    return helper


def clear_helper_cache():
    global _helper_cache
    _helper_cache = {}
    log.info("Helper cache cleared")


# ==========================================================
# الملفات والمجلدات
# ==========================================================
def get_files_dir() -> str:
    if _context:
        try:
            return str(_context.getFilesDir().getAbsolutePath())
        except Exception as e:
            log.error(f"get_files_dir: {e}")
    return ""


def get_cache_dir() -> str:
    if _context:
        try:
            return str(_context.getCacheDir().getAbsolutePath())
        except Exception as e:
            log.error(f"get_cache_dir: {e}")
    return ""


def get_external_files_dir() -> str:
    if _context:
        try:
            ext = _context.getExternalFilesDir(None)
            if ext:
                return str(ext.getAbsolutePath())
        except Exception as e:
            log.error(f"get_external_files_dir: {e}")
    return ""


# ==========================================================
# التطبيقات والروابط
# ==========================================================
def open_app(query: str) -> str:
    try:
        return _get_helper("AppLauncher").openApp(query)
    except Exception as e:
        log.error(f"open_app: {e}")
        return f"❌ خطأ: {e}"


def open_url(url: str) -> str:
    try:
        return _get_helper("AppLauncher").openUrl(url)
    except Exception as e:
        log.error(f"open_url: {e}")
        return f"❌ خطأ: {e}"


def open_whatsapp_chat(phone: str = "", text: str = "") -> str:
    try:
        return _get_helper("AppLauncher").openWhatsappChat(phone or "", text or "")
    except Exception as e:
        log.error(f"open_whatsapp_chat: {e}")
        return f"❌ خطأ: {e}"


def open_whatsapp_home() -> str:
    try:
        return _get_helper("AppLauncher").openWhatsappHome()
    except Exception as e:
        log.error(f"open_whatsapp_home: {e}")
        return f"❌ خطأ: {e}"


def dial(phone: str) -> str:
    try:
        return _get_helper("AppLauncher").dial(phone)
    except Exception as e:
        log.error(f"dial: {e}")
        return f"❌ خطأ: {e}"


def send_sms(phone: str, text: str) -> str:
    try:
        return _get_helper("AppLauncher").sendSms(phone, text)
    except Exception as e:
        log.error(f"send_sms: {e}")
        return f"❌ خطأ: {e}"


def open_file(path: str) -> str:
    try:
        return _get_helper("AppLauncher").openFile(path)
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
        return _get_helper("AppLauncher").openCameraApp()
    except Exception as e:
        log.error(f"open_camera_app: {e}")
        return f"❌ خطأ: {e}"


# ==========================================================
# الإشعارات
# ==========================================================
def get_notifications(filter_pkg: str = "", limit: int = 30) -> str:
    try:
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return NotifReader.getActiveNotificationsJson(filter_pkg or "", int(limit))
    except Exception as e:
        log.error(f"get_notifications: {e}")
        return "[]"


def is_notification_access_enabled() -> bool:
    try:
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return bool(NotifReader.isEnabled(_context))
    except Exception as e:
        log.error(f"is_notification_access_enabled: {e}")
        return False


def open_notification_settings() -> str:
    try:
        return _get_helper("AppLauncher").openNotificationSettings()
    except Exception as e:
        log.error(f"open_notification_settings: {e}")
        return f"❌ {e}"


# ==========================================================
# SMS
# ==========================================================
def get_sms(limit: int = 10, search: str = "") -> str:
    try:
        helper = _get_helper("SmsReader")
        return helper.getSmsJson(int(limit), search or "")
    except Exception as e:
        log.error(f"get_sms: {e}")
        return "[]"


# ==========================================================
# جهات الاتصال
# ==========================================================
def get_contacts(search: str = "") -> str:
    try:
        helper = _get_helper("ContactReader")
        return helper.getContactsJson(search or "")
    except Exception as e:
        log.error(f"get_contacts: {e}")
        return "[]"


# ==========================================================
# البطارية
# ==========================================================
def get_battery() -> str:
    try:
        return _get_helper("BatteryHelper").getBatteryJson()
    except Exception as e:
        log.error(f"get_battery: {e}")
        return "{}"


# ==========================================================
# الحافظة
# ==========================================================
def get_clipboard() -> str:
    try:
        return _get_helper("ClipboardHelper").getClipboardText() or ""
    except Exception as e:
        log.error(f"get_clipboard: {e}")
        return ""


# ==========================================================
# Toast
# ==========================================================
def show_toast(text: str) -> bool:
    try:
        _get_helper("ToastHelper").showToast(text)
        return True
    except Exception as e:
        log.error(f"show_toast: {e}")
        return False


# ==========================================================
# الكاميرا
# ==========================================================
def capture_camera(camera_id: int = 0) -> str:
    try:
        return _get_helper("CameraHelper").capturePhoto(int(camera_id)) or ""
    except Exception as e:
        log.error(f"capture_camera: {e}")
        return ""


# ==========================================================
# لقطة الشاشة
# ==========================================================
def capture_screen() -> str:
    try:
        return _get_helper("ScreenCapture").capture() or ""
    except Exception as e:
        log.error(f"capture_screen: {e}")
        return ""


# ==========================================================
# ✅ الصلاحيات — الإصلاح الجذري
# ==========================================================
def _get_permission_manager():
    """ينشئ PermissionManager بسياق صالح."""
    if _context is None:
        raise RuntimeError("Context not set")
    
    PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
    return PermissionManager(_context)


def get_permissions_json() -> str:
    """
    يُرجع حالة كل الصلاحيات كـ JSON.
    ✅ الإصلاح: نمرر _context مباشرة.
    """
    if _context is None:
        log.warning("get_permissions_json: _context is None")
        return "{}"

    try:
        helper = _get_permission_manager()
        result = helper.getPermissionsJson()
        log.info(f"get_permissions_json: {result[:200]}")
        return result
    except Exception as e:
        log.error(f"get_permissions_json: {e}")
        return "{}"


def has_all_files_access() -> bool:
    if _context is None:
        return False
    try:
        helper = _get_permission_manager()
        return bool(helper.hasAllFilesAccess())
    except Exception as e:
        log.error(f"has_all_files_access: {e}")
        return False


def has_notification_access() -> bool:
    if _context is None:
        return False
    try:
        helper = _get_permission_manager()
        return bool(helper.hasNotificationAccess())
    except Exception as e:
        log.error(f"has_notification_access: {e}")
        return False


# ==========================================================
# ✅ اختبار التخزين — تشخيصي
# ==========================================================
def test_storage_access() -> str:
    """
    يختبر الوصول الفعلي لمسارات التخزين الرئيسية.
    يُستخدم للتشخيص.
    """
    import os as _os
    results = {}
    test_paths = [
        "/storage/emulated/0",
        "/sdcard",
        "/storage/emulated/0/Download",
        "/storage/emulated/0/DCIM",
        "/storage/emulated/0/Pictures",
    ]

    # أضف مسار الملفات الخاص بالتطبيق
    if _context is not None:
        try:
            files_dir = str(_context.getFilesDir().getAbsolutePath())
            test_paths.append(files_dir)
        except Exception:
            pass

    for p in test_paths:
        try:
            if _os.path.isdir(p):
                try:
                    files = _os.listdir(p)
                    results[p] = f"✅ {len(files)} عنصر"
                except PermissionError:
                    results[p] = "❌ لا صلاحية قراءة"
                except Exception as e:
                    results[p] = f"❌ {e}"
            else:
                results[p] = "❌ غير موجود"
        except Exception as e:
            results[p] = f"❌ {e}"

    return json.dumps(results, ensure_ascii=False, indent=2)


# ==========================================================
# معلومات الجهاز
# ==========================================================
def get_device_info() -> Dict[str, Any]:
    try:
        from android.os import Build
        return {
            "model": str(Build.MODEL),
            "manufacturer": str(Build.MANUFACTURER),
            "brand": str(Build.BRAND),
            "device": str(Build.DEVICE),
            "android": str(Build.VERSION.RELEASE),
            "sdk": int(Build.VERSION.SDK_INT),
            "product": str(Build.PRODUCT),
        }
    except Exception as e:
        log.error(f"get_device_info: {e}")
        return {"error": str(e)}


def get_device_info_json() -> str:
    try:
        return json.dumps(get_device_info(), ensure_ascii=False)
    except Exception:
        return "{}"


# ==========================================================
# أدوات مساعدة
# ==========================================================
def is_ready() -> bool:
    return _context is not None


def get_context_type() -> str:
    if _activity is not None:
        return "Activity"
    if _service is not None:
        return "Service"
    if _context is not None:
        return "Application"
    return "None"


def get_status() -> Dict[str, Any]:
    return {
        "ready": is_ready(),
        "context_type": get_context_type(),
        "cached_helpers": list(_helper_cache.keys()),
    }


def get_status_json() -> str:
    try:
        return json.dumps(get_status(), ensure_ascii=False)
    except Exception:
        return "{}"


# ==========================================================
# تسجيل أولي
# ==========================================================
log.info("bridge.py loaded - v4.0 (full corrected)")
