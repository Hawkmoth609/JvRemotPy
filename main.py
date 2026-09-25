"""
Main entry point for JvRemotPy.
Handles Discord bot operations with proper Intents and error handling.
"""

import sys
import os
import asyncio
import threading

# Add current directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ✅ استيراد مكتبات Discord مع معالجة الأخطاء
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError as e:
    print(f"❌ discord.py not available: {e}")
    DISCORD_AVAILABLE = False


def get_version():
    """Returns the current version of the script."""
    return "2.0.0"


def run(message=""):
    """دالة اختبار بسيطة (تعمل بدون Discord)."""
    return f"🎉 تم التحديث من GitHub! الإصدار: {get_version()}. رسالتك: {message}"


def run_bot(token=None):
    """
    ✅ دالة تشغيل بوت Discord (كانت مفقودة تمامًا!).
    
    الخطأ السابق "The application did not respond" سببه:
    1. عدم وجود هذه الدالة أصلاً.
    2. عدم تفعيل message_content intent.
    3. عدم معالجة الأخطاء داخل الأوامر.
    
    الحلول المطبقة:
    1. إنشاء النوايا (Intents) المناسبة.
    2. إضافة on_ready للتشخيص.
    3. إضافة on_command_error لمعالجة الأخطاء.
    4. تشغيل البوت في حلقة غير متزامنة.
    """
    if not DISCORD_AVAILABLE:
        msg = "❌ خطأ: مكتبة discord.py غير متوفرة"
        print(msg)
        return msg

    if not token:
        msg = "❌ خطأ: التوكن مطلوب"
        print(msg)
        return msg

    print(f"🚀 بدء تشغيل البوت... (Python {sys.version.split()[0]})")

    # ✅ إنشاء النوايا (Intents) — ضروري لـ discord.py 2.x
    intents = discord.Intents.default()
    intents.message_content = True   # قراءة محتوى الرسائل (إلزامي للأوامر النصية)
    intents.messages = True          # استقبال الرسائل
    intents.guilds = True            # استقبال معلومات السيرفرات

    bot = commands.Bot(command_prefix="!", intents=intents)

    # ✅ حدث عند اتصال البوت بنجاح
    @bot.event
    async def on_ready():
        print(f"✅ Bot logged in as {bot.user}")
        print(f"✅ Connected to {len(bot.guilds)} guild(s)")
        for guild in bot.guilds:
            print(f"   - {guild.name} (id: {guild.id})")
        print("🎉 البوت جاهز لاستقبال الأوامر")

    # ✅ معالجة الأخطاء داخل الأوامر (يمنع "The application did not respond")
    @bot.event
    async def on_command_error(ctx, error):
        print(f"❌ Command error: {error}")
        try:
            await ctx.send(f"⚠️ حدث خطأ: {error}")
        except Exception as e:
            print(f"Failed to send error message: {e}")

    # ✅ أمر بسيط للاختبار
    @bot.command(name="ping")
    async def ping_cmd(ctx):
        await ctx.send("Pong! 🏓")

    # ✅ أمر ترحيب
    @bot.command(name="hello")
    async def hello_cmd(ctx):
        await ctx.send(f"مرحباً {ctx.author.name}! 👋")

    # ✅ أمر يعرض الإصدار
    @bot.command(name="version")
    async def version_cmd(ctx):
        await ctx.send(f"الإصدار: {get_version()}")

    # ✅ تشغيل البوت
    try:
        bot.run(token)
        return "✅ تم إيقاف البوت"
    except discord.LoginFailure:
        msg = "❌ فشل تسجيل الدخول: التوكن غير صحيح"
        print(msg)
        return msg
    except discord.PrivilegedIntentsRequired:
        msg = "❌ خطأ: يجب تفعيل 'Message Content Intent' في Discord Developer Portal"
        print(msg)
        return msg
    except Exception as e:
        error_msg = f"❌ فشل تشغيل البوت: {e}"
        print(error_msg)
        return error_msg


if __name__ == "__main__":
    # للاختبار المحلي فقط
    print(run("اختبار"))
