from html import unescape
import re
from typing import Final

import requests

from .cache import DailyPageCache

UPL_STANDINGS_URL: Final = "https://upl.ua/ua/tournaments/championship/428/table"
UPL_CALENDAR_URL: Final = "https://upl.ua/ua/tournaments/championship/428/calendar"
DEFAULT_TIMEOUT_SECONDS: Final = 10
DEFAULT_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
QUOTED_TEAM_NAME_PATTERN: Final = re.compile(r"«([^»]+)»")


class UplSiteFetchError(RuntimeError):
    """Raised when a page cannot be retrieved from upl.ua."""


def fetch_upl_page(
    url: str,
    *,
    page_cache: DailyPageCache | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    def _load_page() -> str:
        try:
            response = requests.get(
                url,
                headers={"User-Agent": user_agent},
                timeout=timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise UplSiteFetchError(f"Failed to fetch upl.ua page: {url}") from error

        return response.text

    if page_cache is not None:
        return page_cache.fetch(url, _load_page)

    return _load_page()


def normalize_team_name(raw_team_name: str) -> str:
    normalized = " ".join(unescape(raw_team_name).split())
    quoted_match = QUOTED_TEAM_NAME_PATTERN.search(normalized)
    if quoted_match is not None:
        return quoted_match.group(1)

    return normalized
