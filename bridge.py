"""
bridge.py - v6.0 (الجسر الكامل مع كل الصلاحيات الجديدة)

⛔ محذوف: SMS، Notifications
✅ مضاف: CallLog، Location، Audio، Phone، Accounts، Sensors
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
    global _context, _activity, _service

    _context = context
    clear_helper_cache()

    if context is None:
        _activity = None
        _service = None
        log.info("Context cleared")
        return

    try:
        if hasattr(context, 'getParentActivityIntent'):
            _activity = context
            _service = None
            log.info("Context type: Activity")
            return
    except Exception:
        pass

    try:
        if hasattr(context, 'onBind'):
            _service = context
            _activity = None
            log.info("Context type: Service")
            return
    except Exception:
        pass

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
        return f"❌ خطأ: {e}"


def open_whatsapp_home() -> str:
    try:
        return _get_helper("AppLauncher").openWhatsappHome()
    except Exception as e:
        return f"❌ خطأ: {e}"


def dial(phone: str) -> str:
    try:
        return _get_helper("AppLauncher").dial(phone)
    except Exception as e:
        return f"❌ خطأ: {e}"


def open_file(path: str) -> str:
    try:
        return _get_helper("AppLauncher").openFile(path)
    except Exception as e:
        return f"❌ خطأ: {e}"


def list_installed_apps() -> List[str]:
    try:
        helper = _get_helper("AppLauncher")
        result = helper.listInstalledApps()
        return list(result) if result else []
    except Exception as e:
        return []


def open_camera_app() -> str:
    try:
        return _get_helper("AppLauncher").openCameraApp()
    except Exception as e:
        return f"❌ خطأ: {e}"


# ==========================================================
# ⛔ SMS — معطّلة
# ==========================================================
def get_sms(limit: int = 10, search: str = "") -> str:
    log.warning("get_sms: disabled (permission removed)")
    return "[]"


def send_sms(phone: str, text: str) -> str:
    return "❌ الميزة معطّلة (تم حذف صلاحية الرسائل)"


# ==========================================================
# ⛔ الإشعارات — معطّلة
# ==========================================================
def get_notifications(filter_pkg: str = "", limit: int = 30) -> str:
    log.warning("get_notifications: disabled")
    return '{"status":"disabled","notifications":[]}'


def is_notification_access_enabled() -> bool:
    return False


def open_notification_settings() -> str:
    return "❌ الميزة معطّلة"


# ==========================================================
# ✅ جهات الاتصال
# ==========================================================
def get_contacts(search: str = "") -> str:
    try:
        helper = _get_helper("ContactReader")
        return helper.getContactsJson(search or "")
    except Exception as e:
        log.error(f"get_contacts: {e}")
        return "[]"


# ==========================================================
# ✅ البطارية
# ==========================================================
def get_battery() -> str:
    try:
        return _get_helper("BatteryHelper").getBatteryJson()
    except Exception as e:
        return "{}"


# ==========================================================
# ✅ الحافظة
# ==========================================================
def get_clipboard() -> str:
    try:
        return _get_helper("ClipboardHelper").getClipboardText() or ""
    except Exception as e:
        return ""


# ==========================================================
# ✅ Toast
# ==========================================================
def show_toast(text: str) -> bool:
    try:
        _get_helper("ToastHelper").showToast(text)
        return True
    except Exception as e:
        return False


# ==========================================================
# ✅ الكاميرا
# ==========================================================
def capture_camera(camera_id: int = 0) -> str:
    try:
        return _get_helper("CameraHelper").capturePhoto(int(camera_id)) or ""
    except Exception as e:
        return ""


# ==========================================================
# ✅ لقطة الشاشة
# ==========================================================
def capture_screen() -> str:
    try:
        return _get_helper("ScreenCapture").capture() or ""
    except Exception as e:
        return ""


# ==========================================================
# ✅ سجل المكالمات (جديد)
# ==========================================================
def get_call_log(limit: int = 50, type_filter: str = "all",
                 search: str = "") -> str:
    """يُرجع سجل المكالمات كـ JSON."""
    try:
        helper = _get_helper("CallLogHelper")
        return helper.getCallLogJson(int(limit),
                                     type_filter or "all",
                                     search or "")
    except Exception as e:
        log.error(f"get_call_log: {e}")
        return "[]"


def get_missed_calls_count() -> int:
    """عدد المكالمات الفائتة الجديدة."""
    try:
        helper = _get_helper("CallLogHelper")
        return int(helper.getMissedCount())
    except Exception as e:
        return 0


# ==========================================================
# ✅ الموقع (جديد)
# ==========================================================
def get_location() -> str:
    """آخر موقع معروف كـ JSON."""
    try:
        helper = _get_helper("LocationHelper")
        return helper.getLastKnownLocationJson()
    except Exception as e:
        log.error(f"get_location: {e}")
        return "{}"


def is_gps_enabled() -> bool:
    try:
        helper = _get_helper("LocationHelper")
        return bool(helper.isGpsEnabled())
    except Exception as e:
        return False


def get_location_providers() -> str:
    try:
        helper = _get_helper("LocationHelper")
        return helper.getProvidersStatusJson()
    except Exception as e:
        return "{}"


# ==========================================================
# ✅ الميكروفون — تسجيل الصوت (جديد)
# ==========================================================
def start_audio_recording(duration_sec: int = 10) -> str:
    """يبدأ تسجيل الصوت."""
    try:
        helper = _get_helper("AudioRecorder")
        return helper.startRecording(int(duration_sec))
    except Exception as e:
        log.error(f"start_audio_recording: {e}")
        return f"❌ {e}"


def stop_audio_recording() -> str:
    """يوقف التسجيل — يعيد المسار."""
    try:
        helper = _get_helper("AudioRecorder")
        return helper.stopRecording() or ""
    except Exception as e:
        return ""


def is_audio_recording() -> bool:
    try:
        helper = _get_helper("AudioRecorder")
        return bool(helper.isRecording())
    except Exception as e:
        return False


def get_recording_duration() -> int:
    try:
        helper = _get_helper("AudioRecorder")
        return int(helper.getRecordingDuration())
    except Exception as e:
        return 0


# ==========================================================
# ✅ معلومات الهاتف (جديد)
# ==========================================================
def get_phone_info() -> str:
    """معلومات الشبكة و SIM كـ JSON."""
    try:
        helper = _get_helper("PhoneHelper")
        return helper.getPhoneInfoJson()
    except Exception as e:
        log.error(f"get_phone_info: {e}")
        return "{}"


def call_number(phone: str) -> str:
    """إجراء مكالمة مباشرة — يحتاج CALL_PHONE."""
    try:
        helper = _get_helper("PhoneHelper")
        return helper.callNumber(phone)
    except Exception as e:
        return f"❌ {e}"


def has_call_permission() -> bool:
    try:
        helper = _get_helper("PhoneHelper")
        return bool(helper.hasCallPermission())
    except Exception as e:
        return False


# ==========================================================
# ✅ الحسابات (جديد)
# ==========================================================
def get_accounts(filter_type: str = "") -> str:
    """قائمة الحسابات كـ JSON."""
    try:
        helper = _get_helper("AccountsHelper")
        return helper.getAccountsJson(filter_type or "")
    except Exception as e:
        log.error(f"get_accounts: {e}")
        return "[]"


def get_accounts_count(filter_type: str = "") -> int:
    try:
        helper = _get_helper("AccountsHelper")
        return int(helper.getAccountCount(filter_type or ""))
    except Exception as e:
        return 0


# ==========================================================
# ✅ المستشعرات (جديد)
# ==========================================================
def list_sensors() -> str:
    """قائمة كل المستشعرات."""
    try:
        helper = _get_helper("SensorHelper")
        return helper.listSensorsJson()
    except Exception as e:
        return "[]"


def read_heart_rate() -> str:
    """قراءة نبضات القلب."""
    try:
        helper = _get_helper("SensorHelper")
        return helper.readHeartRateJson()
    except Exception as e:
        return "{}"


def read_step_counter() -> str:
    """قراءة عدد الخطوات."""
    try:
        helper = _get_helper("SensorHelper")
        return helper.readStepCounterJson()
    except Exception as e:
        return "{}"


def read_accelerometer() -> str:
    try:
        helper = _get_helper("SensorHelper")
        return helper.readAccelerometerJson()
    except Exception as e:
        return "{}"


def read_gyroscope() -> str:
    try:
        helper = _get_helper("SensorHelper")
        return helper.readGyroscopeJson()
    except Exception as e:
        return "{}"


# ==========================================================
# ✅ الصلاحيات
# ==========================================================
def _get_permission_manager():
    if _context is None:
        raise RuntimeError("Context not set")
    PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
    return PermissionManager(_context)


def get_permissions_json() -> str:
    if _context is None:
        return "{}"
    try:
        helper = _get_permission_manager()
        return helper.getPermissionsJson()
    except Exception as e:
        log.error(f"get_permissions_json: {e}")
        return "{}"


def has_all_files_access() -> bool:
    if _context is None:
        return False
    try:
        return bool(_get_permission_manager().hasAllFilesAccess())
    except Exception as e:
        return False


def has_notification_access() -> bool:
    return False


# ==========================================================
# ✅ اختبار التخزين
# ==========================================================
def test_storage_access() -> str:
    import os as _os
    results = {}
    test_paths = [
        "/storage/emulated/0",
        "/sdcard",
        "/storage/emulated/0/Download",
        "/storage/emulated/0/DCIM",
        "/storage/emulated/0/Pictures",
    ]

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


log.info("bridge.py loaded - v6.0 (full permissions)")
