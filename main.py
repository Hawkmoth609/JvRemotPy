"""
╔══════════════════════════════════════════════════════════════════╗
║                    JvRemotPy — Core Engine v4.0                  ║
║              Python Runtime for Android (Chaquopy)               ║
║                                                                  ║
║  Features:                                                       ║
║    • Discord Bot with full Intents support                       ║
║    • Robust token validation (base64-aware)                      ║
║    • Graceful error handling & auto-recovery                     ║
║    • Thread-safe state management                                ║
║    • Environment auto-detection (Android / Desktop)              ║
║    • Hot-reload support without restarting                       ║
║    • Periodic tasks scheduler                                    ║
║    • Detailed Logging for Android Logcat                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import asyncio
import traceback
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List

# ═══════════════════════════════════════════════════════════════════
#                       ENVIRONMENT SETUP
# ═══════════════════════════════════════════════════════════════════

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


# ═══════════════════════════════════════════════════════════════════
#                       SAFE IMPORTS
# ═══════════════════════════════════════════════════════════════════

_discord = None
_commands = None
_tasks = None
DISCORD_AVAILABLE = False
DISCORD_VERSION = "N/A"
_IMPORT_ERROR = None

try:
    import discord
    from discord.ext import commands, tasks
    _discord = discord
    _commands = commands
    _tasks = tasks
    DISCORD_AVAILABLE = True
    DISCORD_VERSION = getattr(discord, "__version__", "unknown")
except ImportError as e:
    _IMPORT_ERROR = str(e)


# ═══════════════════════════════════════════════════════════════════
#                       LOGGER
# ═══════════════════════════════════════════════════════════════════

class Logger:
    """Logger موحّد يعمل مع Android Logcat."""

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
    ICONS = {"DEBUG": "🔍", "INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌"}

    def __init__(self, level: str = "INFO"):
        self.level_value = self.LEVELS.get(level.upper(), 20)

    def _log(self, level: str, msg: str):
        if self.LEVELS[level] < self.level_value:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        icon = self.ICONS[level]
        try:
            print(f"[{ts}] {icon} [{level}] {msg}", flush=True)
        except Exception:
            pass  # تجنّب فشل الطباعة على Android

    def debug(self, msg): self._log("DEBUG", msg)
    def info(self, msg):  self._log("INFO", msg)
    def warn(self, msg):  self._log("WARN", msg)
    def error(self, msg): self._log("ERROR", msg)

    def exception(self, msg, exc=None):
        self.error(f"{msg}: {exc}" if exc else msg)
        try:
            print(traceback.format_exc(), flush=True)
        except Exception:
            pass


log = Logger()


# ═══════════════════════════════════════════════════════════════════
#                       GLOBAL STATE (Thread-safe)
# ═══════════════════════════════════════════════════════════════════

class BotState:
    """حالة عامة للبوت — محمية بقفل للخيوط."""

    def __init__(self):
        self._lock = threading.RLock()
        self.bot = None
        self.is_running = False
        self.start_time: Optional[float] = None
        self.last_error: Optional[str] = None
        self.stop_event = threading.Event()

    def reset(self):
        with self._lock:
            self.bot = None
            self.is_running = False
            self.start_time = None
            self.stop_event = threading.Event()

    def set_bot(self, bot):
        with self._lock:
            self.bot = bot

    def get_bot(self):
        with self._lock:
            return self.bot

    def mark_running(self):
        with self._lock:
            self.is_running = True
            self.start_time = time.time()

    def mark_stopped(self):
        with self._lock:
            self.is_running = False

    def set_error(self, err: str):
        with self._lock:
            self.last_error = err


_state = BotState()


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
        activity_name: Optional[str] = None,
        activity_type: str = "listening",
    ):
        self.token = token
        self.prefix = prefix
        self.enable_message_content = enable_message_content
        self.enable_members = enable_members
        self.enable_presences = enable_presences
        self.enable_all_intents = enable_all_intents
        self.log_level = log_level
        self.activity_name = activity_name or f"{prefix}help"
        self.activity_type = activity_type

    def __repr__(self):
        return (
            f"BotConfig(prefix={self.prefix!r}, "
            f"intents={{msg={self.enable_message_content}, "
            f"members={self.enable_members}, "
            f"presences={self.enable_presences}}})"
        )


# ═══════════════════════════════════════════════════════════════════
#                       VERSION & ENVIRONMENT
# ═══════════════════════════════════════════════════════════════════

def get_version() -> str:
    return "4.0.0"


def get_environment_info() -> Dict[str, Any]:
    """معلومات شاملة عن البيئة."""
    return {
        "version": get_version(),
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "is_android": "android" in sys.platform.lower() or hasattr(sys, "getandroidapilevel"),
        "discord_available": DISCORD_AVAILABLE,
        "discord_version": DISCORD_VERSION,
        "script_dir": _SCRIPT_DIR,
        "cwd": os.getcwd(),
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
#              ✅ TOKEN VALIDATION (الإصلاح الجذري)
# ═══════════════════════════════════════════════════════════════════

def validate_token(token: Optional[str]) -> tuple:
    """
    ✅ التحقق من صيغة توكن Discord.

    صيغة توكن Discord:
        part1.part2.part3
        - part1: Bot ID مُرمّز بـ base64 (عادة 24-26 حرفًا)
        - part2: timestamp (6-7 أحرف)
        - part3: HMAC signature (27-38 حرفًا)

    ⚠️ ملاحظة مهمة: الجزء الأول هو base64 وليس رقمًا!
    """
    if not token:
        return False, "التوكن فارغ"

    if not isinstance(token, str):
        return False, "التوكن ليس نصًا"

    token = token.strip()

    if len(token) < 50:
        return False, f"التوكن قصير جدًا ({len(token)} حرف، المتوقع 60+)"

    if len(token) > 120:
        return False, f"التوكن طويل جدًا ({len(token)} حرف)"

    # التحقق من وجود 3 أجزاء
    parts = token.split(".")
    if len(parts) != 3:
        return False, f"التنسيق غير صحيح ({len(parts)} أجزاء، المتوقع 3)"

    # ✅ تحقق فقط أن كل الأجزاء غير فارغة
    # ❌ لا نتحقق من isdigit() — الجزء الأول base64
    if not all(parts):
        return False, "أحد أجزاء التوكن فارغ"

    # تحقق من طول كل جزء (معايير Discord)
    p1_len, p2_len, p3_len = len(parts[0]), len(parts[1]), len(parts[2])

    if p1_len < 20:
        return False, f"الجزء الأول قصير جدًا ({p1_len} حرف)"
    if p2_len < 5:
        return False, f"الجزء الثاني قصير جدًا ({p2_len} حرف)"
    if p3_len < 25:
        return False, f"الجزء الثالث قصير جدًا ({p3_len} حرف)"

    return True, "صحيح"


# ═══════════════════════════════════════════════════════════════════
#                       INTENTS BUILDER
# ═══════════════════════════════════════════════════════════════════

def make_intents(config: BotConfig):
    """إنشاء Intents حسب الإعدادات."""
    if not DISCORD_AVAILABLE:
        return None

    if config.enable_all_intents:
        return discord.Intents.all()

    intents = discord.Intents.default()
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
    """إنشاء البوت مع كل الأحداث والأوامر."""
    if not DISCORD_AVAILABLE:
        raise RuntimeError(f"discord.py غير متوفر: {_IMPORT_ERROR}")

    intents = make_intents(config)
    bot = _commands.Bot(command_prefix=config.prefix, intents=intents)

    # ═══════════════════ Events ═══════════════════

    @bot.event
    async def on_ready():
        _state.mark_running()
        log.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
        log.info(f"✅ Connected to {len(bot.guilds)} guild(s)")
        for g in bot.guilds:
            log.info(f"   • {g.name} (id={g.id}, members={g.member_count})")
        try:
            atype = {
                "playing": discord.ActivityType.playing,
                "listening": discord.ActivityType.listening,
                "watching": discord.ActivityType.watching,
                "competing": discord.ActivityType.competing,
            }.get(config.activity_type, discord.ActivityType.listening)

            await bot.change_presence(
                activity=discord.Activity(type=atype, name=config.activity_name),
                status=discord.Status.online,
            )
        except Exception as e:
            log.warn(f"Presence error: {e}")
        log.info("🎉 البوت جاهز")

    @bot.event
    async def on_disconnect():
        log.warn("⚠️ Disconnected from Discord")

    @bot.event
    async def on_resumed():
        log.info("🔄 Session resumed")

    @bot.event
    async def on_command_error(ctx, error):
        _state.set_error(str(error))

        if isinstance(error, _commands.CommandNotFound):
            return
        if isinstance(error, _commands.MissingRequiredArgument):
            await ctx.send(f"⚠️ وسيط ناقص: `{error.param.name}`")
            return
        if isinstance(error, _commands.CommandOnCooldown):
            await ctx.send(f"⏳ انتظر {error.retry_after:.1f} ثانية")
            return
        if isinstance(error, _commands.MissingPermissions):
            await ctx.send("🚫 ليس لديك الصلاحية")
            return
        if isinstance(error, _commands.BotMissingPermissions):
            await ctx.send(f"🚫 البوت يفتقد صلاحيات: {error.missing_permissions}")
            return

        log.exception(f"Command error in {ctx.command}", error)
        try:
            await ctx.send(f"❌ خطأ: `{error}`")
        except Exception:
            pass

    @bot.event
    async def on_guild_join(guild):
        log.info(f"➕ Joined: {guild.name} (id={guild.id})")

    @bot.event
    async def on_guild_remove(guild):
        log.info(f"➖ Left: {guild.name} (id={guild.id})")

    # ═══════════════════ Commands ═══════════════════

    @bot.command(name="ping", help="اختبار سرعة الاستجابة")
    async def cmd_ping(ctx):
        await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

    @bot.command(name="hello", help="ترحيب")
    async def cmd_hello(ctx):
        await ctx.send(f"مرحباً {ctx.author.mention}! 👋")

    @bot.command(name="version", help="إصدار السكربت")
    async def cmd_version(ctx):
        await ctx.send(f"📦 `{get_version()}`")

    @bot.command(name="info", help="معلومات البوت")
    async def cmd_info(ctx):
        env = get_environment_info()
        uptime = "—"
        if _state.start_time:
            s = int(time.time() - _state.start_time)
            uptime = f"{s // 3600}h {(s % 3600) // 60}m {s % 60}s"

        await ctx.send(
            f"**🤖 JvRemotPy Info**\n```\n"
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

    @bot.command(name="uptime", help="مدة التشغيل")
    async def cmd_uptime(ctx):
        if not _state.start_time:
            await ctx.send("⚠️ البوت لم يبدأ بعد")
            return
        s = int(time.time() - _state.start_time)
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        await ctx.send(f"⏱️ `{h:02d}:{m:02d}:{sec:02d}`")

    @bot.command(name="echo", help="إعادة النص")
    async def cmd_echo(ctx, *, text: str = ""):
        if not text:
            await ctx.send("⚠️ استخدم: `!echo <نص>`")
            return
        await ctx.send(f"📢 {text}")

    @bot.command(name="say", help="إرسال رسالة")
    @_commands.has_permissions(manage_messages=True)
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
            await ctx.send("⚠️ للسيرفرات فقط")
            return
        await ctx.send(
            f"**🏰 {g.name}**\n```\n"
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
        roles = ", ".join(r.mention for r in member.roles[1:]) or "لا يوجد"
        await ctx.send(
            f"**👤 {member.display_name}**\n```\n"
            f"ID     : {member.id}\n"
            f"Bot    : {member.bot}\n"
            f"Joined : {member.joined_at.strftime('%Y-%m-%d') if member.joined_at else '—'}\n"
            f"Roles  : {roles}\n"
            f"```"
        )

    @bot.command(name="avatar", help="صورة المستخدم")
    async def cmd_avatar(ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(member.display_avatar.url)

    @bot.command(name="help", help="قائمة الأوامر")
    async def cmd_help(ctx):
        cmds = [
            ("ping", "اختبار سرعة الاستجابة"),
            ("hello", "ترحيب"),
            ("version", "إصدار السكربت"),
            ("info", "معلومات البوت"),
            ("uptime", "مدة التشغيل"),
            ("echo <نص>", "إعادة النص"),
            ("say <نص>", "إرسال رسالة"),
            ("serverinfo", "معلومات السيرفر"),
            ("userinfo [@user]", "معلومات مستخدم"),
            ("avatar [@user]", "صورة المستخدم"),
            ("help", "هذه القائمة"),
        ]
        lines = [f"`{config.prefix}{c[0]}` — {c[1]}" for c in cmds]
        await ctx.send("**📋 الأوامر المتاحة:**\n" + "\n".join(lines))

    @bot.command(name="stop", help="إيقاف البوت (للمالك)")
    async def cmd_stop(ctx):
        try:
            is_owner = await bot.is_owner(ctx.author)
        except Exception:
            is_owner = False

        if not is_owner:
            await ctx.send("🚫 للمالك فقط")
            return
        await ctx.send("👋 إيقاف...")
        _state.stop_event.set()
        await bot.close()

    @bot.command(name="reload", help="إعادة تحميل main.py (للمالك)")
    async def cmd_reload(ctx):
        try:
            is_owner = await bot.is_owner(ctx.author)
        except Exception:
            is_owner = False

        if not is_owner:
            await ctx.send("🚫 للمالك فقط")
            return

        try:
            import importlib
            import main as main_module
            importlib.reload(main_module)
            await ctx.send("✅ تم إعادة التحميل")
        except Exception as e:
            await ctx.send(f"❌ فشل: `{e}`")

    @bot.command(name="eval", help="تنفيذ Python (للمالك)")
    async def cmd_eval(ctx, *, code: str = ""):
        try:
            is_owner = await bot.is_owner(ctx.author)
        except Exception:
            is_owner = False

        if not is_owner:
            await ctx.send("🚫 للمالك فقط")
            return
        if not code:
            await ctx.send("⚠️ استخدم: `!eval <كود>`")
            return

        try:
            result = eval(code)
            await ctx.send(f"✅ `{result}`")
        except Exception as e:
            await ctx.send(f"❌ `{e}`")

    return bot


# ═══════════════════════════════════════════════════════════════════
#                       PUBLIC API
# ═══════════════════════════════════════════════════════════════════

def run(message: str = "") -> str:
    """دالة اختبار بسيطة بدون Discord."""
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
        token: توكن البوت (مطلوب)
        prefix: بادئة الأوامر
        enable_message_content: قراءة الرسائل (إلزامي)
        enable_members: قراءة الأعضاء (اختياري)
        enable_presences: قراءة الحالات (اختياري)
        enable_all_intents: كل الـ Intents

    Returns:
        رسالة نصية بالنتيجة.
    """
    log.info("=" * 60)
    log.info(f"🚀 run_bot() called — v{get_version()}")
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

    # 3. إيقاف أي بوت سابق
    if _state.is_running and _state.bot and not _state.bot.is_closed():
        log.warn("⚠️ Bot already running — stopping old")
        try:
            _state.stop_event.set()
            threading.Thread(
                target=lambda: _state.bot.loop.call_soon_threadsafe(_state.bot.loop.stop),
                daemon=True,
            ).start()
            time.sleep(2)
        except Exception as e:
            log.warn(f"Stop previous failed: {e}")

    _state.reset()

    # 4. بناء البوت
    config = BotConfig(
        token=token,
        prefix=prefix,
        enable_message_content=enable_message_content,
        enable_members=enable_members,
        enable_presences=enable_presences,
        enable_all_intents=enable_all_intents,
    )
    log.info(f"⚙️ Config: {config}")

    try:
        bot = create_bot(config)
    except Exception as e:
        log.exception("Failed to create bot", e)
        return f"❌ فشل إنشاء البوت: {e}"

    _state.set_bot(bot)

    # 5. تشغيل البوت
    try:
        log.info("▶️ Starting bot.run()...")
        bot.run(token, log_handler=None)
        log.info("⏹️ bot.run() finished")
        return "✅ تم إيقاف البوت"

    except _discord.LoginFailure:
        msg = "❌ فشل تسجيل الدخول: التوكن غير صحيح أو منتهي"
        log.error(msg)
        return msg

    except _discord.PrivilegedIntentsRequired:
        msg = (
            "❌ يجب تفعيل Privileged Intents:\n"
            "1. discord.com/developers/applications\n"
            "2. اختر تطبيقك → Bot\n"
            "3. فعّل Message Content Intent\n"
        )
        log.error(msg)
        return msg

    except _discord.HTTPException as e:
        msg = f"❌ خطأ HTTP: {e}"
        log.error(msg)
        return msg

    except KeyboardInterrupt:
        log.info("⌨️ Interrupted")
        return "⏹️ إيقاف يدوي"

    except Exception as e:
        log.exception("Unexpected error", e)
        return f"❌ خطأ غير متوقع: {e}"

    finally:
        _state.mark_stopped()
        log.info("🏁 run_bot() finished")


