"""Moderation commands. All gated behind real Discord permissions.

`default_permissions` hides the command in the UI from members who lack the
permission; `has_permissions` enforces it server-side; `bot_has_permissions`
checks Codex itself can perform the action.
"""

from __future__ import annotations

import datetime

import discord
from discord import app_commands
from discord.ext import commands


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Kick a member from the server.")
    @app_commands.describe(member="Who to kick", reason="Reason (shown in audit log)")
    @app_commands.guild_only()
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(
        self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None
    ) -> None:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked **{member}**. {reason or ''}")

    @app_commands.command(description="Ban a member from the server.")
    @app_commands.describe(member="Who to ban", reason="Reason (shown in audit log)")
    @app_commands.guild_only()
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(
        self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None
    ) -> None:
        await member.ban(reason=reason, delete_message_days=0)
        await interaction.response.send_message(f"🔨 Banned **{member}**. {reason or ''}")

    @app_commands.command(description="Time a member out for a number of minutes.")
    @app_commands.describe(member="Who to time out", minutes="1-40320 (28 days max)")
    @app_commands.guild_only()
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str | None = None,
    ) -> None:
        until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.timeout(until, reason=reason)
        await interaction.response.send_message(f"🔇 Timed out **{member}** for {minutes} min.")

    @app_commands.command(description="Bulk-delete recent messages in this channel.")
    @app_commands.describe(amount="How many messages to delete (1-100)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    async def clear(
        self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        assert isinstance(interaction.channel, discord.TextChannel)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} messages.", ephemeral=True)

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            msg = "You don't have permission to do that."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "I'm missing the permissions to do that — check my role."
        else:
            msg = f"Something went wrong: {error}"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
