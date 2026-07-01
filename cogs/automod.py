"""Moderation automation: native AutoMod rule management + an audit mod-log.

- /automod keyword|preset|mentions|list|remove — create and manage Discord's
  built-in AutoMod rules (server-side keyword/spam/mention filtering) without
  leaving chat. Alerts are routed to the mod-log channel when one is set.
- /logging set|disable|status — pick a channel that Codex streams moderation
  events to: message edits/deletes, member joins/leaves, bans, and every
  AutoMod rule that fires.

The log channel is stored in `guild_config.log_channel` (created in
`core/database.py`) and cached in memory so the hot listeners avoid a DB hit.
Message edit/delete listeners only fire for messages still in the bot's cache —
that's fine for a friends' server and needs no extra storage.
"""

from __future__ import annotations

import contextlib

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import config
from core.database import init_db

_ADMIN = discord.Permissions(manage_guild=True)

# Per-event colours so a glance at the mod-log tells you what happened.
_RED = discord.Color.red()
_ORANGE = discord.Color.orange()
_GREEN = discord.Color.green()
_GREY = discord.Color.light_grey()
_DARK_RED = discord.Color.dark_red()

_PRESETS = {
    "profanity": "Profanity",
    "sexual_content": "Sexual content",
    "slurs": "Slurs",
}


def _clip(text: str, limit: int = 1024) -> str:
    """Trim text to fit an embed field, leaving room for an ellipsis."""
    text = text or "*(no text content)*"
    return text if len(text) <= limit else text[: limit - 1] + "…"


