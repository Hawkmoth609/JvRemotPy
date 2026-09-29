"""
bridge.py - v8.0 (الجسر الشامل المُحسَّن)

⛔ محذوف: SMS، Notifications
✅ مضاف: CallLog، Location، Audio، Phone، Accounts، Sensors

التحسينات الجوهرية:
  • Context-generation tracking لمنع stale cache
  • _get_helper مع force_new + error logging
  • دوال فحص صلاحية قبل كل عملية
  • دوال إحصائيات (call_log_stats, accounts_stats)
  • diagnose() شاملة للتشخيص
  • رسائل خطأ أوضح مع إرشادات
  • get_recording_path() للحصول على مسار التسجيل الحالي
  • dial_number() كبديل بدون صلاحية CALL_PHONE
"""

import logging
import json
import os
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
_context_generation = 0


# ==========================================================
# ضبط السياق
# ==========================================================
def set_context(context) -> None:
    """يحفظ Context من Java + يمسح الـ cache."""
    global _context, _activity, _service, _context_generation

    _context = context
    _context_generation += 1
    clear_helper_cache()

    if context is None:
        _activity = None
        _service = None
        log.info("Context cleared (gen=%d)", _context_generation)
        return

    try:
        if hasattr(context, 'getParentActivityIntent'):
            _activity = context
            _service = None
            log.info("Context type: Activity (gen=%d)", _context_generation)
            return
    except Exception:
        pass

    try:
        if hasattr(context, 'onBind'):
            _service = context
            _activity = None
            log.info("Context type: Service (gen=%d)", _context_generation)
            return
    except Exception:
        pass

    _activity = None
    _service = None
    log.info("Context type: Application/Other (gen=%d)", _context_generation)


def get_context():
    return _context


def get_activity():
    return _activity


def get_service():
    return _service


def get_context_generation() -> int:
    return _context_generation


# ==========================================================
# Helper Cache
# ==========================================================
def _get_helper(class_name: str, force_new: bool = False) -> Any:
    """يُنشئ أو يعيد helper من Java (مع caching)."""
    global _helper_cache

    if _context is None:
        raise RuntimeError("Context not set. Call set_context() first.")

    if not force_new and class_name in _helper_cache:
        return _helper_cache[class_name]

    try:
        HelperClass = jclass(f"com.example.myfirstapp.{class_name}")
        helper = HelperClass(_context)
        _helper_cache[class_name] = helper
        log.debug("Helper created: %s (gen=%d)", class_name, _context_generation)
        return helper
    except Exception as e:
        log.error("Failed to create helper %s: %s", class_name, e)
        raise


def clear_helper_cache():
    """يمسح cache الـ helpers."""
    global _helper_cache
    old_size = len(_helper_cache)
    _helper_cache = {}
    log.info("Helper cache cleared (%d items)", old_size)


def get_cached_helpers() -> List[str]:
    """يُرجع قائمة الـ helpers المخزنة."""
    return list(_helper_cache.keys())


# ==========================================================
# Wrapper helpers
# ==========================================================
def _safe_json(data, fallback: str = "{}") -> str:
    """يضمن أن الناتج JSON صالح."""
    if data is None:
        return fallback
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return fallback


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
        log.error(f"list_installed_apps: {e}")
        return []


def open_camera_app() -> str:
    try:
        return _get_helper("AppLauncher").openCameraApp()
    except Exception as e:
        return f"❌ خطأ: {e}"


# ==========================================================
# ⛔ SMS — معطّلة (Play Protect)
# ==========================================================
def get_sms(limit: int = 10, search: str = "") -> str:
    log.warning("get_sms: disabled (permission removed)")
    return "[]"


def send_sms(phone: str, text: str) -> str:
    return "❌ الميزة معطّلة (تم حذف صلاحية الرسائل)"


