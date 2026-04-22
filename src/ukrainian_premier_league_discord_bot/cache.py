from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Final
from uuid import uuid4
from zoneinfo import ZoneInfo

CACHE_DATE_FORMAT: Final = "%Y-%m-%d"
KYIV_TIMEZONE: Final = ZoneInfo("Europe/Kyiv")
DEFAULT_CACHE_DIR: Final = (
    Path.home() / ".cache" / "ukrainian-premier-league-discord-bot" / "upl-pages"
)


class UplPageCacheError(RuntimeError):
    """Raised when the page cache cannot be read from or written to disk."""


@dataclass(frozen=True, slots=True)
class CachedPage:
    url: str
    cached_on: str
    body: str


class DailyPageCache:
    def __init__(
        self,
        *,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._cache_dir = cache_dir
        self._now_provider = now_provider or self._default_now

    def fetch(self, url: str, loader: Callable[[], str]) -> str:
        cached_body = self.get(url)
        if cached_body is not None:
            return cached_body

        body = loader()
        self.set(url, body)
        return body

    def get(self, url: str) -> str | None:
        path = self._cache_path(url)
        if not path.is_file():
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as error:
            raise UplPageCacheError(f"Failed to read cache file: {path}") from error
        except json.JSONDecodeError:
            return None

        cached_page = _parse_cached_page(payload)
        if cached_page is None:
            return None

        if cached_page.url != url or cached_page.cached_on != self._current_cache_token():
            return None

        return cached_page.body

    def set(self, url: str, body: str) -> None:
        path = self._cache_path(url)
        temp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        payload = CachedPage(
            url=url,
            cached_on=self._current_cache_token(),
            body=body,
        )

        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(
                json.dumps(
                    {
                        "url": payload.url,
                        "cached_on": payload.cached_on,
                        "body": payload.body,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            temp_path.replace(path)
        except OSError as error:
            raise UplPageCacheError(f"Failed to write cache file: {path}") from error

    def _current_cache_token(self) -> str:
        return self._now_provider().strftime(CACHE_DATE_FORMAT)

    def _cache_path(self, url: str) -> Path:
        cache_key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self._cache_dir / f"{cache_key}.json"

    @staticmethod
    def _default_now() -> datetime:
        return datetime.now(KYIV_TIMEZONE)


def _parse_cached_page(payload: object) -> CachedPage | None:
    match payload:
        case {"url": str(url), "cached_on": str(cached_on), "body": str(body)}:
            return CachedPage(url=url, cached_on=cached_on, body=body)
        case _:
            return None
