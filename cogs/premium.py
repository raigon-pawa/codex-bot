"""Premium tier via Discord App Subscriptions (SKUs + entitlements).

Discord hosts the payment: you create a subscription **SKU** in the Developer
Portal (Monetization), and Discord grants subscribers an **entitlement** to it.
Every interaction carries the caller's entitlements, so gating a command is just
a membership check — no billing code, webhooks, or card handling on our side.

Setup:
1. Developer Portal → Monetization → create a subscription SKU.
2. `/premium skus` (owner-only) to read its ID.
3. Put that ID in `PREMIUM_SKU_ID` (.env) and restart.

With `PREMIUM_SKU_ID` unset the cog still loads; premium simply reads as
"not configured", so the bot runs fine before monetization is approved.
"""

from __future__ import annotations

import contextlib
import logging

import discord
from discord import app_commands
from discord.ext import commands

import config

log = logging.getLogger("codex")

_GOLD = discord.Color.gold()

# What the paid tier unlocks. Purely cosmetic copy for /premium perks — wire the
# actual gating into other cogs with the same entitlement check used here.
_PERKS = (
    "🎵 Longer music queue and higher-quality audio",
    "🧠 Priority AI replies on the top-tier model",
    "🎴 Unlimited flashcard decks",
    "✨ A shiny supporter badge on `/premium status`",
)


class UpgradeView(discord.ui.View):
    """A single native premium button; Discord renders the store/upgrade flow."""

    def __init__(self, sku_id: int) -> None:
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(style=discord.ButtonStyle.premium, sku_id=sku_id))


class Premium(commands.Cog):
    premium = app_commands.Group(name="premium", description="Premium subscription tools.")

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _entitled(self, interaction: discord.Interaction) -> bool:
        """True if this interaction carries a live entitlement to our SKU."""
        if config.PREMIUM_SKU_ID is None:
            return False
        return any(
            ent.sku_id == config.PREMIUM_SKU_ID and not ent.is_expired()
            for ent in interaction.entitlements
        )

    def _upgrade_prompt(self, description: str) -> tuple[discord.Embed, UpgradeView]:
        embed = discord.Embed(title="✨ Codex Premium", description=description, color=_GOLD)
        if config.PREMIUM_SKU_ID is None:
            # MISSING (not None) so send_message omits the view — passing None
            # makes discord.py call None.is_finished() and crash.
            return embed, discord.utils.MISSING
        return embed, UpgradeView(config.PREMIUM_SKU_ID)

    # ── Commands ──────────────────────────────────────────────
    @premium.command(name="status", description="Check your premium status.")
    async def status(self, interaction: discord.Interaction) -> None:
        if self._entitled(interaction):
            embed = discord.Embed(
                title="✨ Premium active",
                description="Thanks for supporting the server — all perks are unlocked!",
                color=_GOLD,
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        if config.PREMIUM_SKU_ID is None:
            await interaction.response.send_message(
                "Premium isn't set up on this bot yet.", ephemeral=True
            )
            return
        embed, view = self._upgrade_prompt("You're on the free tier. Tap below to upgrade.")
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @premium.command(name="perks", description="See what Premium unlocks.")
    async def perks(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="✨ Codex Premium perks",
            description="\n".join(_PERKS),
            color=_GOLD,
        )
        embed.set_footer(text="Check your status with /premium status")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @premium.command(name="exclusive", description="A Premium-only demo command.")
    async def exclusive(self, interaction: discord.Interaction) -> None:
        if not self._entitled(interaction):
            embed, view = self._upgrade_prompt(
                "This is a **Premium-only** command. Upgrade to unlock it!"
                if config.PREMIUM_SKU_ID is not None
                else "This is a Premium-only command, but Premium isn't set up yet."
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return
        await interaction.response.send_message(
            "🎉 Here's your exclusive Premium content — thanks for subscribing!", ephemeral=True
        )

    @premium.command(name="skus", description="(Owner) List this app's SKUs and their IDs.")
    async def skus(self, interaction: discord.Interaction) -> None:
        if interaction.user.id not in config.OWNER_IDS:
            await interaction.response.send_message(
                "This is an owner-only command. Set `OWNER_IDS` in `.env` to use it.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True)
        skus = await self.bot.fetch_skus()
        if not skus:
            await interaction.followup.send(
                "No SKUs found. Create one in Developer Portal → Monetization first.",
                ephemeral=True,
            )
            return
        lines = [f"`{sku.id}` — **{sku.name}** ({sku.type.name})" for sku in skus]
        embed = discord.Embed(
            title="Application SKUs",
            description="\n".join(lines)[:4096],
            color=config.COLOR,
        )
        embed.set_footer(text="Put a subscription SKU's ID in PREMIUM_SKU_ID (.env).")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Lifecycle listeners ───────────────────────────────────
    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement: discord.Entitlement) -> None:
        log.info(
            "Entitlement created: sku=%s user=%s guild=%s",
            entitlement.sku_id,
            entitlement.user_id,
            entitlement.guild_id,
        )
        if (
            config.PREMIUM_SKU_ID is None
            or entitlement.sku_id != config.PREMIUM_SKU_ID
            or entitlement.user_id is None
        ):
            return
        user = self.bot.get_user(entitlement.user_id)
        if user is None:
            with contextlib.suppress(discord.HTTPException):
                user = await self.bot.fetch_user(entitlement.user_id)
        if user is not None:
            with contextlib.suppress(discord.HTTPException):
                await user.send("✨ Thanks for going Premium! Your perks are now active. Enjoy!")

    @commands.Cog.listener()
    async def on_entitlement_delete(self, entitlement: discord.Entitlement) -> None:
        log.info(
            "Entitlement ended: sku=%s user=%s guild=%s",
            entitlement.sku_id,
            entitlement.user_id,
            entitlement.guild_id,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Premium(bot))
