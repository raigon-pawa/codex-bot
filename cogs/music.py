"""Music cog: stream audio into a voice channel via yt-dlp + FFmpeg.

`/music play` resolves a URL or search text with yt-dlp (off the event loop),
then streams the audio through FFmpeg into the caller's voice channel. Each
guild gets its own queue; tracks auto-advance, volume is adjustable live, and
the bot leaves on its own once it's been idle or left alone.

Runtime needs: the **FFmpeg** binary on PATH and **PyNaCl** for voice
encryption (both provided by the Docker image / requirements.txt).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import dataclass, field

import discord
import yt_dlp
from discord import app_commands
from discord.ext import commands

import config

log = logging.getLogger("codex")

# Resolve the best audio-only stream; ytsearch turns bare text into a search.
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "default_search": "ytsearch",
    "quiet": True,
    "no_warnings": True,
    "source_address": "0.0.0.0",  # bind to IPv4 to dodge some 403s
}

# -reconnect keeps long streams alive; -vn drops any video track.
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

IDLE_TIMEOUT = 180  # seconds to linger while idle or alone before disconnecting


def _fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return "live"
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


@dataclass
class Track:
    title: str
    url: str
    stream_url: str
    duration: int | None
    requester_id: int


@dataclass
class GuildMusic:
    queue: deque[Track] = field(default_factory=deque)
    current: Track | None = None
    volume: float = 0.5
    source: discord.PCMVolumeTransformer | None = None
    text_channel: discord.abc.Messageable | None = None
    idle_task: asyncio.Task | None = None


class Music(commands.Cog):
    music = app_commands.Group(
        name="music", description="Play audio in a voice channel.", guild_only=True
    )

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.states: dict[int, GuildMusic] = {}

    async def cog_unload(self) -> None:
        for state in self.states.values():
            if state.idle_task and not state.idle_task.done():
                state.idle_task.cancel()
        for vc in list(self.bot.voice_clients):
            with contextlib.suppress(Exception):
                await vc.disconnect(force=True)

    def _state(self, guild_id: int) -> GuildMusic:
        return self.states.setdefault(guild_id, GuildMusic())

    # ── Resolution & playback ─────────────────────────────────
    async def _resolve(self, query: str, requester_id: int) -> Track:
        """Run yt-dlp in a thread so the event loop keeps serving Discord."""
        loop = asyncio.get_running_loop()

        def extract() -> dict:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(query, download=False)
            if info and "entries" in info:  # search / playlist → first hit
                info = info["entries"][0]
            return info

        info = await loop.run_in_executor(None, extract)
        return Track(
            title=info.get("title", "Unknown"),
            url=info.get("webpage_url", query),
            stream_url=info["url"],
            duration=info.get("duration"),
            requester_id=requester_id,
        )

    def _play_next(self, guild: discord.Guild, error: Exception | None = None) -> None:
        """FFmpeg's `after` hook — runs in a worker thread, so hop back to the loop."""
        if error:
            log.error("Playback error in guild %s: %s", guild.id, error)
        asyncio.run_coroutine_threadsafe(self._advance(guild), self.bot.loop)

    async def _advance(self, guild: discord.Guild, *, announce: bool = True) -> None:
        state = self.states.get(guild.id)
        vc = guild.voice_client
        if state is None or not isinstance(vc, discord.VoiceClient):
            return
        if not state.queue:
            state.current = None
            state.source = None
            self._schedule_idle_leave(guild)
            return
        if state.idle_task and not state.idle_task.done():
            state.idle_task.cancel()
        track = state.queue.popleft()
        state.current = track
        try:
            audio = discord.FFmpegPCMAudio(track.stream_url, **FFMPEG_OPTIONS)
        except Exception:
            log.exception("Failed to start FFmpeg for %s", track.title)
            self._play_next(guild)  # skip the bad track, try the next
            return
        state.source = discord.PCMVolumeTransformer(audio, volume=state.volume)
        vc.play(state.source, after=lambda e: self._play_next(guild, e))
        if announce and state.text_channel is not None:
            with contextlib.suppress(discord.HTTPException):
                await state.text_channel.send(embed=self._now_playing_embed(state))

    def _schedule_idle_leave(self, guild: discord.Guild) -> None:
        state = self.states.get(guild.id)
        if state is None:
            return
        if state.idle_task and not state.idle_task.done():
            state.idle_task.cancel()
        state.idle_task = self.bot.loop.create_task(self._idle_leave(guild))

    async def _idle_leave(self, guild: discord.Guild) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(IDLE_TIMEOUT)
            vc = guild.voice_client
            if not isinstance(vc, discord.VoiceClient):
                return
            has_listeners = any(not m.bot for m in vc.channel.members)
            if has_listeners and vc.is_playing():
                return  # someone's still here and listening
            await vc.disconnect()
            self.states.pop(guild.id, None)

    def _now_playing_embed(self, state: GuildMusic) -> discord.Embed:
        track = state.current
        assert track is not None
        embed = discord.Embed(
            title="🎵 Now playing",
            description=f"**[{track.title}]({track.url})**",
            color=config.COLOR,
        )
        embed.add_field(name="Duration", value=_fmt_duration(track.duration))
        embed.add_field(name="Requested by", value=f"<@{track.requester_id}>")
        embed.add_field(name="Volume", value=f"{int(state.volume * 100)}%")
        return embed

    # ── Commands ──────────────────────────────────────────────
    @music.command(name="play", description="Play a track from a URL or search text.")
    @app_commands.describe(query="A YouTube/SoundCloud URL or search terms")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        user = interaction.user
        if not isinstance(user, discord.Member) or user.voice is None or user.voice.channel is None:
            await interaction.response.send_message("Join a voice channel first.", ephemeral=True)
            return
        channel = user.voice.channel
        guild = interaction.guild
        assert guild is not None
        await interaction.response.defer()

        vc = guild.voice_client
        if not isinstance(vc, discord.VoiceClient):
            perms = channel.permissions_for(guild.me)
            if not (perms.connect and perms.speak):
                await interaction.followup.send(
                    "I need permission to connect and speak in that channel.", ephemeral=True
                )
                return
            try:
                vc = await channel.connect()
            except (discord.ClientException, TimeoutError):
                await interaction.followup.send(
                    "I couldn't join your voice channel.", ephemeral=True
                )
                return
        elif vc.channel != channel:
            await interaction.followup.send(
                "I'm already playing in another voice channel.", ephemeral=True
            )
            return

        try:
            track = await self._resolve(query, user.id)
        except Exception as exc:
            log.warning("Resolve failed for %r: %s", query, exc)
            await interaction.followup.send(
                "Couldn't find or load that track — try a different link or search.",
                ephemeral=True,
            )
            return

        state = self._state(guild.id)
        state.text_channel = interaction.channel
        if state.idle_task and not state.idle_task.done():
            state.idle_task.cancel()
        state.queue.append(track)
        if not vc.is_playing() and state.current is None:
            await self._advance(guild, announce=False)
            await interaction.followup.send(embed=self._now_playing_embed(state))
        else:
            await interaction.followup.send(
                f"✅ Queued **{track.title}** — position {len(state.queue)}."
            )

    @music.command(name="skip", description="Skip the current track.")
    async def skip(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client  # type: ignore[union-attr]
        if not isinstance(vc, discord.VoiceClient) or not (vc.is_playing() or vc.is_paused()):
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        vc.stop()  # fires the `after` hook, which advances the queue
        await interaction.response.send_message("⏭️ Skipped.")

    @music.command(name="pause", description="Pause playback.")
    async def pause(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client  # type: ignore[union-attr]
        if isinstance(vc, discord.VoiceClient) and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused.")
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @music.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        vc = interaction.guild.voice_client  # type: ignore[union-attr]
        if isinstance(vc, discord.VoiceClient) and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed.")
        else:
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)

    @music.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        state = self.states.get(guild.id)
        if state is not None:
            state.queue.clear()
        vc = guild.voice_client
        if isinstance(vc, discord.VoiceClient) and (vc.is_playing() or vc.is_paused()):
            vc.stop()
        await interaction.response.send_message("⏹️ Stopped and cleared the queue.")

    @music.command(name="leave", description="Disconnect from the voice channel.")
    async def leave(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        vc = guild.voice_client
        if not isinstance(vc, discord.VoiceClient):
            await interaction.response.send_message("I'm not in a voice channel.", ephemeral=True)
            return
        await vc.disconnect()
        self.states.pop(guild.id, None)
        await interaction.response.send_message("👋 Left the voice channel.")

    @music.command(name="queue", description="Show the upcoming tracks.")
    async def queue(self, interaction: discord.Interaction) -> None:
        state = self.states.get(interaction.guild_id)  # type: ignore[arg-type]
        if state is None or (state.current is None and not state.queue):
            await interaction.response.send_message("The queue is empty.", ephemeral=True)
            return
        lines = []
        if state.current is not None:
            lines.append(f"**Now:** {state.current.title}")
        for i, track in enumerate(list(state.queue)[:10], 1):
            lines.append(f"{i}. {track.title} ({_fmt_duration(track.duration)})")
        remaining = len(state.queue) - 10
        if remaining > 0:
            lines.append(f"…and {remaining} more")
        embed = discord.Embed(
            title="🎶 Queue", description="\n".join(lines)[:4096], color=config.COLOR
        )
        await interaction.response.send_message(embed=embed)

    @music.command(name="nowplaying", description="Show the current track.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        state = self.states.get(interaction.guild_id)  # type: ignore[arg-type]
        if state is None or state.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self._now_playing_embed(state))

    @music.command(name="volume", description="Set the playback volume (0-100).")
    @app_commands.describe(level="Volume percentage from 0 to 100")
    async def volume(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]
    ) -> None:
        state = self._state(interaction.guild_id)  # type: ignore[arg-type]
        state.volume = level / 100
        if state.source is not None:
            state.source.volume = state.volume
        await interaction.response.send_message(f"🔊 Volume set to {level}%.")

    # ── Auto-leave when left alone ────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        vc = member.guild.voice_client
        if not isinstance(vc, discord.VoiceClient):
            return
        if not any(not m.bot for m in vc.channel.members):
            self._schedule_idle_leave(member.guild)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Music(bot))
