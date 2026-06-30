"""Interactive UI showcase: buttons, select menus, modals, and context menus.

The PanelView uses `timeout=None` + `custom_id`s and is registered with
`bot.add_view`, so its buttons keep working even after the bot restarts
("persistent views").
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import config


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
        await interaction.response.send_message(
            f"Reported message by **{message.author}** to the moderators. 🛡️", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    bot.add_view(PanelView())  # register the persistent view
    await bot.add_cog(Components(bot))
