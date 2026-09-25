"""
╔══════════════════════════════════════════════════════════════════╗
║                      JvRemotPy — Core Engine                     ║
║              Python Runtime for Android (Chaquopy)               ║
║                                                                  ║
║  Version: 3.0.0                                                  ║
║  Features:                                                       ║
║    • Discord Bot with full Intents support                       ║
║    • Graceful error handling & recovery                          ║
║    • Thread-safe async execution                                 ║
║    • Environment auto-detection (Android / Desktop)              ║
║    • Extensible command system                                   ║
║    • Detailed logging for Android Logcat                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import traceback
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Callable

# ═══════════════════════════════════════════════════════════════════
#                       ENVIRONMENT SETUP
# ═══════════════════════════════════════════════════════════════════

# ضمان أن مجلد السكربتات في sys.path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


# ═══════════════════════════════════════════════════════════════════
#                       SAFE IMPORTS
# ═══════════════════════════════════════════════════════════════════

_discord = None
_commands = None
_tasks = None

try:
    import discord
    from discord.ext import commands, tasks
    _discord = discord
    _commands = commands
    _tasks = tasks
    DISCORD_AVAILABLE = True
    DISCORD_VERSION = getattr(discord, "__version__", "unknown")
except ImportError as e:
    DISCORD_AVAILABLE = False
    DISCORD_VERSION = "N/A"
    _IMPORT_ERROR = str(e)
else:
    _IMPORT_ERROR = None


# ═══════════════════════════════════════════════════════════════════
#                       CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

class BotConfig:
    """إعدادات قابلة للتخصيص لكل تشغيل."""

    def __init__(
        self,
        token: str,
        prefix: str = "!",
        enable_message_content: bool = True,
        enable_members: bool = False,
        enable_presences: bool = False,
        enable_all_intents: bool = False,
        log_level: str = "INFO",
    ):
        self.token = token
        self.prefix = prefix
        self.enable_message_content = enable_message_content
        self.enable_members = enable_members
        self.enable_presences = enable_presences
        self.enable_all_intents = enable_all_intents
        self.log_level = log_level

    def __repr__(self):
        return (
            f"BotConfig(prefix={self.prefix!r}, "
            f"intents={{msg={self.enable_message_content}, "
            f"members={self.enable_members}, presences={self.enable_presences}}})"
        )


# ═══════════════════════════════════════════════════════════════════
#                       LOGGER
# ═══════════════════════════════════════════════════════════════════

class Logger:
    """بسيط، موحّد، يعمل داخل Android Logcat."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(self, level: str = "INFO"):
        self.level_value = self.LEVELS.get(level.upper(), 20)

    def _log(self, level: str, msg: str):
        if self.LEVELS[level] < self.level_value:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        icon = {"DEBUG": "🔍", "INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌"}[level]
        print(f"[{ts}] {icon} [{level}] {msg}", flush=True)

    def debug(self, msg): self._log("DEBUG", msg)
    def info(self, msg):  self._log("INFO", msg)
    def warn(self, msg):  self._log("WARN", msg)
    def error(self, msg): self._log("ERROR", msg)

    def exception(self, msg, exc: Exception):
        self.error(f"{msg}: {exc}")
        print(traceback.format_exc(), flush=True)


log = Logger()


# ═══════════════════════════════════════════════════════════════════
#                       GLOBAL STATE
# ═══════════════════════════════════════════════════════════════════

class _State:
    """حالة عامة — لأن Chaquopy يستدعي run_bot عدة مرات."""
    bot = None
    is_running = False
    start_time: Optional[float] = None
    last_error: Optional[str] = None
    stop_event = threading.Event()

    @classmethod
    def reset(cls):
        cls.bot = None
        cls.is_running = False
        cls.start_time = None
        cls.stop_event = threading.Event()


# ═══════════════════════════════════════════════════════════════════
#                       CORE UTILITIES
# ═══════════════════════════════════════════════════════════════════

def get_version() -> str:
    """إرجاع إصدار السكربت."""
    return "3.0.0"


def get_environment_info() -> Dict[str, Any]:
    """معلومات شاملة عن البيئة."""
    return {
        "version": get_version(),
        "python_version": sys.version.split()[0],
        "python_full": sys.version,
        "platform": sys.platform,
        "is_android": "android" in sys.platform.lower() or hasattr(sys, "getandroidapilevel"),
        "discord_available": DISCORD_AVAILABLE,
        "discord_version": DISCORD_VERSION,
        "script_dir": _SCRIPT_DIR,
        "cwd": os.getcwd(),
        "timestamp": datetime.now().isoformat(),
    }


