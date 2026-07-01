"""Music cog: stream audio into a voice channel via yt-dlp + FFmpeg.

`/music play` resolves a URL or search text with yt-dlp (off the event loop),
then streams the audio through FFmpeg into the caller's voice channel. Each
guild gets its own queue; tracks auto-advance, volume is adjustable live, and
the bot leaves on its own once it's been idle or left alone.

The Now Playing message carries a live seekbar plus a control panel (seek ±15s,
pause/resume, skip, volume). Interactive seeking re-spawns FFmpeg with `-ss`.

Runtime needs: the **FFmpeg** binary on PATH and **PyNaCl + davey** for voice
(installed via discord.py[voice] / the Docker image).
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
SEEKBAR_INTERVAL = 12  # seconds between live progress-bar edits
SEEK_STEP = 15  # seconds the ⏪/⏩ buttons jump
VOLUME_STEP = 0.1  # fraction the 🔉/🔊 buttons change
_BAR_WIDTH = 18  # cells in the rendered seekbar


def _fmt_duration(seconds: int | None) -> str:
    if not seconds:
        return "live"
    return _clock(seconds)


def _clock(seconds: float) -> str:
    """Format seconds as M:SS (or H:MM:SS), always — 0 renders as 0:00."""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _progress_bar(elapsed: float, total: int | None) -> str:
    """A text seekbar: `0:42` ▬▬▬🔘▬▬▬ `3:15` (or a LIVE marker)."""
    if not total:  # live stream / unknown length
        return "🔴 **LIVE**"
    ratio = min(max(elapsed / total, 0.0), 1.0)
    filled = int(ratio * (_BAR_WIDTH - 1))
    bar = "▬" * filled + "🔘" + "▬" * (_BAR_WIDTH - 1 - filled)
    return f"`{_clock(elapsed)}` {bar} `{_clock(total)}`"


class TrackedAudio(discord.PCMVolumeTransformer):
    """Volume-adjustable source that counts frames read to expose elapsed time.

    discord.py pulls one 20 ms frame per `read()`; it stops reading while paused,
    so counting frames tracks true playback position with no wall-clock drift.
    """

    def __init__(self, original: discord.AudioSource, volume: float) -> None:
        super().__init__(original, volume=volume)
        self.frames = 0

    def read(self) -> bytes:
        data = super().read()
        if data:
            self.frames += 1
        return data

    @property
    def elapsed(self) -> float:
        return self.frames * 0.02  # each frame is 20 ms


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
    source: TrackedAudio | None = None
    text_channel: discord.abc.Messageable | None = None
    idle_task: asyncio.Task | None = None
    np_message: discord.Message | None = None  # the live "Now playing" message
    np_view: PlayerControls | None = None  # its control buttons
    np_task: asyncio.Task | None = None  # loop editing the seekbar
    seek_to: float | None = None  # pending seek position (consumed by the after-hook)


class PlayerControls(discord.ui.View):
    """Buttons under the Now Playing message: seek ±15s, pause/resume, skip, volume.

    Only members in the bot's voice channel may use them, and only on the newest
    Now Playing message (older ones have their controls stripped on track change).
    """

    def __init__(self, cog: Music, guild_id: int, *, seekable: bool) -> None:
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        if not seekable:  # live streams have no position to seek within
            self.rewind.disabled = True
            self.forward.disabled = True

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.secondary, row=0)
    async def rewind(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pre = await self.cog.control_precheck(interaction)
        if pre is None:
            return
        state, vc = pre
        elapsed = state.source.elapsed if state.source else 0.0
        await interaction.response.defer()
        self.cog.request_seek(vc.guild, max(0.0, elapsed - SEEK_STEP))

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, row=0)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pre = await self.cog.control_precheck(interaction)
        if pre is None:
            return
        state, vc = pre
        if vc.is_paused():
            vc.resume()
        elif vc.is_playing():
            vc.pause()
        await interaction.response.edit_message(
            embed=self.cog.now_playing_embed(state, paused=vc.is_paused())
        )

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pre = await self.cog.control_precheck(interaction)
        if pre is None:
            return
        _state, vc = pre
        await interaction.response.defer()
        vc.stop()  # after-hook advances the queue

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.secondary, row=0)
    async def forward(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        pre = await self.cog.control_precheck(interaction)
        if pre is None:
            return
        state, vc = pre
        elapsed = state.source.elapsed if state.source else 0.0
        total = state.current.duration if state.current else 0
        target = elapsed + SEEK_STEP
        if total:
            target = min(target, max(0.0, total - 1))
        await interaction.response.defer()
        self.cog.request_seek(vc.guild, target)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, row=1)
    async def volume_down(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._change_volume(interaction, -VOLUME_STEP)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, row=1)
    async def volume_up(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await self._change_volume(interaction, VOLUME_STEP)

    async def _change_volume(self, interaction: discord.Interaction, delta: float) -> None:
        pre = await self.cog.control_precheck(interaction)
        if pre is None:
            return
        state, vc = pre
        state.volume = round(min(1.0, max(0.0, state.volume + delta)), 2)
        if state.source is not None:
            state.source.volume = state.volume
        await interaction.response.edit_message(
            embed=self.cog.now_playing_embed(state, paused=vc.is_paused())
        )


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
            if state.np_task and not state.np_task.done():
                state.np_task.cancel()
            if state.np_view is not None:
                state.np_view.stop()
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
        state = self.states.get(guild.id)
        if state is not None and state.seek_to is not None:
            position = state.seek_to
            state.seek_to = None
            # A seek is pending: replay the SAME track at the new spot, don't advance.
            asyncio.run_coroutine_threadsafe(self._start_at(guild, position), self.bot.loop)
            return
        if error:
            log.error("Playback error in guild %s: %s", guild.id, error)
        asyncio.run_coroutine_threadsafe(self._advance(guild), self.bot.loop)

    async def _advance(self, guild: discord.Guild, *, announce: bool = True) -> None:
        state = self.states.get(guild.id)
        vc = guild.voice_client
        if state is None or not isinstance(vc, discord.VoiceClient):
            return
        await self._teardown_player(state)  # finalize the previous track's player
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
        state.source = TrackedAudio(audio, state.volume)
        vc.play(state.source, after=lambda e: self._play_next(guild, e))
        if announce and state.text_channel is not None:
            with contextlib.suppress(discord.HTTPException):
                view = PlayerControls(self, guild.id, seekable=bool(track.duration))
                message = await state.text_channel.send(
                    embed=self.now_playing_embed(state), view=view
                )
                self._start_player(guild, message, view)

    async def _start_at(self, guild: discord.Guild, position: float) -> None:
        """Restart the current track at `position` seconds (interactive seek)."""
        state = self.states.get(guild.id)
        vc = guild.voice_client
        if state is None or state.current is None or not isinstance(vc, discord.VoiceClient):
            return
        options = {
            "before_options": FFMPEG_OPTIONS["before_options"] + f" -ss {position:.2f}",
            "options": "-vn",
        }
        try:
            audio = discord.FFmpegPCMAudio(state.current.stream_url, **options)
        except Exception:
            log.exception("Failed to seek in %s", state.current.title)
            return
        source = TrackedAudio(audio, state.volume)
        source.frames = int(position / 0.02)  # so the seekbar shows the new position
        state.source = source
        vc.play(source, after=lambda e: self._play_next(guild, e))
        await self._refresh_np(guild, paused=False)

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

    # ── Live seekbar & player message ─────────────────────────
    def _start_player(
        self, guild: discord.Guild, message: discord.Message, view: PlayerControls
    ) -> None:
        state = self.states.get(guild.id)
        if state is None:
            return
        state.np_message = message
        state.np_view = view
        state.np_task = self.bot.loop.create_task(self._seekbar_loop(guild))

    async def _teardown_player(self, state: GuildMusic) -> None:
        """Stop the seekbar loop and strip controls off the old Now Playing message."""
        if state.np_task and not state.np_task.done():
            state.np_task.cancel()
        state.np_task = None
        if state.np_view is not None:
            state.np_view.stop()
        if state.np_message is not None:
            with contextlib.suppress(discord.HTTPException):
                await state.np_message.edit(view=None)
        state.np_message = None
        state.np_view = None

    async def _seekbar_loop(self, guild: discord.Guild) -> None:
        """Refresh the Now Playing message so the bar tracks playback live."""
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(SEEKBAR_INTERVAL)
                state = self.states.get(guild.id)
                vc = guild.voice_client
                if (
                    state is None
                    or state.np_message is None
                    or state.current is None
                    or not isinstance(vc, discord.VoiceClient)
                    or not (vc.is_playing() or vc.is_paused())
                ):
                    return
                try:
                    await state.np_message.edit(
                        embed=self.now_playing_embed(state, paused=vc.is_paused())
                    )
                except discord.NotFound:
                    return  # message was deleted; stop editing
                except discord.HTTPException:
                    pass

    async def _refresh_np(self, guild: discord.Guild, *, paused: bool) -> None:
        """Immediately redraw the Now Playing message (e.g. on pause/resume/seek)."""
        state = self.states.get(guild.id)
        if state is None or state.np_message is None or state.current is None:
            return
        with contextlib.suppress(discord.HTTPException):
            await state.np_message.edit(embed=self.now_playing_embed(state, paused=paused))

    def now_playing_embed(self, state: GuildMusic, *, paused: bool = False) -> discord.Embed:
        track = state.current
        assert track is not None
        elapsed = state.source.elapsed if state.source is not None else 0.0
        embed = discord.Embed(
            title="⏸️ Paused" if paused else "🎵 Now playing",
            description=f"**[{track.title}]({track.url})**",
            color=config.COLOR,
        )
        embed.add_field(name="Progress", value=_progress_bar(elapsed, track.duration), inline=False)
        embed.add_field(name="Requested by", value=f"<@{track.requester_id}>")
        embed.add_field(name="Volume", value=f"{int(state.volume * 100)}%")
        return embed

    # ── Control-panel helpers (called by PlayerControls) ──────
    async def control_precheck(
        self, interaction: discord.Interaction
    ) -> tuple[GuildMusic, discord.VoiceClient] | None:
        """Validate a control-button click; respond + return None if it's not allowed."""
        guild = interaction.guild
        state = self.states.get(guild.id) if guild else None
        vc = guild.voice_client if guild else None
        if state is None or state.current is None or not isinstance(vc, discord.VoiceClient):
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return None
        user = interaction.user
        if (
            not isinstance(user, discord.Member)
            or user.voice is None
            or user.voice.channel != vc.channel
        ):
            await interaction.response.send_message(
                "Join my voice channel to control playback.", ephemeral=True
            )
            return None
        if (
            state.np_message is None
            or interaction.message is None
            or interaction.message.id != state.np_message.id
        ):
            await interaction.response.send_message(
                "This player is out of date — use the newest Now Playing message.", ephemeral=True
            )
            return None
        return state, vc

    def request_seek(self, guild: discord.Guild, position: float) -> None:
        """Ask the after-hook to replay the current track at `position`."""
        state = self.states.get(guild.id)
        vc = guild.voice_client
        if state is None or state.current is None or not isinstance(vc, discord.VoiceClient):
            return
        state.seek_to = position
        vc.stop()  # after-hook sees seek_to and calls _start_at

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
            seekable = bool(state.current.duration) if state.current else False
            view = PlayerControls(self, guild.id, seekable=seekable)
            message = await interaction.followup.send(
                embed=self.now_playing_embed(state), view=view, wait=True
            )
            self._start_player(guild, message, view)
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
        guild = interaction.guild
        assert guild is not None
        vc = guild.voice_client
        if isinstance(vc, discord.VoiceClient) and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸️ Paused.")
            await self._refresh_np(guild, paused=True)
        else:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    @music.command(name="resume", description="Resume playback.")
    async def resume(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        vc = guild.voice_client
        if isinstance(vc, discord.VoiceClient) and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶️ Resumed.")
            await self._refresh_np(guild, paused=False)
        else:
            await interaction.response.send_message("Nothing is paused.", ephemeral=True)

    @music.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        state = self.states.get(guild.id)
        if state is not None:
            state.queue.clear()
            await self._teardown_player(state)
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
        state = self.states.get(guild.id)
        if state is not None:
            await self._teardown_player(state)
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

    @music.command(name="nowplaying", description="Show the current track and seekbar.")
    async def nowplaying(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        assert guild is not None
        state = self.states.get(guild.id)
        if state is None or state.current is None:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return
        vc = guild.voice_client
        paused = isinstance(vc, discord.VoiceClient) and vc.is_paused()
        await interaction.response.send_message(embed=self.now_playing_embed(state, paused=paused))

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