# ==========================================================
# ⛔ الإشعارات — معطّلة (Play Protect)
# ==========================================================
def get_notifications(filter_pkg: str = "", limit: int = 30) -> str:
    log.warning("get_notifications: disabled")
    return '{"status":"disabled","notifications":[]}'


def is_notification_access_enabled() -> bool:
    return False


def open_notification_settings() -> str:
    return "❌ الميزة معطّلة"


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
        return "{}"


# ==========================================================
# الحافظة
# ==========================================================
def get_clipboard() -> str:
    try:
        return _get_helper("ClipboardHelper").getClipboardText() or ""
    except Exception as e:
        return ""


# ==========================================================
# Toast
# ==========================================================
def show_toast(text: str) -> bool:
    try:
        _get_helper("ToastHelper").showToast(text)
        return True
    except Exception as e:
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


def capture_screen() -> str:
    try:
        return _get_helper("ScreenCapture").capture() or ""
    except Exception as e:
        return ""


# ==========================================================
# ✅ سجل المكالمات
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


def get_call_log_stats() -> str:
    """إحصائيات سجل المكالمات."""
    try:
        helper = _get_helper("CallLogHelper")
        return helper.getStatsJson()
    except Exception as e:
        log.error(f"get_call_log_stats: {e}")
        return "{}"


def get_missed_calls_count() -> int:
    """عدد المكالمات الفائتة الجديدة."""
    try:
        helper = _get_helper("CallLogHelper")
        return int(helper.getMissedCount())
    except Exception as e:
        return 0


def has_call_log_permission() -> bool:
    """فحص صلاحية سجل المكالمات."""
    try:
        helper = _get_helper("CallLogHelper")
        return bool(helper.hasCallLogPermission())
    except Exception as e:
        return False


# ==========================================================
# ✅ الموقع
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


def has_location_permission() -> bool:
    try:
        helper = _get_helper("LocationHelper")
        return bool(helper.hasLocationPermission())
    except Exception as e:
        return False


# ==========================================================
# ✅ الميكروفون — تسجيل الصوت
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
        log.error(f"stop_audio_recording: {e}")
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


def get_recording_path() -> str:
    """مسار التسجيل الحالي."""
    try:
        helper = _get_helper("AudioRecorder")
        return str(helper.getCurrentFilePath() or "")
    except Exception as e:
        return ""


def has_audio_permission() -> bool:
    """فحص صلاحية الميكروفون."""
    try:
        helper = _get_helper("AudioRecorder")
        return bool(helper.hasAudioPermission())
    except Exception:
        # fallback: فحص يدوي عبر PermissionManager
        try:
            return bool(_get_permission_manager().hasRecordAudio())
        except Exception:
            return False


# ==========================================================
# ✅ معلومات الهاتف والمكالمات
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
        log.error(f"call_number: {e}")
        return f"❌ {e}"


def dial_number(phone: str) -> str:
    """فتح لوحة الاتصال (بدون صلاحية CALL_PHONE)."""
    try:
        helper = _get_helper("PhoneHelper")
        return helper.dialNumber(phone)
    except Exception as e:
        return f"❌ {e}"


def has_call_permission() -> bool:
    try:
        helper = _get_helper("PhoneHelper")
        return bool(helper.hasCallPermission())
    except Exception as e:
        return False


# ==========================================================
# ✅ الحسابات
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


def get_accounts_stats() -> str:
    """إحصائيات الحسابات."""
    try:
        helper = _get_helper("AccountsHelper")
        return helper.getAccountsStatsJson()
    except Exception as e:
        log.error(f"get_accounts_stats: {e}")
        return "{}"


def has_accounts_permission() -> bool:
    """فحص صلاحية GET_ACCOUNTS."""
    try:
        helper = _get_helper("AccountsHelper")
        return bool(helper.hasAccountsPermission())
    except Exception as e:
        return False


# ==========================================================
# ✅ المستشعرات
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
    """كل الصلاحيات كـ JSON."""
    if _context is None:
        return "{}"
    try:
        helper = _get_permission_manager()
        return helper.getPermissionsJson()
    except Exception as e:
        log.error(f"get_permissions_json: {e}")
        return "{}"