def validate_token(token: Optional[str]) -> tuple:
    """
    تحقق شامل من التوكن.
    Returns: (is_valid: bool, reason: str)
    """
    if not token:
        return False, "التوكن فارغ"

    if not isinstance(token, str):
        return False, "التوكن ليس نصًا"

    token = token.strip()

    if len(token) < 50:
        return False, f"التوكن قصير جدًا ({len(token)} حرف، المتوقع 70+)"

    # تنسيق Discord token: 3 أجزاء مفصولة بنقاط
    parts = token.split(".")
    if len(parts) != 3:
        return False, f"تنسيق التوكن غير صحيح ({len(parts)} أجزاء، المتوقع 3)"

    if not parts[0].isdigit():
        return False, "الجزء الأول من التوكن ليس رقمًا"

    return True, "صحيح"


def make_intents(config: BotConfig):
    """إنشاء Intents حسب الإعدادات."""
    if not DISCORD_AVAILABLE:
        return None

    intents = discord.Intents.default()

    if config.enable_all_intents:
        intents = discord.Intents.all()
    else:
        intents.message_content = config.enable_message_content
        intents.messages = True
        intents.guilds = True
        intents.members = config.enable_members
        intents.presences = config.enable_presences

    return intents


# ═══════════════════════════════════════════════════════════════════
#                       BOT BUILDER
# ═══════════════════════════════════════════════════════════════════

def create_bot(config: BotConfig):
    """
    إنشاء كائن البوت وتسجيل كل الأحداث والأوامر.
    """
    if not DISCORD_AVAILABLE:
        raise RuntimeError(f"discord.py غير متوفر: {_IMPORT_ERROR}")

    intents = make_intents(config)
    bot = commands.Bot(command_prefix=config.prefix, intents=intents)

    # ─────────────────────────────────────────────────────────────
    # Events
    # ─────────────────────────────────────────────────────────────

    @bot.event
    async def on_ready():
        _State.is_running = True
        _State.start_time = time.time()
        log.info(f"✅ Bot logged in as {bot.user} (ID: {bot.user.id})")
        log.info(f"✅ Connected to {len(bot.guilds)} guild(s)")
        for g in bot.guilds:
            log.info(f"   • {g.name} (id={g.id}, members={g.member_count})")
        try:
            activity = discord.Activity(type=discord.ActivityType.listening, name=config.prefix + "help")
            await bot.change_presence(activity=activity, status=discord.Status.online)
        except Exception as e:
            log.warn(f"Could not set presence: {e}")
        log.info("🎉 البوت جاهز لاستقبال الأوامر")

    @bot.event
    async def on_disconnect():
        log.warn("⚠️ Bot disconnected from Discord")

    @bot.event
    async def on_resumed():
        log.info("🔄 Bot session resumed")

    @bot.event
    async def on_command_error(ctx, error):
        _State.last_error = str(error)

        if isinstance(error, commands.CommandNotFound):
            return  # تجاهل الأوامر غير المعروفة

        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ وسيط ناقص: `{error.param.name}`")
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ انتظر {error.retry_after:.1f} ثانية")
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("🚫 ليس لديك الصلاحية لاستخدام هذا الأمر")
            return

        log.exception(f"Command error in {ctx.command}", error)
        try:
            await ctx.send(f"❌ حدث خطأ: `{error}`")
        except Exception:
            pass

    @bot.event
    async def on_guild_join(guild):
        log.info(f"➕ Joined guild: {guild.name} (id={guild.id})")

    @bot.event
    async def on_guild_remove(guild):
        log.info(f"➖ Left guild: {guild.name} (id={guild.id})")

    # ─────────────────────────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────────────────────────

    @bot.command(name="ping", help="اختبار سرعة الاستجابة")
    async def cmd_ping(ctx):
        latency_ms = round(bot.latency * 1000)
        await ctx.send(f"🏓 Pong! `{latency_ms}ms`")

    @bot.command(name="hello", help="ترحيب بالمستخدم")
    async def cmd_hello(ctx):
        await ctx.send(f"مرحباً {ctx.author.mention}! 👋")

    @bot.command(name="version", help="إصدار السكربت")
    async def cmd_version(ctx):
        await ctx.send(f"📦 الإصدار: `{get_version()}`")

    @bot.command(name="info", help="معلومات عن البوت والبيئة")
    async def cmd_info(ctx):
        env = get_environment_info()
        uptime = "—"
        if _State.start_time:
            secs = int(time.time() - _State.start_time)
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
            uptime = f"{h}h {m}m {s}s"

        msg = (
            f"**🤖 JvRemotPy Info**\n"
            f"```\n"
            f"Version    : {env['version']}\n"
            f"Python     : {env['python_version']}\n"
            f"Platform   : {env['platform']}\n"
            f"Android    : {env['is_android']}\n"
            f"discord.py : {env['discord_version']}\n"
            f"Prefix     : {config.prefix}\n"
            f"Uptime     : {uptime}\n"
            f"Guilds     : {len(bot.guilds)}\n"
            f"Latency    : {round(bot.latency * 1000)}ms\n"
            f"```"
        )
        await ctx.send(msg)

    @bot.command(name="echo", help="إعادة النص (للمطورين)")
    async def cmd_echo(ctx, *, text: str = ""):
        if not text:
            await ctx.send("⚠️ استخدم: `!echo <نص>`")
            return
        await ctx.send(f"📢 {text}")

    @bot.command(name="say", help="إرسال رسالة")
    @commands.has_permissions(manage_messages=True)
    async def cmd_say(ctx, *, text: str = ""):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        if text:
            await ctx.send(text)

    @bot.command(name="serverinfo", help="معلومات السيرفر")
    async def cmd_serverinfo(ctx):
        g = ctx.guild
        if not g:
            await ctx.send("⚠️ هذا الأمر للسيرفرات فقط")
            return
        await ctx.send(
            f"**🏰 {g.name}**\n"
            f"```\n"
            f"Owner   : {g.owner}\n"
            f"Members : {g.member_count}\n"
            f"Channels: {len(g.channels)}\n"
            f"Roles   : {len(g.roles)}\n"
            f"Created : {g.created_at.strftime('%Y-%m-%d')}\n"
            f"```"
        )

    @bot.command(name="userinfo", help="معلومات مستخدم")
    async def cmd_userinfo(ctx, member: discord.Member = None):
        member = member or ctx.author
        roles = ", ".join([r.mention for r in member.roles[1:]]) or "لا يوجد"
        await ctx.send(
            f"**👤 {member.display_name}**\n"
            f"```\n"
            f"ID     : {member.id}\n"
            f"Bot    : {member.bot}\n"
            f"Joined : {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else '—'}\n"
            f"Roles  : {roles}\n"
            f"```"
        )

    @bot.command(name="stop", help="إيقاف البوت (للمالك فقط)")
    async def cmd_stop(ctx):
        if not await bot.is_owner(ctx.author):
            await ctx.send("🚫 هذا الأمر للمالك فقط")
            return
        await ctx.send("👋 إيقاف البوت...")
        _State.stop_event.set()
        await bot.close()

    @bot.command(name="reload", help="إعادة تحميل الأوامر (للمالك)")
    async def cmd_reload(ctx):
        if not await bot.is_owner(ctx.author):
            await ctx.send("🚫 هذا الأمر للمالك فقط")
            return
        try:
            # إعادة تحميل الوحدة (لتحديث الأوامر من GitHub)
            import importlib
            import main as main_module
            importlib.reload(main_module)
            await ctx.send("✅ تم إعادة التحميل")
        except Exception as e:
            await ctx.send(f"❌ فشل: `{e}`")

    return bot


