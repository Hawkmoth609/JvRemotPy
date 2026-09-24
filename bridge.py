"""
bridge.py - النسخة الجبارة المحسّنة v2.

جسر للتواصل بين Python و Java.
يوفّر كل دوال الوصول إلى ميزات أندرويد الأصلية.

الميزات:
  - إدارة تلقائية لـ Activity / Service / Context
  - Caching للـ helper objects
  - معالجة أخطاء شاملة
  - Type hints للأمان
  - دوال JSON موحدة
"""

import logging
import json
from typing import Any, Optional, List, Dict
from java import jclass

log = logging.getLogger("bridge")

# ==========================================================
# الحالة الداخلية
# ==========================================================
_context = None          # Context الأساسي (Application)
_activity = None         # Activity (اختياري — للأنشطة)
_service = None          # Service (اختياري — للخلفية)

# Cache للأدوات
_helper_cache: Dict[str, Any] = {}


# ==========================================================
# ضبط السياق
# ==========================================================
def set_context(context) -> None:
    """
    يحفظ Context من Java.
    يقبل: Application / Activity / Service.
    """
    global _context, _activity, _service

    _context = context

    # محاولة تحديد النوع
    try:
        # Activity ترث من Context و لها getParent
        if hasattr(context, 'getParentActivityIntent'):
            _activity = context
            _service = None
            log.info("Context type: Activity")
            return
    except Exception:
        pass

    try:
        # Service لها onBind
        if hasattr(context, 'onBind'):
            _service = context
            _activity = None
            log.info("Context type: Service")
            return
    except Exception:
        pass

    # الباقي: Application Context
    _activity = None
    _service = None
    log.info("Context type: Application/Context")


def get_context():
    """يُرجع الـ Context الأساسي."""
    return _context


def get_activity():
    """يُرجع Activity إن وُجد، وإلا None."""
    return _activity


def _get_helper(class_name: str) -> Any:
    """
    يُنشئ أو يعيد helper object من Java (مع caching).
    """
    global _helper_cache

    if _context is None:
        raise RuntimeError("Context not set. Call set_context() first.")

    # Cache hit
    if class_name in _helper_cache:
        return _helper_cache[class_name]

    # إنشاء جديد
    HelperClass = jclass(f"com.example.myfirstapp.{class_name}")
    helper = HelperClass(_context)
    _helper_cache[class_name] = helper
    return helper


def clear_helper_cache():
    """يمسح الـ cache (عند تغيير السياق)."""
    global _helper_cache
    _helper_cache = {}
    log.info("Helper cache cleared")


# ==========================================================
# الملفات والمجلدات
# ==========================================================
def get_files_dir() -> str:
    """يُرجع مسار مجلد الملفات الخاص بالتطبيق."""
    if _context:
        try:
            return str(_context.getFilesDir().getAbsolutePath())
        except Exception as e:
            log.error(f"get_files_dir: {e}")
    return ""


def get_cache_dir() -> str:
    """يُرجع مسار مجلد الكاش."""
    if _context:
        try:
            return str(_context.getCacheDir().getAbsolutePath())
        except Exception as e:
            log.error(f"get_cache_dir: {e}")
    return ""


def get_external_files_dir() -> str:
    """يُرجع مسار الملفات الخارجية (getExternalFilesDir)."""
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
    """يفتح تطبيقًا بالاسم أو الحزمة."""
    try:
        return _get_helper("AppLauncher").openApp(query)
    except Exception as e:
        log.error(f"open_app: {e}")
        return f"❌ خطأ: {e}"


def open_url(url: str) -> str:
    """يفتح رابطًا في المتصفح."""
    try:
        return _get_helper("AppLauncher").openUrl(url)
    except Exception as e:
        log.error(f"open_url: {e}")
        return f"❌ خطأ: {e}"


def open_whatsapp_chat(phone: str = "", text: str = "") -> str:
    """يفتح محادثة واتساب."""
    try:
        return _get_helper("AppLauncher").openWhatsappChat(phone or "", text or "")
    except Exception as e:
        log.error(f"open_whatsapp_chat: {e}")
        return f"❌ خطأ: {e}"


def open_whatsapp_home() -> str:
    """يفتح واتساب على الشاشة الرئيسية."""
    try:
        return _get_helper("AppLauncher").openWhatsappHome()
    except Exception as e:
        log.error(f"open_whatsapp_home: {e}")
        return f"❌ خطأ: {e}"


def dial(phone: str) -> str:
    """يفتح لوحة الاتصال."""
    try:
        return _get_helper("AppLauncher").dial(phone)
    except Exception as e:
        log.error(f"dial: {e}")
        return f"❌ خطأ: {e}"


def send_sms(phone: str, text: str) -> str:
    """يفتح رسالة SMS جاهزة."""
    try:
        return _get_helper("AppLauncher").sendSms(phone, text)
    except Exception as e:
        log.error(f"send_sms: {e}")
        return f"❌ خطأ: {e}"


def open_file(path: str) -> str:
    """يفتح ملفًا بتطبيق النظام المناسب."""
    try:
        return _get_helper("AppLauncher").openFile(path)
    except Exception as e:
        log.error(f"open_file: {e}")
        return f"❌ خطأ: {e}"


def list_installed_apps() -> List[str]:
    """يُرجع قائمة الحزم المثبتة."""
    try:
        helper = _get_helper("AppLauncher")
        result = helper.listInstalledApps()
        return list(result) if result else []
    except Exception as e:
        log.error(f"list_installed_apps: {e}")
        return []