class AutoMod(commands.Cog):
    automod = app_commands.Group(
        name="automod",
        description="Manage Discord's built-in AutoMod rules.",
        default_permissions=_ADMIN,
        guild_only=True,
    )
    logging = app_commands.Group(
        name="logging",
        description="Stream moderation events to a mod-log channel.",
        default_permissions=_ADMIN,
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # guild_id -> log channel id (or None if disabled). Absent key = not loaded.
        self._log_cache: dict[int, int | None] = {}

    async def cog_load(self) -> None:
        await init_db()

    # ── Log-channel plumbing ──────────────────────────────────
    async def _log_channel_id(self, guild_id: int) -> int | None:
        if guild_id not in self._log_cache:
            async with aiosqlite.connect(config.DB_PATH) as db:
                cursor = await db.execute(
                    "SELECT log_channel FROM guild_config WHERE guild_id=?", (guild_id,)
                )
                row = await cursor.fetchone()
            self._log_cache[guild_id] = row[0] if row else None
        return self._log_cache[guild_id]

    async def _send_log(self, guild: discord.Guild, embed: discord.Embed) -> None:
        channel_id = await self._log_channel_id(guild.id)
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        if not channel.permissions_for(guild.me).send_messages:
            return
        with contextlib.suppress(discord.HTTPException):
            await channel.send(embed=embed)

    # ── /logging ──────────────────────────────────────────────
    @logging.command(name="set", description="Send the moderation log to a channel.")
    @app_commands.describe(channel="The channel to post moderation events in")
    async def logging_set(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        me = interaction.guild.me  # type: ignore[union-attr]
        if not channel.permissions_for(me).send_messages:
            await interaction.response.send_message(
                f"I can't send messages in {channel.mention} — grant me access there first.",
                ephemeral=True,
            )
            return
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "INSERT INTO guild_config (guild_id, log_channel) VALUES (?,?) "
                "ON CONFLICT(guild_id) DO UPDATE SET log_channel=excluded.log_channel",
                (interaction.guild_id, channel.id),
            )
            await db.commit()
        self._log_cache[interaction.guild_id] = channel.id  # type: ignore[index]
        await interaction.response.send_message(
            f"📓 Moderation events will now be logged to {channel.mention}.", ephemeral=True
        )

    @logging.command(name="disable", description="Stop logging moderation events.")
    async def logging_disable(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "UPDATE guild_config SET log_channel=NULL WHERE guild_id=?",
                (interaction.guild_id,),
            )
            await db.commit()
        self._log_cache[interaction.guild_id] = None  # type: ignore[index]
        await interaction.response.send_message("Logging disabled.", ephemeral=True)

    @logging.command(name="status", description="Show the current mod-log channel.")
    async def logging_status(self, interaction: discord.Interaction) -> None:
        channel_id = await self._log_channel_id(interaction.guild_id)  # type: ignore[arg-type]
        text = f"Logging to <#{channel_id}>." if channel_id else "Logging is disabled."
        await interaction.response.send_message(text, ephemeral=True)

    # ── /automod ──────────────────────────────────────────────
    async def _alert_action(self, guild_id: int) -> discord.AutoModRuleAction | None:
        """An action that copies AutoMod hits into the mod-log, if one is set."""
        channel_id = await self._log_channel_id(guild_id)
        if channel_id is None:
            return None
        return discord.AutoModRuleAction(channel_id=channel_id)

    async def _create_rule(
        self,
        interaction: discord.Interaction,
        *,
        name: str,
        trigger: discord.AutoModTrigger,
        block_message: str,
    ) -> None:
        actions = [
            discord.AutoModRuleAction(
                type=discord.AutoModRuleActionType.block_message, custom_message=block_message
            )
        ]
        alert = await self._alert_action(interaction.guild_id)  # type: ignore[arg-type]
        if alert is not None:
            actions.append(alert)
        try:
            rule = await interaction.guild.create_automod_rule(  # type: ignore[union-attr]
                name=name,
                event_type=discord.AutoModRuleEventType.message_send,
                trigger=trigger,
                actions=actions,
                enabled=True,
                reason=f"Created by {interaction.user} via /automod",
            )
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"Discord rejected that rule: {exc.text or exc}", ephemeral=True
            )
            return
        note = "" if alert else " Set a mod-log with `/logging set` to get alerts here."
        await interaction.response.send_message(
            f"🛡️ Created AutoMod rule **{rule.name}** (`{rule.id}`).{note}", ephemeral=True
        )

    @automod.command(name="keyword", description="Block messages containing words/phrases.")
    @app_commands.describe(words="Comma-separated words or phrases to block (use * for wildcards)")
    @app_commands.checks.bot_has_permissions(manage_guild=True)
    async def automod_keyword(self, interaction: discord.Interaction, words: str) -> None:
        keywords = [w.strip()[:60] for w in words.split(",") if w.strip()][:100]
        if not keywords:
            await interaction.response.send_message(
                "Give me at least one word, e.g. `spoiler, n-word, buy now`.", ephemeral=True
            )
            return
        trigger = discord.AutoModTrigger(
            type=discord.AutoModRuleTriggerType.keyword, keyword_filter=keywords
        )
        await self._create_rule(
            interaction,
            name=f"Codex keywords ({len(keywords)})",
            trigger=trigger,
            block_message="That message was blocked by the server's word filter.",
        )

    @automod.command(name="preset", description="Block a built-in category (profanity/slurs/…).")
    @app_commands.describe(preset="Which Discord-maintained word list to block")
    @app_commands.choices(
        preset=[app_commands.Choice(name=v, value=k) for k, v in _PRESETS.items()]
    )
    @app_commands.checks.bot_has_permissions(manage_guild=True)
    async def automod_preset(
        self, interaction: discord.Interaction, preset: app_commands.Choice[str]
    ) -> None:
        presets = discord.AutoModPresets(**{preset.value: True})
        trigger = discord.AutoModTrigger(
            type=discord.AutoModRuleTriggerType.keyword_preset, presets=presets
        )
        await self._create_rule(
            interaction,
            name=f"Codex preset: {preset.name}",
            trigger=trigger,
            block_message="That message was blocked by the server's content filter.",
        )

    @automod.command(name="mentions", description="Block messages with too many mentions.")
    @app_commands.describe(limit="Max user/role mentions allowed in one message (1-50)")
    @app_commands.checks.bot_has_permissions(manage_guild=True)
    async def automod_mentions(
        self, interaction: discord.Interaction, limit: app_commands.Range[int, 1, 50]
    ) -> None:
        trigger = discord.AutoModTrigger(
            type=discord.AutoModRuleTriggerType.mention_spam, mention_limit=limit
        )
        await self._create_rule(
            interaction,
            name=f"Codex mention limit ({limit})",
            trigger=trigger,
            block_message=f"Please keep it under {limit} mentions per message.",
        )

    @automod.command(name="list", description="List this server's AutoMod rules.")
    @app_commands.checks.bot_has_permissions(manage_guild=True)
    async def automod_list(self, interaction: discord.Interaction) -> None:
        rules = await interaction.guild.fetch_automod_rules()  # type: ignore[union-attr]
        if not rules:
            await interaction.response.send_message(
                "No AutoMod rules yet — create one with `/automod keyword`.", ephemeral=True
            )
            return
        lines = [
            f"`{r.id}` — **{r.name}** · {r.trigger.type.name} · "
            f"{'🟢 on' if r.enabled else '⚪ off'}"
            for r in rules
        ]
        embed = discord.Embed(
            title="🛡️ AutoMod rules",
            description="\n".join(lines)[:4096],
            color=config.COLOR,
        )
        embed.set_footer(text="Remove one with /automod remove <id>")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod.command(name="remove", description="Delete an AutoMod rule by its ID.")
    @app_commands.describe(rule_id="The rule ID (see /automod list)")
    @app_commands.checks.bot_has_permissions(manage_guild=True)
    async def automod_remove(self, interaction: discord.Interaction, rule_id: str) -> None:
        if not rule_id.isdigit():
            await interaction.response.send_message("That's not a valid rule ID.", ephemeral=True)
            return
        guild = interaction.guild
        assert guild is not None
        try:
            rule = await guild.fetch_automod_rule(int(rule_id))
            await rule.delete(reason=f"Removed by {interaction.user} via /automod")
        except discord.NotFound:
            await interaction.response.send_message(
                "No rule with that ID — check `/automod list`.", ephemeral=True
            )
            return
        await interaction.response.send_message(f"🗑️ Deleted **{rule.name}**.", ephemeral=True)

    # ── Audit listeners ───────────────────────────────────────
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        embed = discord.Embed(
            title="🗑️ Message deleted",
            description=_clip(message.content, 2048),
            color=_RED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention)
        if message.attachments:
            embed.add_field(name="Attachments", value=str(len(message.attachments)))
        embed.set_footer(text=f"Author ID: {message.author.id}")
        await self._send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.guild is None or after.author.bot or before.content == after.content:
            return
        embed = discord.Embed(
            title="✏️ Message edited",
            color=_ORANGE,
            timestamp=discord.utils.utcnow(),
            description=f"[Jump to message]({after.jump_url})",
        )
        embed.set_author(name=str(after.author), icon_url=after.author.display_avatar.url)
        embed.add_field(name="Before", value=_clip(before.content), inline=False)
        embed.add_field(name="After", value=_clip(after.content), inline=False)
        embed.set_footer(text=f"Author ID: {after.author.id}")
        await self._send_log(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title="📥 Member joined",
            description=f"{member.mention} · {member}",
            color=_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="Account created", value=discord.utils.format_dt(member.created_at, "R")
        )
        embed.set_footer(text=f"User ID: {member.id}")
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed = discord.Embed(
            title="📤 Member left",
            description=f"{member.mention} · {member}",
            color=_GREY,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        if roles:
            embed.add_field(name="Roles", value=_clip(", ".join(roles)), inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        await self._send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(
            title="🔨 Member banned",
            description=f"{user.mention} · {user}",
            color=_DARK_RED,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"User ID: {user.id}")
        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(
            title="♻️ Member unbanned",
            description=f"{user.mention} · {user}",
            color=_GREEN,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"User ID: {user.id}")
        await self._send_log(guild, embed)

    @commands.Cog.listener()
    async def on_automod_action(self, execution: discord.AutoModAction) -> None:
        guild = execution.guild
        if guild is None:
            return
        embed = discord.Embed(
            title="🛡️ AutoMod triggered",
            description=_clip(execution.content, 2048),
            color=_ORANGE,
            timestamp=discord.utils.utcnow(),
        )
        if execution.member is not None:
            embed.set_author(
                name=str(execution.member), icon_url=execution.member.display_avatar.url
            )
        embed.add_field(name="Rule trigger", value=execution.rule_trigger_type.name)
        if execution.matched_keyword:
            embed.add_field(name="Matched", value=_clip(execution.matched_keyword, 256))
        if execution.channel is not None:
            embed.add_field(name="Channel", value=execution.channel.mention)
        embed.set_footer(text=f"User ID: {execution.user_id}")
        await self._send_log(guild, embed)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You need the **Manage Server** permission for that."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "I need the **Manage Server** permission to manage AutoMod rules."
        else:
            msg = f"Something went wrong: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoMod(bot))