# ═══════════════════════════════════════════════════════════════════
#                       PUBLIC API
# ═══════════════════════════════════════════════════════════════════

def run(message: str = "") -> str:
    """
    دالة اختبار بسيطة (بدون Discord).
    تُستخدَم من MainActivity للتأكد من أن Python يعمل.
    """
    return (
        f"🎉 JvRemotPy v{get_version()} يعمل!\n"
        f"🐍 Python: {sys.version.split()[0]}\n"
        f"📱 Platform: {sys.platform}\n"
        f"💬 رسالتك: {message}"
    )


def run_bot(
    token: Optional[str] = None,
    prefix: str = "!",
    enable_message_content: bool = True,
    enable_members: bool = False,
    enable_presences: bool = False,
    enable_all_intents: bool = False,
) -> str:
    """
    ⭐ الدالة الرئيسية — تشغيل بوت Discord.

    Args:
        token: توكن البوت (مطلوب).
        prefix: بادئة الأوامر (افتراضي: "!").
        enable_message_content: تفعيل قراءة الرسائل (إلزامي للأوامر).
        enable_members: تفعيل قراءة الأعضاء (اختياري).
        enable_presences: تفعيل قراءة الحالات (اختياري).
        enable_all_intents: تفعيل كل الـ Intents (للمتقدمين).

    Returns:
        رسالة نصية بالنتيجة.
    """
    log.info("=" * 60)
    log.info(f"🚀 run_bot() called — version {get_version()}")
    log.info(f"🐍 Python: {sys.version.split()[0]}")
    log.info(f"📱 Platform: {sys.platform}")
    log.info("=" * 60)

    # 1. تحقق من المكتبة
    if not DISCORD_AVAILABLE:
        msg = f"❌ discord.py غير متوفر: {_IMPORT_ERROR}"
        log.error(msg)
        return msg

    # 2. تحقق من التوكن
    is_valid, reason = validate_token(token)
    if not is_valid:
        msg = f"❌ التوكن غير صحيح: {reason}"
        log.error(msg)
        return msg

    token = token.strip()
    log.info(f"🔑 Token validated (length={len(token)})")

    # 3. إذا كان البوت يعمل بالفعل
    if _State.is_running and _State.bot and not _State.bot.is_closed():
        log.warn("⚠️ Bot already running — stopping the old one")
        try:
            _State.stop_event.set()
            # محاولة إيقاف البوت الحالي في الخلفية
            threading.Thread(
                target=lambda: _State.bot.loop.call_soon_threadsafe(_State.bot.loop.stop),
                daemon=True
            ).start()
            time.sleep(2)
        except Exception as e:
            log.warn(f"Could not stop previous bot: {e}")

    _State.reset()

    # 4. بناء البوت
    config = BotConfig(
        token=token,
        prefix=prefix,
        enable_message_content=enable_message_content,
        enable_members=enable_members,
        enable_presences=enable_presences,
        enable_all_intents=enable_all_intents,
    )
    log.info(f"⚙️  Config: {config}")

    try:
        bot = create_bot(config)
    except Exception as e:
        log.exception("Failed to create bot", e)
        return f"❌ فشل إنشاء البوت: {e}"

    _State.bot = bot

    # 5. تشغيل البوت (blocking)
    try:
        log.info("▶️  Starting bot.run()...")
        bot.run(token, log_handler=None)  # log_handler=None لتجنب تعارض logging
        log.info("⏹️  bot.run() returned normally")
        return "✅ تم إيقاف البوت بنجاح"

    except discord.LoginFailure:
        msg = "❌ فشل تسجيل الدخول: التوكن غير صحيح أو منتهي الصلاحية"
        log.error(msg)
        return msg

    except discord.PrivilegedIntentsRequired as e:
        msg = (
            "❌ يجب تفعيل Privileged Intents:\n"
            "1. اذهب إلى https://discord.com/developers/applications\n"
            "2. اختر تطبيقك\n"
            "3. Bot → Privileged Gateway Intents\n"
            "4. فعّل Message Content Intent (و Members إن لزم)\n"
            f"التفاصيل: {e}"
        )
        log.error(msg)
        return msg

    except discord.HTTPException as e:
        msg = f"❌ خطأ HTTP من Discord: {e}"
        log.error(msg)
        return msg

    except KeyboardInterrupt:
        log.info("⌨️  Interrupted by user")
        return "⏹️ تم الإيقاف يدويًا"

    except Exception as e:
        log.exception("Unexpected error in bot.run()", e)
        return f"❌ خطأ غير متوقع: {e}"

    finally:
        _State.is_running = False
        log.info("🏁 run_bot() finished")


