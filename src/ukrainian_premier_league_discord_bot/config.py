from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import os

_DEFAULT_ENV_PATH = Path(".env")
_DISCORD_BOT_TOKEN = "DISCORD_BOT_TOKEN"
_DISCORD_DAILY_MATCHES_CHANNEL_ID = "DISCORD_DAILY_MATCHES_CHANNEL_ID"
_DISCORD_GUILD_ID = "DISCORD_GUILD_ID"


class ConfigError(ValueError):
    """Raised when required application configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    discord_bot_token: str
    daily_matches_channel_id: int
    discord_guild_id: int | None


def load_config(
    env_path: Path = _DEFAULT_ENV_PATH,
    environ: Mapping[str, str] | None = None,
) -> Config:
    file_values = _read_dotenv(env_path) if env_path.is_file() else {}
    runtime_values = dict(environ) if environ is not None else dict(os.environ)
    values = {**file_values, **runtime_values}

    missing = [
        key
        for key in (_DISCORD_BOT_TOKEN,)
        if not values.get(key, "").strip()
    ]
    if missing:
        missing_keys = ", ".join(missing)
        raise ConfigError(
            f"Missing required configuration values: {missing_keys}. "
            "Set them in .env or provide them as environment variables."
        )

    return Config(
        discord_bot_token=values[_DISCORD_BOT_TOKEN],
        daily_matches_channel_id=_parse_int_value(
            key=_DISCORD_DAILY_MATCHES_CHANNEL_ID,
            values=values,
        ),
        discord_guild_id=_parse_optional_int_value(
            key=_DISCORD_GUILD_ID,
            values=values,
        ),
    )


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line.removeprefix("export ").strip()

        if "=" not in line:
            raise ConfigError(f"Invalid .env entry on line {line_number}: {raw_line!r}")

        key, value = line.split("=", maxsplit=1)
        normalized_key = key.strip()
        if not normalized_key:
            raise ConfigError(f"Empty environment variable name on line {line_number}.")

        values[normalized_key] = _strip_optional_quotes(value.strip())

    return values


def _strip_optional_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_int_value(*, key: str, values: Mapping[str, str]) -> int:
    raw_value = values.get(key, "").strip()
    if not raw_value:
        raise ConfigError(
            f"Missing required configuration value: {key}. "
            "Set it in .env or provide it as an environment variable."
        )

    try:
        return int(raw_value)
    except ValueError as error:
        raise ConfigError(
            f"Configuration value {key} must be an integer, got {raw_value!r}."
        ) from error


def _parse_optional_int_value(*, key: str, values: Mapping[str, str]) -> int | None:
    raw_value = values.get(key, "").strip()
    if not raw_value:
        return None

    try:
        return int(raw_value)
    except ValueError as error:
        raise ConfigError(
            f"Configuration value {key} must be an integer, got {raw_value!r}."
        ) from error
