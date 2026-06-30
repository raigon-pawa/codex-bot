"""Role tools: button self-assign roles + automatic level-up roles.

- /selfrole add|remove|panel — admins choose which roles members can self-assign,
  then post a button panel. Buttons are persistent (a `DynamicItem` keyed on the
  role id), so they keep working after a restart with no per-message bookkeeping.
- /levelrole set|remove|list — map an XP level to a role; the cog listens for the
  `level_up` event dispatched by the `social` cog and grants milestone roles.
"""

from __future__ import annotations

import contextlib

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands

import config
from core.database import init_db

_ADMIN = discord.Permissions(manage_roles=True)


class SelfRoleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"codex:selfrole:(?P<role_id>\d+)",
):
    """A button that toggles one role. Reconstructed from its custom_id after a
    restart, so panels survive without storing each view."""

    def __init__(
        self, role_id: int, *, label: str = "Role", emoji: discord.PartialEmoji | None = None
    ) -> None:
        self.role_id = role_id
        super().__init__(
            discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                custom_id=f"codex:selfrole:{role_id}",
            )
        )

    @classmethod
    async def from_custom_id(cls, interaction, item, match, /):
        return cls(int(match["role_id"]))

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return
        role = guild.get_role(self.role_id)
        if role is None:
            await interaction.response.send_message("That role no longer exists.", ephemeral=True)
            return
        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Self-role panel")
                await interaction.response.send_message(f"Removed {role.mention}.", ephemeral=True)
            else:
                await member.add_roles(role, reason="Self-role panel")
                await interaction.response.send_message(f"Added {role.mention}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                "I can't manage that role — it's probably above my highest role.", ephemeral=True
            )


class Roles(commands.Cog):
    selfrole = app_commands.Group(
        name="selfrole",
        description="Self-assignable roles.",
        default_permissions=_ADMIN,
        guild_only=True,
    )
    levelrole = app_commands.Group(
        name="levelrole",
        description="Roles granted at XP levels.",
        default_permissions=_ADMIN,
        guild_only=True,
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        await init_db()

    # ── Self-assign roles ─────────────────────────────────────
    @selfrole.command(name="add", description="Let members self-assign a role.")
    @app_commands.describe(role="The role", emoji="Optional button emoji")
    async def selfrole_add(
        self, interaction: discord.Interaction, role: discord.Role, emoji: str | None = None
    ) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "INSERT INTO self_roles (guild_id, role_id, emoji) VALUES (?,?,?) "
                "ON CONFLICT(guild_id, role_id) DO UPDATE SET emoji=excluded.emoji",
                (interaction.guild_id, role.id, emoji),
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ {role.mention} is now self-assignable. Run `/selfrole panel` to post the menu.",
            ephemeral=True,
        )

    @selfrole.command(name="remove", description="Stop a role being self-assignable.")
    @app_commands.describe(role="The role")
    async def selfrole_remove(self, interaction: discord.Interaction, role: discord.Role) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM self_roles WHERE guild_id=? AND role_id=?",
                (interaction.guild_id, role.id),
            )
            await db.commit()
        await interaction.response.send_message(
            f"Removed {role.mention} from the menu."
            if cursor.rowcount
            else "That role wasn't in the menu.",
            ephemeral=True,
        )

    @selfrole.command(name="panel", description="Post the self-assign role panel.")
    async def selfrole_panel(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT role_id, emoji FROM self_roles WHERE guild_id=?", (guild.id,)
            )
            rows = await cursor.fetchall()
        view = discord.ui.View(timeout=None)
        added = 0
        for role_id, emoji in rows:
            role = guild.get_role(role_id)
            if role is None or added >= 25:  # Discord caps a message at 25 components
                continue
            emoji_obj = discord.PartialEmoji.from_str(emoji) if emoji else None
            view.add_item(SelfRoleButton(role_id, label=role.name, emoji=emoji_obj))
            added += 1
        if added == 0:
            await interaction.response.send_message(
                "No self-assignable roles yet — add some with `/selfrole add`.", ephemeral=True
            )
            return
        embed = discord.Embed(
            title="🎭 Self-assign roles",
            description="Click a button to add or remove a role.",
            color=config.COLOR,
        )
        await interaction.response.send_message(embed=embed, view=view)

    # ── Level roles ───────────────────────────────────────────
    @levelrole.command(name="set", description="Grant a role when members reach a level.")
    @app_commands.describe(level="The level (1+)", role="The role to grant")
    async def levelrole_set(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 1, 1000],
        role: discord.Role,
    ) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            await db.execute(
                "INSERT INTO level_roles (guild_id, level, role_id) VALUES (?,?,?) "
                "ON CONFLICT(guild_id, level) DO UPDATE SET role_id=excluded.role_id",
                (interaction.guild_id, level, role.id),
            )
            await db.commit()
        await interaction.response.send_message(
            f"✅ {role.mention} will be granted at **level {level}**.", ephemeral=True
        )

    @levelrole.command(name="remove", description="Remove a level→role mapping.")
    @app_commands.describe(level="The level to clear")
    async def levelrole_remove(self, interaction: discord.Interaction, level: int) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "DELETE FROM level_roles WHERE guild_id=? AND level=?",
                (interaction.guild_id, level),
            )
            await db.commit()
        await interaction.response.send_message(
            "Mapping removed." if cursor.rowcount else "Nothing set for that level.", ephemeral=True
        )

    @levelrole.command(name="list", description="Show configured level roles.")
    async def levelrole_list(self, interaction: discord.Interaction) -> None:
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT level, role_id FROM level_roles WHERE guild_id=? ORDER BY level",
                (interaction.guild_id,),
            )
            rows = await cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No level roles configured.", ephemeral=True)
            return
        lines = [f"**Level {level}** → <@&{role_id}>" for level, role_id in rows]
        embed = discord.Embed(
            title="🏅 Level roles", description="\n".join(lines)[:4096], color=config.COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.Cog.listener()
    async def on_level_up(self, member: discord.Member, level: int) -> None:
        """Grant every milestone role up to the member's new level (cumulative)."""
        async with aiosqlite.connect(config.DB_PATH) as db:
            cursor = await db.execute(
                "SELECT role_id FROM level_roles WHERE guild_id=? AND level<=?",
                (member.guild.id, level),
            )
            role_ids = [r[0] for r in await cursor.fetchall()]
        roles = [member.guild.get_role(rid) for rid in role_ids]
        to_add = [r for r in roles if r is not None and r not in member.roles]
        if to_add:
            with contextlib.suppress(discord.Forbidden):
                await member.add_roles(*to_add, reason=f"Reached level {level}")

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        msg = (
            "You need the **Manage Roles** permission for that."
            if isinstance(error, app_commands.MissingPermissions)
            else f"Something went wrong: {error}"
        )
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    bot.add_dynamic_items(SelfRoleButton)  # route persistent button clicks after restart
    await bot.add_cog(Roles(bot))
