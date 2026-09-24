"""
Main entry point for JvRemotPy.
This script is loaded dynamically from GitHub into the Android app.
"""

import sys
import os

# Add current directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_version():
    """Returns the current version of the script."""
    return "1.0.0"


def run(message=""):
    """
    Main function called from the Android app.
    Returns a greeting message.
    """
    return f"مرحباً من Python! الإصدار: {get_version()}. رسالتك: {message}"


def process_data(data):
    """
    Example data processing function.
    Returns a dict with the processing result.
    """
    if data is None:
        return {"status": "error", "message": "No data provided"}

    return {
        "status": "ok",
        "original": str(data),
        "processed": str(data).upper(),
        "length": len(str(data))
    }


def get_info():
    """Returns info about the Python environment."""
    return {
        "version": get_version(),
        "python_version": sys.version,
        "platform": sys.platform
    }


if __name__ == "__main__":
    # This runs only when the script is executed directly (not from Android)
    print(run("اختبار محلي"))
    print(process_data("hello world"))
    print(get_info())
