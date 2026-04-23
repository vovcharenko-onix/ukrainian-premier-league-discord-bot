import asyncio
import logging
from datetime import time
from typing import Final

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .attackers import (
    UplAttackersClient,
    UplAttackersError,
    format_discord_attackers_table,
)
from .cache import DailyPageCache
from .config import Config, load_config
from .fixtures import (
    KYIV_TIMEZONE,
    UplFixturesClient,
    UplFixturesError,
    format_discord_daily_matches,
    format_discord_tour_schedule,
)
from .standings import (
    UplStandingsClient,
    UplStandingsError,
    format_discord_standings_table,
)

LOGGER: Final = logging.getLogger(__name__)
DAILY_POST_TIME: Final = time(hour=14, minute=0, tzinfo=KYIV_TIMEZONE)


class DailyMatchesChannelError(RuntimeError):
    """Raised when the configured daily matches channel cannot be used."""


class UplBotCog(commands.Cog):
    def __init__(self, bot: commands.Bot, config: Config) -> None:
        self.bot = bot
        self.config = config
        page_cache = DailyPageCache()
        self.attackers_client = UplAttackersClient(page_cache=page_cache)
        self.standings_client = UplStandingsClient()
        self.fixtures_client = UplFixturesClient(page_cache=page_cache)

    async def cog_load(self) -> None:
        self.daily_matches_post.start()

    async def cog_unload(self) -> None:
        self.daily_matches_post.cancel()

    @app_commands.command(
        name="table",
        description="Показати повну турнірну таблицю УПЛ.",
    )
    async def table(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        try:
            standings = await asyncio.to_thread(self.standings_client.fetch_standings)
        except UplStandingsError as error:
            await interaction.followup.send(
                f"Не вдалося отримати турнірну таблицю УПЛ: {error}"
            )
            return

        await interaction.followup.send(format_discord_standings_table(standings))

    @app_commands.command(
        name="attackers",
        description="Показати таблицю бомбардирів УПЛ.",
    )
    async def attackers(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        try:
            attackers = await asyncio.to_thread(self.attackers_client.fetch_attackers)
        except UplAttackersError as error:
            await interaction.followup.send(
                f"Не вдалося отримати таблицю бомбардирів УПЛ: {error}"
            )
            return

        await interaction.followup.send(format_discord_attackers_table(attackers))

    @app_commands.command(
        name="today",
        description="Показати сьогоднішні матчі УПЛ.",
    )
    async def today(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        try:
            fixtures = await asyncio.to_thread(self.fixtures_client.fetch_matches_for_date)
        except UplFixturesError as error:
            await interaction.followup.send(
                f"Не вдалося отримати сьогоднішні матчі УПЛ: {error}"
            )
            return

        message = format_discord_daily_matches(fixtures)
        if message is None:
            await interaction.followup.send("Сьогодні матчів УПЛ немає.")
            return

        await interaction.followup.send(message)

    @app_commands.command(
        name="current",
        description="Показати поточний тур УПЛ для ігрового тижня вівторок-понеділок.",
    )
    async def current(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        try:
            tour = await asyncio.to_thread(self.fixtures_client.fetch_current_tour)
        except UplFixturesError as error:
            await interaction.followup.send(
                f"Не вдалося отримати поточний тур УПЛ: {error}"
            )
            return

        if tour is None:
            await interaction.followup.send("У поточному ігровому тижні тур УПЛ не знайдено.")
            return

        await interaction.followup.send(
            format_discord_tour_schedule(tour, title_prefix="Поточний тур УПЛ")
        )

    @app_commands.command(
        name="next",
        description="Показати наступний тур УПЛ.",
    )
    async def next(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)

        try:
            tour = await asyncio.to_thread(self.fixtures_client.fetch_next_tour)
        except UplFixturesError as error:
            await interaction.followup.send(
                f"Не вдалося отримати наступний тур УПЛ: {error}"
            )
            return

        if tour is None:
            await interaction.followup.send("Наступний тур УПЛ не знайдено.")
            return

        await interaction.followup.send(
            format_discord_tour_schedule(tour, title_prefix="Наступний тур УПЛ")
        )

    @tasks.loop(time=DAILY_POST_TIME)
    async def daily_matches_post(self) -> None:
        try:
            fixtures = await asyncio.to_thread(self.fixtures_client.fetch_matches_for_date)
        except UplFixturesError:
            LOGGER.exception("Failed to fetch today's UPL fixtures for scheduled posting.")
            return

        message = format_discord_daily_matches(fixtures, include_empty_message=False)
        if message is None:
            LOGGER.info("No UPL matches scheduled for today; skipping daily post.")
            return

        try:
            channel = await self._resolve_daily_channel()
        except DailyMatchesChannelError:
            LOGGER.exception(
                "Failed to resolve the configured daily matches channel %s.",
                self.config.daily_matches_channel_id,
            )
            return

        try:
            await channel.send(message)
        except discord.Forbidden:
            LOGGER.exception(
                "Missing permission to send the scheduled daily matches post to channel %s.",
                self.config.daily_matches_channel_id,
            )
        except discord.HTTPException:
            LOGGER.exception(
                "Discord rejected the scheduled daily matches post for channel %s.",
                self.config.daily_matches_channel_id,
            )

    @daily_matches_post.before_loop
    async def before_daily_matches_post(self) -> None:
        await self.bot.wait_until_ready()

    async def _resolve_daily_channel(self) -> discord.TextChannel | discord.Thread:
        channel = self.bot.get_channel(self.config.daily_matches_channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(
                    self.config.daily_matches_channel_id
                )
            except discord.NotFound as error:
                raise DailyMatchesChannelError(
                    "Configured daily matches channel was not found. "
                    "Update DISCORD_DAILY_MATCHES_CHANNEL_ID or restore the channel."
                ) from error
            except discord.Forbidden as error:
                raise DailyMatchesChannelError(
                    "Bot does not have access to the configured daily matches channel."
                ) from error
            except discord.HTTPException as error:
                raise DailyMatchesChannelError(
                    "Discord API request failed while resolving the configured daily "
                    "matches channel."
                ) from error

        if isinstance(channel, (discord.TextChannel, discord.Thread)):
            return channel

        raise DailyMatchesChannelError(
            "Configured daily matches channel is not a text channel or thread."
        )


class UplDiscordBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self._config = config

    async def setup_hook(self) -> None:
        await self.add_cog(UplBotCog(self, self._config))
        if self._config.discord_guild_id is not None:
            guild = discord.Object(id=self._config.discord_guild_id)
            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            LOGGER.info(
                "Synced slash commands only to guild %s and cleared global commands.",
                self._config.discord_guild_id,
            )
            return

        await self.tree.sync()
        LOGGER.info("Synced slash commands globally. Discord may take time to show updates.")


def run_bot() -> None:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    bot = UplDiscordBot(config)
    bot.run(config.discord_bot_token)
