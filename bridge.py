"""
bridge.py - v3.0 (الإصلاح)
"""

import logging
import json
from typing import Any, Optional, List, Dict
from java import jclass

log = logging.getLogger("bridge")

_context = None
_activity = None
_service = None
_helper_cache: Dict[str, Any] = {}


def set_context(context) -> None:
    """يحفظ Context من Java — مع مسح cache القديم."""
    global _context, _activity, _service

    _context = context
    clear_helper_cache()   # ✅ إصلاح: مسح cache عند تغيير السياق

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
    log.info("Context type: Application/Context")


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


# ... (باقي الدوال بدون تغيير — أبقِها كما هي)

def get_permissions_json() -> str:
    """✅ الإصلاح: نمرر _context مباشرة (يقبل Context الآن)."""
    if _context is None:
        return "{}"
    try:
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(_context)   # ← Context مباشرة
        return helper.getPermissionsJson()
    except Exception as e:
        log.error(f"get_permissions_json: {e}")
        return "{}"


def has_all_files_access() -> bool:
    try:
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(_context)
        return bool(helper.hasAllFilesAccess())
    except Exception as e:
        log.error(f"has_all_files_access: {e}")
        return False


def has_notification_access() -> bool:
    try:
        PermissionManager = jclass("com.example.myfirstapp.PermissionManager")
        helper = PermissionManager(_context)
        return bool(helper.hasNotificationAccess())
    except Exception as e:
        log.error(f"has_notification_access: {e}")
        return False


# ... (باقي الدوال كما هي في النسخة الحالية)
