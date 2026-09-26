"""
╔══════════════════════════════════════════════════════════════════╗
║                    JvRemotPy — Core Engine v7.0                  ║
║              Python Runtime for Android (Chaquopy)               ║
║                                                                  ║
║  Improvements in v7.0:                                           ║
║    ✅ is_owner آمن (بدون API call لكل استدعاء)                   ║
║    ✅ Thread-safe ContactsBridge                                ║
║    ✅ Rate limiting على !contacts                               ║
║    ✅ أوامر جديدة: !health, !status, !reload_bridge              ║
║    ✅ إصلاح bot.loop قد يكون None                                ║
║    ✅ معالجة NotOwner error                                      ║
║    ✅ Idempotent _init_contacts_bridge                           ║
║    ✅ logging مُهيّأ عند الاستيراد                                ║
║    ✅ Health monitoring built-in                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

import sys
import os
import time
import io
import logging
import traceback
import threading
import contextlib
from datetime import datetime
from typing import Optional, Dict, Any, List

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


# ✅ إعداد logging مرة واحدة (بدلاً من داخل الدوال)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)
logging.getLogger("discord.gateway").setLevel(logging.WARNING)


# ═══════════════════════════════════════════════════════════════════
#                       LOGGER
# ═══════════════════════════════════════════════════════════════════

class Logger:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}
    ICONS = {"DEBUG": "🔍", "INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌"}

    def __init__(self, level: str = "INFO"):
        self.level_value = self.LEVELS.get(level.upper(), 20)
        self._history: List[str] = []
        self._max_history = 200

    def _log(self, level: str, msg: str):
        if self.LEVELS[level] < self.level_value:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {self.ICONS[level]} [{level}] {msg}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        # حفظ آخر 200 رسالة
        self._history.append(line)
        if len(self._history) > self._max_history:
            self._history.pop(0)

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

    def get_history(self, n: int = 50) -> List[str]:
        return self._history[-n:]


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
        self._command_count = 0

    def set_bot(self, bot):
        with self._lock:
            self._bot = bot

    def get_bot(self):
        with self._lock:
            return self._bot

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

    def get_start_time(self) -> Optional[float]:
        with self._lock:
            return self._start_time

    def set_error(self, err: str):
        with self._lock:
            self._last_error = err

    def get_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def get_stop_event(self) -> threading.Event:
        with self._lock:
            return self._stop_event

    def increment_commands(self):
        with self._lock:
            self._command_count += 1

    def get_command_count(self) -> int:
        with self._lock:
            return self._command_count

    def reset(self):
        with self._lock:
            self._bot = None
            self._is_running = False
            self._start_time = None
            self._stop_event = threading.Event()


_state = BotState()


# ═══════════════════════════════════════════════════════════════════
#                       CONTACTS BRIDGE (Thread-safe)
# ═══════════════════════════════════════════════════════════════════

_contacts_bridge = None
_contacts_bridge_lock = threading.Lock()
_contacts_bridge_initialized = False


def _init_contacts_bridge(force: bool = False) -> bool:
    """
    محاولة ربط ContactsBridge من Java.
    Idempotent: لا يُعيد المحاولة إلا إذا force=True أو لم يُهيَّأ بعد.
    Thread-safe.
    """
    global _contacts_bridge, _contacts_bridge_initialized

    with _contacts_bridge_lock:
        # إذا مُهيَّأ مسبقًا ولم يُطلب إعادة المحاولة
        if _contacts_bridge_initialized and not force:
            return _contacts_bridge is not None

        # إذا كان الجسر جاهزًا، أعد استخدامه
        if _contacts_bridge is not None and not force:
            return True

        try:
            from java import jclass
            BridgeClass = jclass("com.example.myfirstapp.ContactsBridge")

            if BridgeClass.isReady():
                _contacts_bridge = BridgeClass.getInstance()
                _contacts_bridge_initialized = True
                log.info("📇 ContactsBridge متصل")
                return True
            else:
                log.warn("⚠️ ContactsBridge لم يُهيَّأ في Java بعد")
                _contacts_bridge = None
                _contacts_bridge_initialized = False
                return False

        except Exception as e:
            # على سطح المكتب، java module غير موجود → متوقع
            if "java" in str(e).lower() or "jclass" in str(e).lower():
                log.debug(f"ℹ️ ContactsBridge غير متاح (بيئة غير Android)")
            else:
                log.warn(f"⚠️ ContactsBridge فشل: {e}")
            _contacts_bridge = None
            _contacts_bridge_initialized = False
            return False


def is_contacts_bridge_ready() -> bool:
    with _contacts_bridge_lock:
        return _contacts_bridge is not None


# ═══════════════════════════════════════════════════════════════════
#                       CONFIG
# ═══════════════════════════════════════════════════════════════════

class BotConfig:
    def __init__(
        self,
        token: str,
        prefix: str = "!",
        owner_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        allowed_user_id: Optional[int] = None,
        enable_message_content: bool = True,
        enable_members: bool = False,
        enable_presences: bool = False,
        enable_all_intents: bool = False,
        activity_name: Optional[str] = None,
        activity_type: str = "listening",
        log_level: str = "INFO",
    ):
        self.token = token
        self.prefix = prefix
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.allowed_user_id = allowed_user_id
        self.enable_message_content = enable_message_content
        self.enable_members = enable_members
        self.enable_presences = enable_presences
        self.enable_all_intents = enable_all_intents
        self.activity_name = activity_name or f"{prefix}help"
        self.activity_type = activity_type
        self.log_level = log_level

    def __repr__(self):
        return (
            f"BotConfig(prefix={self.prefix!r}, owner={self.owner_id}, "
            f"guild={self.guild_id}, allowed={self.allowed_user_id}, "
            f"msg_content={self.enable_message_content}, "
            f"members={self.enable_members})"
        )


# ═══════════════════════════════════════════════════════════════════
#                       VERSION & ENV
# ═══════════════════════════════════════════════════════════════════

def get_version() -> str:
    return "7.0.0"


def get_environment_info() -> Dict[str, Any]:
    return {
        "version": get_version(),
        "python_version": sys.version.split()[0],
        "platform": sys.platform,
        "is_android": "android" in sys.platform.lower() or hasattr(sys, "getandroidapilevel"),
        "discord_available": DISCORD_AVAILABLE,
        "discord_version": DISCORD_VERSION,
        "contacts_bridge": is_contacts_bridge_ready(),
        "timestamp": datetime.now().isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
#                       TOKEN VALIDATION
# ═══════════════════════════════════════════════════════════════════

def validate_token(token: Optional[str]) -> tuple:
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
#                       CREATE BOT
# ═══════════════════════════════════════════════════════════════════

def create_bot(config: BotConfig):
    """إنشاء البوت مع كل الإصلاحات."""
    if not DISCORD_AVAILABLE:
        raise RuntimeError(f"discord.py غير متوفر: {_IMPORT_ERROR}")

    intents = make_intents(config)

    # ✅ owner_id يُمرَّر في الـ constructor (أكثر موثوقية)
    bot_kwargs = {
        "command_prefix": config.prefix,
        "intents": intents,
        "help_command": None,
        "case_insensitive": True,
        "strip_after_prefix": True,
    }

    if config.owner_id:
        bot_kwargs["owner_id"] = int(config.owner_id)

    bot = _commands.Bot(**bot_kwargs)

    if config.guild_id:
        log.info(f"🏰 Guild ID: {config.guild_id}")

    if config.allowed_user_id:
        log.info(f"👤 Allowed user: {config.allowed_user_id}")

    # ✅ ربط ContactsBridge (idempotent)
    _init_contacts_bridge()

    # ✅ is_owner آمن بدون API calls
    async def _is_owner(user) -> bool:
        """فحص المالك بدون API call إن أمكن."""
        try:
            # 1. فحص owner_id من Config (الأسرع)
            if config.owner_id and user.id == config.owner_id:
                return True

            # 2. فحص bot.owner_id (يُملأ بعد الاتصال)
            try:
                if bot.owner_id and user.id == bot.owner_id:
                    return True
            except Exception:
                pass

            # 3. fallback إلى API (نادر)
            return await bot.is_owner(user)
        except Exception:
            return False

    async def _is_allowed(user) -> bool:
        """المستخدم مسموح (المالك أو ALLOWED_USER_ID)."""
        try:
            if config.allowed_user_id and user.id == config.allowed_user_id:
                return True
            return await _is_owner(user)
        except Exception:
            return False

    # on_ready مرة واحدة (per bot instance)
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
            try:
                members = g.member_count
            except Exception:
                members = "?"
            log.info(f"   • {g.name} (id={g.id}, members={members})")

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
            log.info(f"📢 Status: {config.activity_type} {config.activity_name}")
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

        if isinstance(error, _commands.CommandNotFound):
            return

        if isinstance(error, _commands.NotOwner):
            try:
                await ctx.send("🚫 للمالك فقط")
            except Exception:
                pass
            return

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
                missing = ", ".join(error.missing_permissions)
                await ctx.send(f"🚫 البوت يفتقد: {missing}")
            except Exception:
                pass
            return

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

    @bot.event
    async def on_command(ctx):
        _state.increment_commands()

    # ═══════════════════ Public Commands ═══════════════════

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

        contacts_status = "✅ متصل" if is_contacts_bridge_ready() else "❌ غير متصل"

        await ctx.send(
            f"**🤖 JvRemotPy Info**\n```\n"
            f"Version    : {env['version']}\n"
            f"Python     : {env['python_version']}\n"
            f"Platform   : {env['platform']}\n"
            f"Android    : {env['is_android']}\n"
            f"discord.py : {env['discord_version']}\n"
            f"Prefix     : {config.prefix}\n"
            f"Owner ID   : {config.owner_id or '—'}\n"
            f"Guild ID   : {config.guild_id or '—'}\n"
            f"Allowed    : {config.allowed_user_id or '—'}\n"
            f"Contacts   : {contacts_status}\n"
            f"Uptime     : {uptime}\n"
            f"Guilds     : {len(bot.guilds)}\n"
            f"Commands   : {_state.get_command_count()}\n"
            f"Latency    : {round(bot.latency * 1000)}ms\n"
            f"```"
        )

    @bot.command(name="health")
    async def cmd_health(ctx):
        """فحص صحة شامل للبوت."""
        start = _state.get_start_time()
        uptime_s = int(time.time() - start) if start else 0

        status_lines = [
            "**🏥 Health Report**",
            "```",
            f"Bot User     : {bot.user}",
            f"Bot ID       : {bot.user.id if bot.user else 'N/A'}",
            f"Latency      : {round(bot.latency * 1000)}ms",
            f"Guilds       : {len(bot.guilds)}",
            f"Users cached : {len(bot.users)}",
            f"Uptime       : {uptime_s}s",
            f"Commands run : {_state.get_command_count()}",
            f"Contacts     : {'✅' if is_contacts_bridge_ready() else '❌'}",
            f"is_running   : {_state.is_running()}",
            f"Last error   : {_state.get_error() or '—'}",
            "```",
        ]
        await ctx.send("\n".join(status_lines))

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

    # ═══════════════════ Contacts Commands ═══════════════════

    @bot.command(name="contacts")
    @_commands.cooldown(1, 30.0, _commands.BucketType.user)  # 30 ثانية cooldown
    async def cmd_contacts(ctx, *, search: str = ""):
        """قراءة جهات الاتصال (cooldown 30s)."""
        if not await _is_allowed(ctx.author):
            await ctx.send("🚫 للمالك أو المستخدم المسموح فقط")
            return

        # محاولة إعادة الربط إذا لم يكن جاهزًا
        if not is_contacts_bridge_ready():
            _init_contacts_bridge(force=True)

        if not is_contacts_bridge_ready():
            await ctx.send(
                "❌ جسر جهات الاتصال غير متاح.\n"
                "تأكد من:\n"
                "1. فتح التطبيق\n"
                "2. منح صلاحية جهات الاتصال\n"
                "3. استخدام `!reload_bridge`"
            )
            return

        try:
            import json
            bridge = _contacts_bridge
            data = bridge.getContactsJson(search or "")
            contacts = json.loads(data)

            if not contacts:
                await ctx.send("📭 لا توجد نتائج")
                return

            lines = []
            for c in contacts[:20]:
                name = c.get('name', '—')
                number = c.get('number', '—')
                email = c.get('email', '')
                line = f"`{name}` — `{number}`"
                if email:
                    line += f" — `{email}`"
                lines.append(line)

            header = f"**📇 جهات الاتصال** ({len(contacts)} نتيجة)\n"
            msg = header + "\n".join(lines)
            if len(contacts) > 20:
                msg += f"\n_... و {len(contacts) - 20} أخرى_"

            await ctx.send(msg[:1900])

        except Exception as e:
            log.exception("contacts command failed", e)
            await ctx.send(f"❌ خطأ: `{e}`")

    @bot.command(name="contactscount")
    @_commands.cooldown(1, 10.0, _commands.BucketType.user)
    async def cmd_contactscount(ctx):
        if not await _is_allowed(ctx.author):
            await ctx.send("🚫 للمالك أو المستخدم المسموح فقط")
            return

        if not is_contacts_bridge_ready():
            _init_contacts_bridge(force=True)

        if not is_contacts_bridge_ready():
            await ctx.send("❌ جسر جهات الاتصال غير متاح")
            return

        try:
            count = _contacts_bridge.getContactsCount()
            await ctx.send(f"📇 العدد: `{count}` جهة اتصال")
        except Exception as e:
            log.exception("contactscount failed", e)
            await ctx.send(f"❌ خطأ: `{e}`")

    @bot.command(name="reload_bridge")
    async def cmd_reload_bridge(ctx):
        """إعادة محاولة ربط ContactsBridge."""
        if not await _is_owner(ctx.author):
            await ctx.send("🚫 للمالك فقط")
            return

        success = _init_contacts_bridge(force=True)
        if success:
            await ctx.send("✅ ContactsBridge متصل")
        else:
            await ctx.send("❌ ContactsBridge لا يزال غير متاح")

    # ═══════════════════ Help ═══════════════════

    @bot.command(name="help")
    async def cmd_help(ctx):
        cmds = [
            ("ping", "اختبار سرعة"),
            ("hello", "ترحيب"),
            ("version", "الإصدار"),
            ("info", "معلومات البوت"),
            ("health", "فحص الصحة"),
            ("uptime", "مدة التشغيل"),
            ("echo <نص>", "إعادة النص"),
            ("say <نص>", "إرسال رسالة"),
            ("serverinfo", "معلومات السيرفر"),
            ("userinfo [@user]", "معلومات مستخدم"),
            ("avatar [@user]", "صورة المستخدم"),
            ("contacts [بحث]", "📇 جهات الاتصال"),
            ("contactscount", "📇 عدد جهات الاتصال"),
            ("help", "هذه القائمة"),
            ("—", "— أوامر المالك —"),
            ("stop", "إيقاف البوت"),
            ("reload", "إعادة تحميل main.py"),
            ("reload_bridge", "إعادة ربط جهات الاتصال"),
            ("logs [n]", "آخر n سطر من السجل"),
            ("exec <كود>", "تنفيذ Python"),
        ]
        lines = [f"`{config.prefix}{c[0]}` — {c[1]}" for c in cmds]
        await ctx.send("**📋 الأوامر:**\n" + "\n".join(lines))

    # ═══════════════════ Owner Commands ═══════════════════

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

    @bot.command(name="logs")
    async def cmd_logs(ctx, n: int = 20):
        """عرض آخر n سطر من السجل."""
        if not await _is_owner(ctx.author):
            await ctx.send("🚫 للمالك فقط")
            return

        n = max(1, min(n, 100))
        history = log.get_history(n)
        if not history:
            await ctx.send("📭 لا يوجد سجل")
            return

        # تقسيم على رسائل متعددة إذا طويل
        text = "\n".join(history)
        if len(text) > 1900:
            # إرسال آخر 1900 حرف
            text = text[-1900:]

        await ctx.send(f"**📜 آخر {len(history)} سطر:**\n```\n{text}\n```")

    @bot.command(name="exec")
    async def cmd_exec(ctx, *, code: str = ""):
        if not await _is_owner(ctx.author):
            await ctx.send("🚫 للمالك فقط")
            return
        if not code:
            await ctx.send("⚠️ استخدم: `!exec <كود>`")
            return

        buf = io.StringIO()
        local_vars = {}
        try:
            with contextlib.redirect_stdout(buf):
                exec(code, {"bot": bot, "discord": discord, "log": log}, local_vars)

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
    owner_id: Optional[int] = None,
    guild_id: Optional[int] = None,
    allowed_user_id: Optional[int] = None,
    enable_message_content: bool = True,
    enable_members: bool = False,
    enable_presences: bool = False,
    enable_all_intents: bool = False,
) -> str:
    """
    ⭐ الدالة الرئيسية — يستدعيها BotService من Java.
    تستقبل كل الإعدادات كوسائط.
    """
    log.info("=" * 60)
    log.info(f"🚀 run_bot() — v{get_version()}")
    log.info(f"👑 owner={owner_id} | guild={guild_id} | allowed={allowed_user_id}")
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

    # إيقاف البوت القديم
    old_bot = _state.get_bot()
    if old_bot and not old_bot.is_closed():
        log.warn("⚠️ Stopping old bot first...")
        try:
            _state.get_stop_event().set()
            loop = getattr(old_bot, "loop", None)
            if loop and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except Exception as e:
                    log.debug(f"loop.stop failed: {e}")
            time.sleep(2)
        except Exception as e:
            log.warn(f"Stop old bot failed: {e}")

    _state.reset()

    # ✅ تنظيف owner_id/guild_id/allowed_user_id
    def _safe_int(v):
        try:
            if v is None:
                return None
            iv = int(v)
            return iv if iv > 0 else None
        except (TypeError, ValueError):
            return None

    config = BotConfig(
        token=token,
        prefix=prefix,
        owner_id=_safe_int(owner_id),
        guild_id=_safe_int(guild_id),
        allowed_user_id=_safe_int(allowed_user_id),
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
        # ✅ فحص loop قبل الاستخدام
        loop = getattr(bot, "loop", None)
        if loop and not loop.is_closed() and loop.is_running():
            loop.call_soon_threadsafe(loop.stop)
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
        "contacts_bridge": is_contacts_bridge_ready(),
        "command_count": _state.get_command_count(),
    }


# ═══════════════════════════════════════════════════════════════════
#                       MAIN (Local Testing)
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info("=== Local Test ===")
    log.info(run("اختبار محلي"))
    log.info(f"Environment: {get_environment_info()}")
