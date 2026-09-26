"""
╔══════════════════════════════════════════════════════════════════╗
║                    JvRemotPy — Core Engine v5.0                  ║
║              Python Runtime for Android (Chaquopy)               ║
║                                                                  ║
║  Fixes in v5.0:                                                  ║
║    ✅ help_command=None (يحل التعارض الجذري)                     ║
║    ✅ bot.owner_id (يعمل is_owner)                               ║
║    ✅ Thread-safe accessors                                      ║
║    ✅ إعادة تشغيل نظيفة                                          ║
║    ✅ !eval يعمل مع statements                                   ║
║    ✅ on_ready يُستدعى مرة واحدة                                 ║
║    ✅ on_error عام                                               ║
║    ✅ إزالة imports غير مستخدمة                                  ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import io
import traceback
import threading
import contextlib
from datetime import datetime
from typing import Optional, Dict, Any

# ═══════════════════════════════════════════════════════════════════
#                       ENVIRONMENT
# ═══════════════════════════════════════════════════════════════════

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)


# ═══════════════════════════════════════════════════════════════════
#                       SAFE IMPORTS
# ═══════════════════════════════════════════════════════════════════

_discord = None
_commands = None
DISCORD_AVAILABLE = False
DISCORD_VERSION = "N/A"
_IMPORT_ERROR = None

try:
    import discord
    from discord.ext import commands
    _discord = discord
    _commands = commands
    DISCORD_AVAILABLE = True
    DISCORD_VERSION = getattr(discord, "__version__", "unknown")
except ImportError as e:
    _IMPORT_ERROR = str(e)


# ═══════════════════════════════════════════════════════════════════
#                       LOGGER
# ═══════════════════════════════════════════════════════════════════

class Logger:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
    ICONS = {"DEBUG": "🔍", "INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌"}

    def __init__(self, level: str = "INFO"):
        self.level_value = self.LEVELS.get(level.upper(), 20)

    def _log(self, level: str, msg: str):
        if self.LEVELS[level] < self.level_value:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            print(f"[{ts}] {self.ICONS[level]} [{level}] {msg}", flush=True)
        except Exception:
            pass

    def debug(self, m): self._log("DEBUG", m)
    def info(self, m):  self._log("INFO", m)
    def warn(self, m):  self._log("WARN", m)
    def error(self, m): self._log("ERROR", m)

    def exception(self, msg, exc=None):
        self.error(f"{msg}: {exc}" if exc else msg)
        try:
            print(traceback.format_exc(), flush=True)
        except Exception:
            pass


log = Logger()


# ═══════════════════════════════════════════════════════════════════
#                       STATE (Thread-safe)
# ═══════════════════════════════════════════════════════════════════

class BotState:
    def __init__(self):
        self._lock = threading.RLock()
        self._bot = None
        self._is_running = False
        self._start_time: Optional[float] = None
        self._last_error: Optional[str] = None
        self._stop_event = threading.Event()

    # ─── Bot ───
    def set_bot(self, bot):
        with self._lock:
            self._bot = bot

    def get_bot(self):
        with self._lock:
            return self._bot

    # ─── Running ───
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def mark_running(self):
        with self._lock:
            self._is_running = True
            self._start_time = time.time()

    def mark_stopped(self):
        with self._lock:
            self._is_running = False

    # ─── Time ───
    def get_start_time(self) -> Optional[float]:
        with self._lock:
            return self._start_time

    # ─── Error ───
    def set_error(self, err: str):
        with self._lock:
            self._last_error = err

    def get_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    # ─── Stop Event ───
    def get_stop_event(self) -> threading.Event:
        with self._lock:
            return self._stop_event

    # ─── Reset ───
    def reset(self):
        with self._lock:
            self._bot = None
            self._is_running = False
            self._start_time = None
            self._stop_event = threading.Event()


_state = BotState()


# ═══════════════════════════════════════════════════════════════════
#                       CONFIG
# ═══════════════════════════════════════════════════════════════════

# ⚠️ ضع معرف Discord الخاص بك (اختياري لكن يفعّل أوامر المالك)
BOT_OWNER_ID: Optional[str] = None  # مثال: "123456789012345678"


class BotConfig:
    def __init__(
        self,
        token: str,
        prefix: str = "!",
        owner_id: Optional[int] = None,
        enable_message_content: bool = True,
        enable_members: bool = False,
        enable_presences: bool = False,
        enable_all_intents: bool = False,
        activity_name: Optional[str] = None,
        activity_type: str = "listening",
    ):
        self.token = token
        self.prefix = prefix
        self.owner_id = owner_id
        self.enable_message_content = enable_message_content
        self.enable_members = enable_members
        self.enable_presences = enable_presences
        self.enable_all_intents = enable_all_intents
        self.activity_name = activity_name or f"{prefix}help"
        self.activity_type = activity_type

    def __repr__(self):
        return (f"BotConfig(prefix={self.prefix!r}, owner={self.owner_id}, "
                f"msg={self.enable_message_content}, members={self.enable_members})")


# ═══════════════════════════════════════════════════════════════════
#                       VERSION & ENV
# ═══════════════════════════════════════════════════════════════════

def get_version() -> str:
    return "5.0.0"


def get_environment_info() -> Dict[str, Any]:
    return {
        "version": get_version(),
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "is_android": "android" in sys.platform.lower() or hasattr(sys, "getandroidapilevel"),
        "discord_available": DISCORD_AVAILABLE,
        "discord_version": DISCORD_VERSION,
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
#                       TOKEN VALIDATION
# ═══════════════════════════════════════════════════════════════════

def validate_token(token: Optional[str]) -> tuple:
    """تحقق من صيغة توكن Discord (base64، 3 أجزاء)."""
    if not token:
        return False, "التوكن فارغ"
    if not isinstance(token, str):
        return False, "التوكن ليس نصًا"

    token = token.strip()

    if " " in token or "\n" in token or "\t" in token:
        return False, "التوكن يحتوي على مسافات"
    if len(token) < 50:
        return False, f"التوكن قصير ({len(token)} حرف)"
    if len(token) > 120:
        return False, f"التوكن طويل ({len(token)} حرف)"

    parts = token.split(".")
    if len(parts) != 3:
        return False, f"عدد الأجزاء {len(parts)} ≠ 3"

    p1, p2, p3 = parts
    if not p1 or not p2 or not p3:
        return False, "جزء فارغ في التوكن"

    if len(p1) < 20:
        return False, f"الجزء الأول قصير ({len(p1)})"
    if len(p2) < 5:
        return False, f"الجزء الثاني قصير ({len(p2)})"
    if len(p3) < 25:
        return False, f"الجزء الثالث قصير ({len(p3)})"

    return True, "صحيح"


# ═══════════════════════════════════════════════════════════════════
#                       INTENTS
# ═══════════════════════════════════════════════════════════════════

def make_intents(config: BotConfig):
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
#              ✅ CREATE BOT (الإصلاحات الجذرية)
# ═══════════════════════════════════════════════════════════════════

def create_bot(config: BotConfig):
    """
    إنشاء البوت مع كل الإصلاحات:
      ✅ help_command=None (يحل التعارض)
      ✅ owner_id
      ✅ on_ready مرة واحدة
      ✅ on_error عام
    """
    if not DISCORD_AVAILABLE:
        raise RuntimeError(f"discord.py غير متوفر: {_IMPORT_ERROR}")

    intents = make_intents(config)

    # ═══════════════════════════════════════════════════════════
    # ✅ الإصلاح #1: help_command=None لمنع التعارض
    # ═══════════════════════════════════════════════════════════
    bot = _commands.Bot(
        command_prefix=config.prefix,
        intents=intents,
        help_command=None,       # ← الحل الجذري
        case_insensitive=True,   # ← أوامر أسهل
        strip_after_prefix=True, # ← "! ping" = "!ping"
    )

    # ✅ الإصلاح #2: owner_id
    if config.owner_id:
        try:
            bot.owner_id = int(config.owner_id)
            log.info(f"👑 Owner ID: {bot.owner_id}")
        except Exception as e:
            log.warn(f"Invalid owner_id: {e}")

    # ✅ الإصلاح #3: on_ready مرة واحدة
    _ready_called = {"value": False}

    # ═══════════════════ Events ═══════════════════

    @bot.event
    async def on_ready():
        if _ready_called["value"]:
            log.debug("on_ready called again (ignored)")
            return
        _ready_called["value"] = True

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
            log.info(f"📢 Status set: {config.activity_type} {config.activity_name}")
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
    async def on_connect():
        log.info("🔌 Connected to Discord gateway")

    # ✅ الإصلاح #4: on_error عام للأخطاء خارج الأوامر
    @bot.event
    async def on_error(event_method, *args, **kwargs):
        log.error(f"⚠️ Unhandled error in {event_method}")
        try:
            print(traceback.format_exc(), flush=True)
        except Exception:
            pass

    @bot.event
    async def on_command_error(ctx, error):
        _state.set_error(str(error))

        # تجاهل الأوامر غير المعروفة
        if isinstance(error, _commands.CommandNotFound):
            return

        # أخطاء شائعة
        if isinstance(error, _commands.MissingRequiredArgument):
            try:
                await ctx.send(f"⚠️ وسيط ناقص: `{error.param.name}`")
            except Exception:
                pass
            return

        if isinstance(error, _commands.CommandOnCooldown):
            try:
                await ctx.send(f"⏳ انتظر {error.retry_after:.1f}s")
            except Exception:
                pass
            return

        if isinstance(error, _commands.MissingPermissions):
            try:
                await ctx.send("🚫 ليس لديك الصلاحية")
            except Exception:
                pass
            return

        if isinstance(error, _commands.BotMissingPermissions):
            try:
                await ctx.send(f"🚫 البوت يفتقد: {', '.join(error.missing_permissions)}")
            except Exception:
                pass
            return

        # خطأ عام
        log.exception(f"Command error in {ctx.command}", error)
        try:
            await ctx.send(f"❌ خطأ: `{type(error).__name__}: {error}`")
        except Exception:
            pass

    @bot.event
    async def on_guild_join(guild):
        log.info(f"➕ Joined: {guild.name} (id={guild.id})")

    @bot.event
    async def on_guild_remove(guild):
        log.info(f"➖ Left: {guild.name} (id={guild.id})")

    # ═══════════════════ Helper: is_owner ═══════════════════

    async def _is_owner(user) -> bool:
        """فحص آمن للمالك."""
        try:
            if bot.owner_id:
                return user.id == bot.owner_id
            return await bot.is_owner(user)
        except Exception:
            return False

    # ═══════════════════ Commands ═══════════════════

    @bot.command(name="ping")
    async def cmd_ping(ctx):
        await ctx.send(f"🏓 Pong! `{round(bot.latency * 1000)}ms`")

    @bot.command(name="hello")
    async def cmd_hello(ctx):
        await ctx.send(f"مرحباً {ctx.author.mention}! 👋")

    @bot.command(name="version")
    async def cmd_version(ctx):
        await ctx.send(f"📦 `{get_version()}`")

    @bot.command(name="info")
    async def cmd_info(ctx):
        env = get_environment_info()
        start = _state.get_start_time()
        uptime = "—"
        if start:
            s = int(time.time() - start)
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

    @bot.command(name="uptime")
    async def cmd_uptime(ctx):
        start = _state.get_start_time()
        if not start:
            await ctx.send("⚠️ لم يبدأ")
            return
        s = int(time.time() - start)
        await ctx.send(f"⏱️ `{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}`")

    @bot.command(name="echo")
    async def cmd_echo(ctx, *, text: str = ""):
        if not text:
            await ctx.send("⚠️ استخدم: `!echo <نص>`")
            return
        await ctx.send(f"📢 {text}")

    @bot.command(name="say")
    @_commands.has_permissions(manage_messages=True)
    async def cmd_say(ctx, *, text: str = ""):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        if text:
            await ctx.send(text)

    @bot.command(name="serverinfo")
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

    @bot.command(name="userinfo")
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

    @bot.command(name="avatar")
    async def cmd_avatar(ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.send(member.display_avatar.url)

    # ✅ command: help (الآن آمن لأن help_command=None)
    @bot.command(name="help")
    async def cmd_help(ctx):
        cmds = [
            ("ping", "اختبار سرعة"),
            ("hello", "ترحيب"),
            ("version", "الإصدار"),
            ("info", "معلومات البوت"),
            ("uptime", "مدة التشغيل"),
            ("echo <نص>", "إعادة النص"),
            ("say <نص>", "إرسال رسالة"),
            ("serverinfo", "معلومات السيرفر"),
            ("userinfo [@user]", "معلومات مستخدم"),
            ("avatar [@user]", "صورة المستخدم"),
            ("help", "هذه القائمة"),
            ("—", "— أوامر المالك —"),
            ("stop", "إيقاف البوت"),
            ("reload", "إعادة تحميل"),
            ("exec <كود>", "تنفيذ Python"),
        ]
        lines = [f"`{config.prefix}{c[0]}` — {c[1]}" for c in cmds]
        await ctx.send("**📋 الأوامر:**\n" + "\n".join(lines))

    @bot.command(name="stop")
    async def cmd_stop(ctx):
        if not await _is_owner(ctx.author):
            await ctx.send("🚫 للمالك فقط")
            return
        await ctx.send("👋 إيقاف...")
        _state.get_stop_event().set()
        await bot.close()

    @bot.command(name="reload")
    async def cmd_reload(ctx):
        if not await _is_owner(ctx.author):
            await ctx.send("🚫 للمالك فقط")
            return
        try:
            import importlib
            import main as main_module
            importlib.reload(main_module)
            await ctx.send("✅ تم إعادة التحميل")
        except Exception as e:
            await ctx.send(f"❌ فشل: `{e}`")

    # ✅ الإصلاح #5: !exec بدل !eval (يدعم statements)
    @bot.command(name="exec")
    async def cmd_exec(ctx, *, code: str = ""):
        if not await _is_owner(ctx.author):
            await ctx.send("🚫 للمالك فقط")
            return
        if not code:
            await ctx.send("⚠️ استخدم: `!exec <كود>`")
            return

        # التقط stdout
        buf = io.StringIO()
        local_vars = {}
        try:
            with contextlib.redirect_stdout(buf):
                exec(code, {"bot": bot, "discord": discord}, local_vars)

            output = buf.getvalue().strip()
            result = local_vars.get("result", None)

            msg_parts = []
            if output:
                msg_parts.append(f"📤 Output:\n```\n{output[:1500]}\n```")
            if result is not None:
                msg_parts.append(f"📊 Result: `{result}`")
            if not msg_parts:
                msg_parts.append("✅ تم التنفيذ (بدون output)")

            await ctx.send("\n".join(msg_parts))
        except Exception as e:
            await ctx.send(f"❌ خطأ:\n```\n{type(e).__name__}: {e}\n```")

    # alias: !eval (للمتوافقية)
    @bot.command(name="eval")
    async def cmd_eval_alias(ctx, *, code: str = ""):
        await cmd_exec(ctx, code=code)

    return bot


# ═══════════════════════════════════════════════════════════════════
#                       PUBLIC API
# ═══════════════════════════════════════════════════════════════════

def run(message: str = "") -> str:
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
    log.info("=" * 60)
    log.info(f"🚀 run_bot() — v{get_version()}")
    log.info(f"🐍 Python: {sys.version.split()[0]}")
    log.info(f"📱 Platform: {sys.platform}")
    log.info("=" * 60)

    if not DISCORD_AVAILABLE:
        msg = f"❌ discord.py غير متوفر: {_IMPORT_ERROR}"
        log.error(msg)
        return msg

    is_valid, reason = validate_token(token)
    if not is_valid:
        msg = f"❌ التوكن غير صحيح: {reason}"
        log.error(msg)
        return msg

    token = token.strip()
    log.info(f"🔑 Token OK (len={len(token)})")

    # ✅ الإصلاح #6: إيقاف نظيف بترتيب صحيح
    old_bot = _state.get_bot()
    if old_bot and not old_bot.is_closed():
        log.warn("⚠️ Stopping old bot first...")
        try:
            _state.get_stop_event().set()
            if old_bot.loop and old_bot.loop.is_running():
                old_bot.loop.call_soon_threadsafe(old_bot.loop.stop)
            time.sleep(2)
        except Exception as e:
            log.warn(f"Stop old bot failed: {e}")

    _state.reset()

    # استخرج owner_id من الإعدادات
    owner_id_int = None
    if BOT_OWNER_ID and BOT_OWNER_ID.isdigit():
        owner_id_int = int(BOT_OWNER_ID)

    config = BotConfig(
        token=token,
        prefix=prefix,
        owner_id=owner_id_int,
        enable_message_content=enable_message_content,
        enable_members=enable_members,
        enable_presences=enable_presences,
        enable_all_intents=enable_all_intents,
    )
    log.info(f"⚙️ {config}")

    try:
        bot = create_bot(config)
    except Exception as e:
        log.exception("create_bot failed", e)
        return f"❌ فشل إنشاء البوت: {e}"

    _state.set_bot(bot)

    try:
        log.info("▶️ bot.run() starting...")
        # ✅ الإصلاح #7: كتم log discord الافتراضي
        import logging
        logging.getLogger("discord").setLevel(logging.WARNING)
        logging.getLogger("discord.http").setLevel(logging.WARNING)

        bot.run(token, log_handler=None)
        log.info("⏹️ bot.run() ended")
        return "✅ تم إيقاف البوت"

    except _discord.LoginFailure:
        msg = "❌ تسجيل الدخول فشل: التوكن غير صحيح"
        log.error(msg)
        return msg

    except _discord.PrivilegedIntentsRequired:
        msg = (
            "❌ فعّل Privileged Intents:\n"
            "1. discord.com/developers/applications\n"
            "2. تطبيقك → Bot\n"
            "3. فعّل Message Content Intent"
        )
        log.error(msg)
        return msg

    except _discord.HTTPException as e:
        msg = f"❌ HTTP: {e}"
        log.error(msg)
        return msg

    except KeyboardInterrupt:
        return "⏹️ إيقاف يدوي"

    except Exception as e:
        log.exception("run_bot failed", e)
        return f"❌ خطأ: {e}"

    finally:
        _state.mark_stopped()
        log.info("🏁 run_bot() finished")


def stop_bot() -> str:
    bot = _state.get_bot()
    if not bot or bot.is_closed():
        return "⚠️ البوت غير مشغّل"
    try:
        _state.get_stop_event().set()
        if bot.loop and bot.loop.is_running():
            bot.loop.call_soon_threadsafe(bot.loop.stop)
        log.info("⏹️ Stop sent")
        return "✅ تم الإرسال"
    except Exception as e:
        log.exception("stop_bot failed", e)
        return f"❌ فشل: {e}"


def get_bot_status() -> Dict[str, Any]:
    bot = _state.get_bot()
    if not bot:
        return {"running": False, "reason": "not_initialized"}
    if bot.is_closed():
        return {"running": False, "reason": "closed"}

    start = _state.get_start_time()
    uptime = int(time.time() - start) if start else 0

    return {
        "running": _state.is_running(),
        "user": str(bot.user) if bot.user else None,
        "user_id": bot.user.id if bot.user else None,
        "guilds": len(bot.guilds),
        "latency_ms": round(bot.latency * 1000),
        "uptime_seconds": uptime,
        "last_error": _state.get_error(),
        "owner_id": bot.owner_id,
    }


if __name__ == "__main__":
    log.info("=== Test ===")
    log.info(run("اختبار"))