def get_missing_permissions() -> str:
    """قائمة الصلاحيات الناقصة كـ JSON."""
    if _context is None:
        return "{}"
    try:
        helper = _get_permission_manager()
        return helper.getMissingPermissionsJson()
    except Exception as e:
        return "{}"


def has_all_files_access() -> bool:
    if _context is None:
        return False
    try:
        return bool(_get_permission_manager().hasAllFilesAccess())
    except Exception as e:
        return False


def has_camera_permission() -> bool:
    if _context is None:
        return False
    try:
        return bool(_get_permission_manager().hasCamera())
    except Exception:
        return False


def has_contacts_permission() -> bool:
    if _context is None:
        return False
    try:
        return bool(_get_permission_manager().hasReadContacts())
    except Exception:
        return False


def has_notification_access() -> bool:
    """⛔ معطّلة — تُرجع False دائمًا."""
    return False


def get_permission_score() -> int:
    """درجة الصلاحيات (0-100)."""
    if _context is None:
        return 0
    try:
        return int(_get_permission_manager().getPermissionScore())
    except Exception:
        return 0


def get_permission_level() -> str:
    """مستوى الصلاحيات النصي."""
    if _context is None:
        return "unknown"
    try:
        return str(_get_permission_manager().getPermissionLevel())
    except Exception:
        return "unknown"


# ==========================================================
# ✅ اختبار التخزين
# ==========================================================
def test_storage_access() -> str:
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
            if os.path.isdir(p):
                try:
                    files = os.listdir(p)
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
# ✅ التشخيص الشامل — جديد
# ==========================================================
def diagnose() -> str:
    """
    تقرير تشخيصي شامل.
    يفحص: السياق، الـ helpers، الصلاحيات، الميزات.
    """
    report = {
        "context": {},
        "permissions": {},
        "features": {},
        "helpers": {},
        "errors": [],
    }

    # 1. السياق
    try:
        report["context"] = {
            "ready": _context is not None,
            "type": get_context_type(),
            "generation": _context_generation,
        }
    except Exception as e:
        report["errors"].append(f"context: {e}")

    # 2. الصلاحيات
    try:
        perms_json = get_permissions_json()
        report["permissions"] = json.loads(perms_json) if perms_json else {}
    except Exception as e:
        report["errors"].append(f"permissions: {e}")

    # 3. الميزات
    features = {}
    try:
        features["all_files"] = has_all_files_access()
    except Exception as e:
        report["errors"].append(f"all_files: {e}")
    try:
        features["call_log"] = has_call_log_permission()
    except Exception as e:
        report["errors"].append(f"call_log: {e}")
    try:
        features["location"] = has_location_permission()
    except Exception as e:
        report["errors"].append(f"location: {e}")
    try:
        features["audio"] = has_audio_permission()
    except Exception as e:
        report["errors"].append(f"audio: {e}")
    try:
        features["accounts"] = has_accounts_permission()
    except Exception as e:
        report["errors"].append(f"accounts: {e}")
    try:
        features["call_phone"] = has_call_permission()
    except Exception as e:
        report["errors"].append(f"call_phone: {e}")
    report["features"] = features

    # 4. الـ helpers
    for name in ["AppLauncher", "ContactReader", "BatteryHelper",
                 "ClipboardHelper", "ToastHelper", "CameraHelper",
                 "CallLogHelper", "LocationHelper", "AudioRecorder",
                 "PhoneHelper", "AccountsHelper", "SensorHelper"]:
        try:
            _get_helper(name)
            report["helpers"][name] = "✅"
        except Exception as e:
            report["helpers"][name] = f"❌ {e}"

    return json.dumps(report, ensure_ascii=False, indent=2)


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
        "context_generation": _context_generation,
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
log.info("bridge.py loaded - v8.0 (comprehensive)")
