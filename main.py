"""
Main entry point for JvRemotPy.
Handles Discord bot operations with proper Intents.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# استيراد discord مع معالجة الأخطاء
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError as e:
    print(f"discord.py not available: {e}")
    DISCORD_AVAILABLE = False


def get_version():
    return "2.0.0"


def run(message=""):
    """دالة اختبار بسيطة."""
    return f"🎉 الإصدار: {get_version()}. رسالتك: {message}"


def run_bot(token=None):
    """
    تشغيل بوت Discord — الدالة التي يستدعيها BotService.java.
    """
    if not DISCORD_AVAILABLE:
        return "❌ مكتبة discord.py غير متوفرة"

    if not token:
        return "❌ التوكن مطلوب"

    print(f"🚀 بدء تشغيل البوت... (Python {sys.version.split()[0]})")

    # ✅ النوايا (Intents) — ضرورية لعمل discord.py 2.x
    intents = discord.Intents.default()
    intents.message_content = True   # الأهم: قراءة محتوى الرسائل
    intents.messages = True
    intents.guilds = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        print(f"✅ Bot logged in as {bot.user}")
        print(f"✅ Connected to {len(bot.guilds)} guild(s)")

    @bot.event
    async def on_command_error(ctx, error):
        print(f"❌ Command error: {error}")
        try:
            await ctx.send(f"⚠️ خطأ: {error}")
        except Exception:
            pass

    @bot.command(name="ping")
    async def ping_cmd(ctx):
        await ctx.send("Pong! 🏓")

    @bot.command(name="hello")
    async def hello_cmd(ctx):
        await ctx.send(f"مرحباً {ctx.author.name}! 👋")

    @bot.command(name="version")
    async def version_cmd(ctx):
        await ctx.send(f"الإصدار: {get_version()}")

    try:
        bot.run(token)
        return "✅ تم إيقاف البوت"
    except discord.LoginFailure:
        return "❌ التوكن غير صحيح"
    except discord.PrivilegedIntentsRequired:
        return "❌ يجب تفعيل Message Content Intent في Discord Developer Portal"
    except Exception as e:
        return f"❌ خطأ: {e}"


if __name__ == "__main__":
    print(run("اختبار"))
