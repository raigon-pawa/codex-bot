"""General-purpose slash commands: info & utility."""

from __future__ import annotations

import time

import discord
from discord import app_commands
from discord.ext import commands

import config

# Cog class name → the section it appears under in /help, in display order.
# Cogs not listed here still show up (under their own name) so new ones aren't
# silently dropped.
_HELP_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("General", "🧭 General"),
    ("AI", "🤖 AI"),
    ("Study", "📚 Study"),
    ("Social", "📈 Leveling"),
    ("Roles", "🎭 Roles"),
    ("Gaming", "🎮 Gaming"),
    ("Music", "🎵 Music"),
    ("Moderation", "🛡️ Moderation"),
    ("AutoMod", "🚔 AutoMod & logging"),
    ("Premium", "✨ Premium"),
    ("Components", "🧩 Components"),
)


def _format_entry(command: app_commands.Command | app_commands.Group) -> str:
    """One help line: a group lists its subcommands, a command its description."""
    if isinstance(command, app_commands.Group):
        subs = " · ".join(sub.name for sub in command.commands)
        return f"`/{command.name}` — {subs}"
    return f"`/{command.name}` — {command.description}"


class General(commands.Cog):
    """Everyday utility commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(description="Check Codex's latency.")
    async def ping(self, interaction: discord.Interaction) -> None:
        ws_latency = round(self.bot.latency * 1000)
        start = time.perf_counter()
        await interaction.response.send_message("Pinging…")
        api_latency = round((time.perf_counter() - start) * 1000)

        embed = discord.Embed(title="🏓 Pong!", color=config.COLOR)
        embed.add_field(name="Gateway", value=f"{ws_latency} ms")
        embed.add_field(name="API", value=f"{api_latency} ms")
        await interaction.edit_original_response(content=None, embed=embed)

    @app_commands.command(description="Show information about this server.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        embed = discord.Embed(title=guild.name, color=config.COLOR)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>")
        embed.add_field(name="Members", value=str(guild.member_count))
        embed.add_field(name="Channels", value=str(len(guild.channels)))
        embed.add_field(name="Roles", value=str(len(guild.roles)))
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count))
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "R"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Show information about a member.")
    @app_commands.describe(member="The member to look up (defaults to you).")
    @app_commands.guild_only()
    async def userinfo(
        self, interaction: discord.Interaction, member: discord.Member | None = None
    ) -> None:
        member = member or interaction.user  # type: ignore[assignment]
        colour = member.color if member.color.value else config.COLOR
        embed = discord.Embed(title=str(member), color=colour)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="ID", value=str(member.id))
        joined = discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "—"
        embed.add_field(name="Joined", value=joined)
        created = discord.utils.format_dt(member.created_at, "R")
        embed.add_field(name="Account created", value=created)
        roles = [r.mention for r in reversed(member.roles[1:])]  # skip @everyone
        embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) or "None", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="List Codex's commands by category.")
    async def help(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Codex — Command Help",
            description="Commands grouped by feature. Groups show their subcommands.",
            color=config.COLOR,
        )

        def add_section(label: str, cog: commands.Cog) -> None:
            cmds = sorted(cog.get_app_commands(), key=lambda c: c.name)
            if cmds:
                value = "\n".join(_format_entry(c) for c in cmds)
                embed.add_field(name=label, value=value[:1024], inline=False)

        shown = set()
        for cog_name, label in _HELP_CATEGORIES:
            cog = self.bot.get_cog(cog_name)
            if cog is not None:
                shown.add(cog_name)
                add_section(label, cog)
        # Any cog not in the category map (e.g. one added later).
        for cog_name, cog in sorted(self.bot.cogs.items()):
            if cog_name not in shown:
                add_section(f"📦 {cog_name}", cog)

        # Right-click (context menu) commands live on the tree, not in a cog.
        menus = self.bot.tree.get_commands(
            type=discord.AppCommandType.user
        ) + self.bot.tree.get_commands(type=discord.AppCommandType.message)
        if menus:
            lines = [f"`{m.name}` (right-click)" for m in sorted(menus, key=lambda m: m.name)]
            embed.add_field(name="🖱️ Context menus", value="\n".join(lines), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