def open_camera_app() -> str:
    """يفتح تطبيق الكاميرا النظامي."""
    try:
        return _get_helper("AppLauncher").openCameraApp()
    except Exception as e:
        log.error(f"open_camera_app: {e}")
        return f"❌ خطأ: {e}"


# ==========================================================
# الإشعارات
# ==========================================================
def get_notifications(filter_pkg: str = "", limit: int = 30) -> str:
    """يُرجع الإشعارات النشطة كـ JSON."""
    try:
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return NotifReader.getActiveNotificationsJson(filter_pkg or "", int(limit))
    except Exception as e:
        log.error(f"get_notifications: {e}")
        return "[]"


def is_notification_access_enabled() -> bool:
    """هل صلاحية الإشعارات ممنوحة؟"""
    try:
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return bool(NotifReader.isEnabled(_context))
    except Exception as e:
        log.error(f"is_notification_access_enabled: {e}")
        return False


def open_notification_settings() -> str:
    """يفتح إعدادات الإشعارات."""
    try:
        return _get_helper("AppLauncher").openNotificationSettings()
    except Exception as e:
        log.error(f"open_notification_settings: {e}")
        return f"❌ {e}"


# ==========================================================
# SMS
# ==========================================================
def get_sms(limit: int = 10, search: str = "") -> str:
    """يُرجع آخر الرسائل كـ JSON."""
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
    """يُرجع جهات الاتصال كـ JSON."""
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
    """يُرجع حالة البطارية كـ JSON."""
    try:
        return _get_helper("BatteryHelper").getBatteryJson()
    except Exception as e:
        log.error(f"get_battery: {e}")
        return "{}"


# ==========================================================
# الحافظة
# ==========================================================
def get_clipboard() -> str:
    """يُرجع نص الحافظة."""
    try:
        return _get_helper("ClipboardHelper").getClipboardText() or ""
    except Exception as e:
        log.error(f"get_clipboard: {e}")
        return ""


# ==========================================================
# Toast
# ==========================================================
def show_toast(text: str) -> bool:
    """يُظهر رسالة Toast على شاشة الهاتف."""
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
    """
    يلتقط صورة بالكاميرا.
    camera_id: 0 = خلفية، 1 = أمامية.
    يُرجع مسار الملف أو "".
    """
    try:
        return _get_helper("CameraHelper").capturePhoto(int(camera_id)) or ""
    except Exception as e:
        log.error(f"capture_camera: {e}")
        return ""


# ==========================================================
# لقطة الشاشة
# ==========================================================
def capture_screen() -> str:
    """
    يلتقط لقطة شاشة.
    يُرجع مسار الملف أو "".
    """
    try:
        return _get_helper("ScreenCapture").capture() or ""
    except Exception as e:
        log.error(f"capture_screen: {e}")
        return ""


# ==========================================================
# ✅ جديد: الصلاحيات
# ==========================================================
def get_permissions_json() -> str:
    """
    يُرجع حالة كل الصلاحيات كـ JSON.
    يستخدمها البوت في /start.
    """
    if _context is None:
        return "{}"

    try:
        # PermissionManager يحتاج Activity وليس Context
        Activity = _activity if _activity else _context
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(Activity)
        return helper.getPermissionsJson()
    except Exception as e:
        log.error(f"get_permissions_json: {e}")
        return "{}"


def has_all_files_access() -> bool:
    """هل صلاحية الوصول الكامل للملفات ممنوحة؟"""
    try:
        Activity = _activity if _activity else _context
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(Activity)
        return bool(helper.hasAllFilesAccess())
    except Exception as e:
        log.error(f"has_all_files_access: {e}")
        return False


def has_notification_access() -> bool:
    """هل صلاحية الإشعارات ممنوحة؟"""
    try:
        Activity = _activity if _activity else _context
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(Activity)
        return bool(helper.hasNotificationAccess())
    except Exception as e:
        log.error(f"has_notification_access: {e}")
        return False


# ==========================================================
# معلومات الجهاز
# ==========================================================
def get_device_info() -> Dict[str, Any]:
    """يُرجع معلومات الجهاز كـ dict."""
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
    """يُرجع معلومات الجهاز كـ JSON string."""
    try:
        return json.dumps(get_device_info(), ensure_ascii=False)
    except Exception as e:
        return "{}"


# ==========================================================
# أدوات مساعدة
# ==========================================================
def is_ready() -> bool:
    """هل الجسر جاهز؟"""
    return _context is not None


def get_context_type() -> str:
    """يُرجع نوع السياق الحالي."""
    if _activity is not None:
        return "Activity"
    if _service is not None:
        return "Service"
    if _context is not None:
        return "Application"
    return "None"


def get_status() -> Dict[str, Any]:
    """يُرجع حالة الجسر كـ dict."""
    return {
        "ready": is_ready(),
        "context_type": get_context_type(),
        "cached_helpers": list(_helper_cache.keys()),
    }


def get_status_json() -> str:
    """يُرجع حالة الجسر كـ JSON."""
    try:
        return json.dumps(get_status(), ensure_ascii=False)
    except Exception:
        return "{}"


# ==========================================================
# تسجيل أولي
# ==========================================================
log.info("bridge.py loaded - v2 (enhanced)")