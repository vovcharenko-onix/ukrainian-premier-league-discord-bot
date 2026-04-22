from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup
from bs4.element import Tag

from .upl import (
    UPL_STANDINGS_URL,
    UplSiteFetchError,
    fetch_upl_page,
    normalize_team_name,
)
EXPECTED_TABLE_HEADERS: Final = (
    "Місце",
    "Команда",
    "І",
    "В",
    "Н",
    "П",
    "ЗМ",
    "ПМ",
    "РМ",
    "О",
)


class UplStandingsError(RuntimeError):
    """Base error for UPL standings retrieval and parsing."""


class UplStandingsFetchError(UplStandingsError):
    """Raised when the standings page cannot be retrieved."""


class UplStandingsParseError(UplStandingsError):
    """Raised when the standings page cannot be parsed."""


@dataclass(frozen=True, slots=True)
class StandingRow:
    position: int
    team_name: str
    matches_played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int

    @property
    def display_goal_difference(self) -> str:
        if self.goal_difference > 0:
            return f"+{self.goal_difference}"
        return str(self.goal_difference)


@dataclass(frozen=True, slots=True)
class StandingsTable:
    title: str
    source_url: str
    rows: tuple[StandingRow, ...]


class UplStandingsClient:
    def __init__(self, *, source_url: str = UPL_STANDINGS_URL) -> None:
        self._source_url = source_url

    def fetch_standings(self) -> StandingsTable:
        try:
            html = fetch_upl_page(self._source_url)
        except UplSiteFetchError as error:
            raise UplStandingsFetchError(
                f"Failed to fetch UPL standings page: {self._source_url}"
            ) from error

        return parse_standings_page(html, source_url=self._source_url)


def parse_standings_page(
    html: str,
    *,
    source_url: str = UPL_STANDINGS_URL,
    title: str = "Турнірна таблиця УПЛ",
) -> StandingsTable:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_standings_table(soup)
    body = table.find("tbody")
    if body is None:
        raise UplStandingsParseError("Standings table body was not found.")

    rows = tuple(_parse_row(row) for row in body.find_all("tr", recursive=False))
    if not rows:
        raise UplStandingsParseError("Standings table does not contain any rows.")

    return StandingsTable(title=title, source_url=source_url, rows=rows)


def format_discord_standings_table(
    standings: StandingsTable,
    *,
    max_team_name_width: int = 22,
) -> str:
    headers = ("#", "Команда", "І", "В", "Н", "П", "ЗМ", "ПМ", "РМ", "О")
    rendered_rows = [
        (
            str(row.position),
            _truncate(row.team_name, max_team_name_width),
            str(row.matches_played),
            str(row.wins),
            str(row.draws),
            str(row.losses),
            str(row.goals_for),
            str(row.goals_against),
            row.display_goal_difference,
            str(row.points),
        )
        for row in standings.rows
    ]

    widths = [
        max(len(header), *(len(row[index]) for row in rendered_rows))
        for index, header in enumerate(headers)
    ]

    lines = [
        _format_line(headers, widths),
        _format_line(tuple("-" * width for width in widths), widths),
    ]
    lines.extend(_format_line(row, widths) for row in rendered_rows)

    return f"🏆 **{standings.title}**\n```text\n" + "\n".join(lines) + "\n```"


def _find_standings_table(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table"):
        headers = tuple(
            header.get_text(" ", strip=True) for header in table.select("thead th")
        )
        if headers == EXPECTED_TABLE_HEADERS:
            return table

    raise UplStandingsParseError("UPL standings table was not found in the page.")


def _parse_row(row: Tag) -> StandingRow:
    cells = row.find_all("td", recursive=False)
    if len(cells) != len(EXPECTED_TABLE_HEADERS):
        raise UplStandingsParseError(
            f"Unexpected standings row shape: expected {len(EXPECTED_TABLE_HEADERS)} "
            f"cells, got {len(cells)}."
        )

    team_link = cells[1].find("a")
    if team_link is None:
        raise UplStandingsParseError("Team link was not found in standings row.")

    team_name = normalize_team_name(team_link.get_text(" ", strip=True))
    return StandingRow(
        position=_parse_int(cells[0].get_text(strip=True)),
        team_name=team_name,
        matches_played=_parse_int(cells[2].get_text(strip=True)),
        wins=_parse_int(cells[3].get_text(strip=True)),
        draws=_parse_int(cells[4].get_text(strip=True)),
        losses=_parse_int(cells[5].get_text(strip=True)),
        goals_for=_parse_int(cells[6].get_text(strip=True)),
        goals_against=_parse_int(cells[7].get_text(strip=True)),
        goal_difference=_parse_int(cells[8].get_text(strip=True)),
        points=_parse_int(cells[9].get_text(strip=True)),
    )
def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise UplStandingsParseError(f"Expected integer value, got {value!r}.") from error


def _truncate(value: str, max_width: int) -> str:
    if len(value) <= max_width:
        return value
    return value[: max_width - 3] + "..."


def _format_line(values: tuple[str, ...], widths: list[int]) -> str:
    first_column = values[0].rjust(widths[0])
    team_column = values[1].ljust(widths[1])
    numeric_columns = [
        value.rjust(width)
        for value, width in zip(values[2:], widths[2:], strict=True)
    ]
    return " ".join((first_column, team_column, *numeric_columns))
