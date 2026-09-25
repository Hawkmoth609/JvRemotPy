"""
Main entry point for JvRemotPy.
Handles Discord bot operations with proper Intents.
"""

import sys
import os

# Add current directory to path so we can import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ✅ إصلاح الخطأ 2: استيراد Intents (ضرورية لـ discord.py 2.x)
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError as e:
    print(f"discord.py not available: {e}")
    DISCORD_AVAILABLE = False


def get_version():
    """Returns the current version of the script."""
    return "1.1.0"


def run(message=""):
    """دالة اختبار بسيطة (تعمل بدون Discord)."""
    return f"مرحباً من Python! الإصدار: {get_version()}. رسالتك: {message}"


def run_bot(token=None):
    """
    ✅ إصلاح الخطأ 2: تشغيل بوت Discord مع Intents الصحيحة.

    الخطأ السابق "The application did not respond" سببه:
    - عدم تفعيل message_content intent.
    - عدم معالجة الأخطاء داخل الأوامر.

    الحلول المطبقة:
    1. تفعيل Intents المناسبة.
    2. إضافة معالجة أخطاء شاملة (on_command_error).
    3. إضافة on_ready و on_message للتشخيص.
    4. إرجاع رد فوري لكل أمر.
    """
    if not DISCORD_AVAILABLE:
        return "خطأ: مكتبة discord.py غير متوفرة"

    if not token:
        return "خطأ: التوكن مطلوب"

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

    # ✅ معالجة الأخطاء داخل الأوامر (يمنع "The application did not respond")
    @bot.event
    async def on_command_error(ctx, error):
        print(f"❌ Command error: {error}")
        try:
            await ctx.send(f"حدث خطأ: {error}")
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
        return "تم إيقاف البوت"
    except Exception as e:
        error_msg = f"فشل تشغيل البوت: {e}"
        print(error_msg)
        return error_msg


if __name__ == "__main__":
    # للاختبار المحلي فقط
    print(run("اختبار"))
