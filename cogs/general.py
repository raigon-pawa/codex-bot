"""General-purpose info & utility commands (hybrid: work as `/cmd` and `!cmd`)."""

from __future__ import annotations

import contextlib
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


class HelpView(discord.ui.View):
    """Paginated command help: one category per page, with a jump dropdown.

    Only the invoker can drive it — matters for `?help`, where the message is
    public (a slash `/help` is ephemeral, so the check is just belt-and-braces).
    """

    def __init__(self, pages: list[tuple[str, str]], author_id: int) -> None:
        super().__init__(timeout=180)
        self.pages = pages
        self.author_id = author_id
        self.index = 0
        self.message: discord.Message | None = None
        self.jump.options = [
            discord.SelectOption(label=label, value=str(i))
            for i, (label, _body) in enumerate(pages[:25])  # Discord caps a select at 25
        ]
        self._sync()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This isn't your help menu — run `/help` (or `?help`) yourself.", ephemeral=True
            )
            return False
        return True

    def render(self) -> discord.Embed:
        label, body = self.pages[self.index]
        embed = discord.Embed(title=f"Codex — {label}", description=body, color=config.COLOR)
        embed.set_footer(text=f"Page {self.index + 1}/{len(self.pages)}")
        return embed

    def _sync(self) -> None:
        self.prev.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        for option in self.jump.options:
            option.default = int(option.value) == self.index

    async def _show(self, interaction: discord.Interaction) -> None:
        self._sync()
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.select(placeholder="Jump to a category…", row=0)
    async def jump(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        self.index = int(select.values[0])
        await self._show(interaction)

    @discord.ui.button(label="Prev", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = max(0, self.index - 1)
        await self._show(interaction)

    @discord.ui.button(label="Next", emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        await self._show(interaction)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True  # type: ignore[attr-defined]
        if self.message is not None:
            with contextlib.suppress(discord.HTTPException):
                await self.message.edit(view=self)


class General(commands.Cog):
    """Everyday utility commands."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(description="Check Codex's latency.")
    async def ping(self, ctx: commands.Context) -> None:
        ws_latency = round(self.bot.latency * 1000)
        start = time.perf_counter()
        message = await ctx.send("Pinging…")
        api_latency = round((time.perf_counter() - start) * 1000)

        embed = discord.Embed(title="🏓 Pong!", color=config.COLOR)
        embed.add_field(name="Gateway", value=f"{ws_latency} ms")
        embed.add_field(name="API", value=f"{api_latency} ms")
        await message.edit(content=None, embed=embed)

    @commands.hybrid_command(description="Show information about this server.")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context) -> None:
        guild = ctx.guild
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
        await ctx.send(embed=embed)

    @commands.hybrid_command(description="Show information about a member.")
    @app_commands.describe(member="The member to look up (defaults to you).")
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        member = member or ctx.author  # type: ignore[assignment]
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
        await ctx.send(embed=embed)

    def _help_pages(self) -> list[tuple[str, str]]:
        """One (label, body) page per feature category, in display order."""
        pages: list[tuple[str, str]] = []
        shown = set()

        def add_section(label: str, cog: commands.Cog) -> None:
            cmds = sorted(cog.get_app_commands(), key=lambda c: c.name)
            if cmds:
                body = "\n".join(_format_entry(c) for c in cmds)
                pages.append((label, body[:4096]))

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
            pages.append(("🖱️ Context menus", "\n".join(lines)))
        return pages

    @commands.hybrid_command(description="Browse Codex's commands by category.")
    async def help(self, ctx: commands.Context) -> None:
        pages = self._help_pages()
        if not pages:
            await ctx.send("No commands are loaded.", ephemeral=True)
            return
        view = HelpView(pages, author_id=ctx.author.id)
        view.message = await ctx.send(embed=view.render(), view=view, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
