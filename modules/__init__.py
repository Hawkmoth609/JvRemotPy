"""
╔══════════════════════════════════════════════════════════════════╗
║                     JvRemotPy Modules Package                    ║
║                                                                  ║
║  يحتوي على الدوال المساعدة التي يستخدمها:                        ║
║    • hawkmoth_bot.py                                             ║
║    • main.py                                                     ║
║    • bridge.py                                                   ║
╚══════════════════════════════════════════════════════════════════╝
"""

__version__ = "2.0.0"
__package_name__ = "modules"
__description__ = "Helper utilities for JvRemotPy"


# ═══════════════════════════════════════════════════════════════════
#                       EXPOSE PUBLIC API
# ═══════════════════════════════════════════════════════════════════

try:
    from .helpers import (
        # Time
        get_timestamp,
        get_local_timestamp,
        get_unix_time,
        format_duration,
        parse_duration,
        is_older_than,

        # Numbers
        safe_int,
        safe_float,
        safe_bool,
        clamp,
        format_size,
        format_number,
        percentage,

        # Strings
        truncate,
        safe_str,
        sanitize_filename,
        slugify,
        pluralize,

        # Dict / JSON
        format_result,
        safe_get,
        safe_json_loads,
        safe_json_dumps,
        deep_merge,
        flatten_dict,

        # Files
        get_extension,
        get_filename,
        get_parent_dir,
        file_exists,
        dir_exists,
        get_file_size,
        ensure_dir,
        is_safe_path,

        # Hash
        md5_hash,
        sha256_hash,
        file_md5,
        short_hash,

        # Classes
        Counter,

        # Status
        ok,
        error,
        success_text,
        error_text,
        warning_text,
        info_text,

        # Lists
        chunk_list,
        unique_list,
        safe_first,
    )
except ImportError:
    # في حال استخدام الوحدة من خارج الحزمة
    from helpers import (
        get_timestamp,
        get_local_timestamp,
        get_unix_time,
        format_duration,
        parse_duration,
        is_older_than,
        safe_int,
        safe_float,
        safe_bool,
        clamp,
        format_size,
        format_number,
        percentage,
        truncate,
        safe_str,
        sanitize_filename,
        slugify,
        pluralize,
        format_result,
        safe_get,
        safe_json_loads,
        safe_json_dumps,
        deep_merge,
        flatten_dict,
        get_extension,
        get_filename,
        get_parent_dir,
        file_exists,
        dir_exists,
        get_file_size,
        ensure_dir,
        is_safe_path,
        md5_hash,
        sha256_hash,
        file_md5,
        short_hash,
        Counter,
        ok,
        error,
        success_text,
        error_text,
        warning_text,
        info_text,
        chunk_list,
        unique_list,
        safe_first,
    )


# ═══════════════════════════════════════════════════════════════════
#                       EXPORTS
# ═══════════════════════════════════════════════════════════════════

__all__ = [
    "__version__",
    "__package_name__",
    "__description__",

    # Time
    "get_timestamp", "get_local_timestamp", "get_unix_time",
    "format_duration", "parse_duration", "is_older_than",

    # Numbers
    "safe_int", "safe_float", "safe_bool", "clamp",
    "format_size", "format_number", "percentage",

    # Strings
    "truncate", "safe_str", "sanitize_filename", "slugify", "pluralize",

    # Dict / JSON
    "format_result", "safe_get", "safe_json_loads", "safe_json_dumps",
    "deep_merge", "flatten_dict",

    # Files
    "get_extension", "get_filename", "get_parent_dir",
    "file_exists", "dir_exists", "get_file_size", "ensure_dir", "is_safe_path",

    # Hash
    "md5_hash", "sha256_hash", "file_md5", "short_hash",

    # Classes
    "Counter",

    # Status
    "ok", "error", "success_text", "error_text", "warning_text", "info_text",

    # Lists
    "chunk_list", "unique_list", "safe_first",
]