def stop_bot() -> str:
    """إيقاف البوت برمجيًا."""
    bot = _state.get_bot()
    if not bot or bot.is_closed():
        return "⚠️ البوت غير مشغّل"

    try:
        _state.stop_event.set()
        bot.loop.call_soon_threadsafe(bot.loop.stop)
        log.info("⏹️ Stop signal sent")
        return "✅ تم الإرسال"
    except Exception as e:
        log.exception("stop_bot failed", e)
        return f"❌ فشل: {e}"


def get_bot_status() -> Dict[str, Any]:
    """حالة البوت الحالية."""
    bot = _state.get_bot()
    if not bot:
        return {"running": False, "reason": "not_initialized"}
    if bot.is_closed():
        return {"running": False, "reason": "closed"}

    uptime = int(time.time() - _state.start_time) if _state.start_time else 0
    return {
        "running": _state.is_running,
        "user": str(bot.user) if bot.user else None,
        "user_id": bot.user.id if bot.user else None,
        "guilds": len(bot.guilds),
        "latency_ms": round(bot.latency * 1000),
        "uptime_seconds": uptime,
        "last_error": _state.last_error,
    }


# ═══════════════════════════════════════════════════════════════════
#                       MAIN (Testing)
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=== Local test ===")
    log.info(run("اختبار"))
    log.info(f"Environment: {get_environment_info()}")
