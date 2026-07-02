"""Interactive UI showcase: buttons, select menus, modals, and context menus.

The PanelView uses `timeout=None` + `custom_id`s and is registered with
`bot.add_view`, so its buttons keep working even after the bot restarts
("persistent views").
"""

from __future__ import annotations

import contextlib

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import config
from core.database import init_db


class FeedbackModal(discord.ui.Modal, title="Send Feedback to Codex"):
    summary = discord.ui.TextInput(label="Summary", max_length=100)
    details = discord.ui.TextInput(
        label="Details",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            f"Thanks! Logged your feedback: **{self.summary.value}**", ephemeral=True
        )


class PanelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)  # persistent

    @discord.ui.button(
        label="Click me",
        style=discord.ButtonStyle.primary,
        emoji="✨",
        custom_id="codex:panel:click",
    )
    async def click(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_message("You clicked the button! 🎉", ephemeral=True)

    @discord.ui.button(
        label="Feedback",
        style=discord.ButtonStyle.secondary,
        custom_id="codex:panel:feedback",
    )
    async def feedback(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.send_modal(FeedbackModal())

    @discord.ui.select(
        placeholder="Pick your favourite feature…",
        custom_id="codex:panel:select",
        options=[
            discord.SelectOption(label="Study tools", emoji="📚"),
            discord.SelectOption(label="AI assistance", emoji="🤖"),
            discord.SelectOption(label="Gaming utilities", emoji="🎮"),
            discord.SelectOption(label="Social features", emoji="💬"),
        ],
    )
    async def pick(self, interaction: discord.Interaction, select: discord.ui.Select) -> None:
        await interaction.response.send_message(
            f"Nice — **{select.values[0]}** it is!", ephemeral=True
        )


class Components(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        # Context-menu commands can't be defined inside a class body, so we
        # build them here and register them on the tree.
        self.ctx_avatar = app_commands.ContextMenu(name="Avatar", callback=self.avatar_ctx)
        self.ctx_report = app_commands.ContextMenu(name="Report Message", callback=self.report_ctx)
        bot.tree.add_command(self.ctx_avatar)
        bot.tree.add_command(self.ctx_report)

    async def cog_load(self) -> None:
        await init_db()

    async def _mod_log(self, guild: discord.Guild) -> discord.TextChannel | None:
        """The mod-log channel set via `/logging set`, if any and writable."""
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT log_channel FROM guild_config WHERE guild_id=?", (guild.id,)
            )
            row = await cursor.fetchone()
        channel_id = row[0] if row else None
        if channel_id:
            channel = guild.get_channel(channel_id)
            if (
                isinstance(channel, discord.TextChannel)
                and channel.permissions_for(guild.me).send_messages
            ):
                return channel
        return None

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_avatar.name, type=self.ctx_avatar.type)
        self.bot.tree.remove_command(self.ctx_report.name, type=self.ctx_report.type)

    @app_commands.command(description="Open the interactive Codex panel.")
    async def panel(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Codex Control Panel",
            description="Buttons, a select menu, and a modal — all in one message.",
            color=config.COLOR,
        )
        await interaction.response.send_message(embed=embed, view=PanelView())

    # ── Context-menu callbacks (right-click → Apps) ───────────
    async def avatar_ctx(self, interaction: discord.Interaction, member: discord.Member) -> None:
        embed = discord.Embed(title=f"{member}'s avatar", color=config.COLOR)
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def report_ctx(self, interaction: discord.Interaction, message: discord.Message) -> None:
        guild = interaction.guild
        channel = await self._mod_log(guild) if guild is not None else None
        if channel is None:
            await interaction.response.send_message(
                "Thanks for the report — but no mod-log channel is set. "
                "An admin can add one with `/logging set`.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="🚩 Message reported",
            description=message.content[:2048] or "*(no text content)*",
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Reported by", value=interaction.user.mention)
        embed.add_field(name="Channel", value=message.channel.mention)
        embed.add_field(name="Message", value=f"[Jump]({message.jump_url})", inline=False)
        embed.set_footer(text=f"Author ID: {message.author.id}")
        with contextlib.suppress(discord.HTTPException):
            await channel.send(embed=embed)
        await interaction.response.send_message(
            "🛡️ Reported to the moderators — thanks.", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_view(PanelView())  # register the persistent view
    await bot.add_cog(Components(bot))
