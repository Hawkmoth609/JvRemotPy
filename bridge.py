"""
bridge.py: جسر للتواصل بين Python و Java.
يوفّر دوال للوصول إلى ميزات أندرويد الأصلية.
"""

import logging
from java import jclass

log = logging.getLogger("bridge")

_context = None


def set_context(context):
    """يحفظ Context من Java."""
    global _context
    _context = context
    log.info(f"Context set: {context}")


def get_context():
    return _context


def _get_helper(class_name):
    """يُنشئ كائن مساعد من Java."""
    if _context is None:
        raise RuntimeError("Context not set. Call set_context() first.")
    HelperClass = jclass(f"com.example.myfirstapp.{class_name}")
    return HelperClass(_context)


# ===== الملفات =====
def get_files_dir():
    """يُرجع مسار مجلد الملفات."""
    if _context:
        return str(_context.getFilesDir().getAbsolutePath())
    return ""


def get_cache_dir():
    if _context:
        return str(_context.getCacheDir().getAbsolutePath())
    return ""


# ===== التطبيقات =====
def open_app(query):
    """يفتح تطبيقًا."""
    try:
        helper = _get_helper("AppLauncher")
        return helper.openApp(query)
    except Exception as e:
        return f"❌ خطأ: {e}"


def open_url(url):
    """يفتح رابطًا."""
    try:
        helper = _get_helper("AppLauncher")
        return helper.openUrl(url)
    except Exception as e:
        return f"❌ خطأ: {e}"


def open_whatsapp_chat(phone, text=""):
    try:
        helper = _get_helper("AppLauncher")
        return helper.openWhatsappChat(phone, text)
    except Exception as e:
        return f"❌ خطأ: {e}"


def dial(phone):
    try:
        helper = _get_helper("AppLauncher")
        return helper.dial(phone)
    except Exception as e:
        return f"❌ خطأ: {e}"


def send_sms(phone, text):
    try:
        helper = _get_helper("AppLauncher")
        return helper.sendSms(phone, text)
    except Exception as e:
        return f"❌ خطأ: {e}"


def open_file(path):
    try:
        helper = _get_helper("AppLauncher")
        return helper.openFile(path)
    except Exception as e:
        return f"❌ خطأ: {e}"


def list_installed_apps():
    try:
        helper = _get_helper("AppLauncher")
        return list(helper.listInstalledApps())
    except Exception as e:
        return []


# ===== الإشعارات =====
def get_notifications(filter_pkg="", limit=30):
    """يُرجع الإشعارات كـ JSON string."""
    try:
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return NotifReader.getActiveNotificationsJson(filter_pkg, limit)
    except Exception as e:
        log.error(f"get_notifications error: {e}")
        return "[]"


def is_notification_access_enabled():
    try:
        NotifReader = jclass("com.example.myfirstapp.NotifReader")
        return NotifReader.isEnabled(_context)
    except Exception:
        return False


# ===== SMS =====
def get_sms(limit=10, search=""):
    try:
        helper = _get_helper("SmsReader")
        return helper.getSmsJson(limit, search)
    except Exception as e:
        return "[]"


# ===== جهات الاتصال =====
def get_contacts(search=""):
    try:
        helper = _get_helper("ContactReader")
        return helper.getContactsJson(search)
    except Exception as e:
        return "[]"


# ===== البطارية =====
def get_battery():
    try:
        helper = _get_helper("BatteryHelper")
        return helper.getBatteryJson()
    except Exception as e:
        return "{}"


# ===== الحافظة =====
def get_clipboard():
    try:
        helper = _get_helper("ClipboardHelper")
        return helper.getClipboardText()
    except Exception as e:
        return ""


# ===== Toast =====
def show_toast(text):
    try:
        helper = _get_helper("ToastHelper")
        helper.showToast(text)
        return True
    except Exception as e:
        return False


# ===== الكاميرا =====
def capture_camera(camera_id=0):
    """يلتقط صورة بالكاميرا."""
    try:
        helper = _get_helper("CameraHelper")
        return helper.capturePhoto(camera_id) or ""
    except Exception as e:
        log.error(f"capture_camera error: {e}")
        return ""


# ===== لقطة الشاشة =====
def capture_screen():
    try:
        helper = _get_helper("ScreenCapture")
        return helper.capture() or ""
    except Exception as e:
        return ""


# ===== فتح إعدادات الإشعارات =====
def open_notification_settings():
    try:
        helper = _get_helper("AppLauncher")
        return helper.openNotificationSettings()
    except Exception as e:
        return f"❌ {e}"


# ===== معلومات =====
def get_device_info():
    """يُرجع معلومات الجهاز."""
    try:
        from java.lang import System
        from android.os import Build
        return {
            "model": str(Build.MODEL),
            "manufacturer": str(Build.MANUFACTURER),
            "android": str(Build.VERSION.RELEASE),
            "sdk": int(Build.VERSION.SDK_INT),
        }
    except Exception as e:
        return {"error": str(e)}