def stop_bot() -> str:
    """إيقاف البوت برمجيًا (يُستدعى من Java)."""
    if not _State.bot or _State.bot.is_closed():
        return "⚠️ البوت غير مشغّل"

    try:
        _State.stop_event.set()
        future = _State.bot.loop.call_soon_threadsafe(_State.bot.loop.stop)
        log.info("⏹️  Stop signal sent")
        return "✅ تم إرسال إشارة الإيقاف"
    except Exception as e:
        log.exception("Failed to stop bot", e)
        return f"❌ فشل الإيقاف: {e}"


def get_bot_status() -> Dict[str, Any]:
    """إرجاع حالة البوت الحالية."""
    if not _State.bot:
        return {"running": False, "reason": "not_initialized"}

    if _State.bot.is_closed():
        return {"running": False, "reason": "closed"}

    uptime = int(time.time() - _State.start_time) if _State.start_time else 0

    return {
        "running": _State.is_running,
        "user": str(_State.bot.user) if _State.bot.user else None,
        "user_id": _State.bot.user.id if _State.bot.user else None,
        "guilds": len(_State.bot.guilds),
        "latency_ms": round(_State.bot.latency * 1000),
        "uptime_seconds": uptime,
        "last_error": _State.last_error,
    }


# ═══════════════════════════════════════════════════════════════════
#                       MAIN (Testing)
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=== Local test mode ===")
    log.info(run("اختبار محلي"))
    log.info(f"Environment: {get_environment_info()}")
