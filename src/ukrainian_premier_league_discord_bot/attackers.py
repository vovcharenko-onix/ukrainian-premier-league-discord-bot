from dataclasses import dataclass
from typing import Final

from bs4 import BeautifulSoup
from bs4.element import Tag

from .upl import UplSiteFetchError, fetch_upl_page

UPL_ATTACKERS_URL: Final = "https://upl.ua/ua/tournaments/championship/428/attackers"
EXPECTED_TABLE_HEADERS: Final = (
    "Футболіст",
    "М'ячів",
    "М'ячів (з пен.)",
    "Ігор",
    "Хвилин",
    "Команда",
)


class UplAttackersError(RuntimeError):
    """Base error for UPL attackers retrieval and parsing."""


class UplAttackersFetchError(UplAttackersError):
    """Raised when the attackers page cannot be retrieved."""


class UplAttackersParseError(UplAttackersError):
    """Raised when the attackers page cannot be parsed."""


@dataclass(frozen=True, slots=True)
class AttackerRow:
    position: int
    player_name: str
    goals: int
    penalty_goals: int
    matches_played: int
    minutes_played: int
    team_name: str


@dataclass(frozen=True, slots=True)
class AttackersTable:
    title: str
    source_url: str
    rows: tuple[AttackerRow, ...]


class UplAttackersClient:
    def __init__(self, *, source_url: str = UPL_ATTACKERS_URL) -> None:
        self._source_url = source_url

    def fetch_attackers(self) -> AttackersTable:
        try:
            html = fetch_upl_page(self._source_url)
        except UplSiteFetchError as error:
            raise UplAttackersFetchError(
                f"Failed to fetch UPL attackers page: {self._source_url}"
            ) from error

        return parse_attackers_page(html, source_url=self._source_url)


def parse_attackers_page(
    html: str,
    *,
    source_url: str = UPL_ATTACKERS_URL,
    title: str = "Бомбардири УПЛ",
) -> AttackersTable:
    soup = BeautifulSoup(html, "html.parser")
    table = _find_attackers_table(soup)
    body = table.find("tbody")
    if body is None:
        raise UplAttackersParseError("Attackers table body was not found.")

    rows = tuple(
        _parse_row(index, row)
        for index, row in enumerate(body.find_all("tr", recursive=False), start=1)
    )
    if not rows:
        raise UplAttackersParseError("Attackers table does not contain any rows.")

    return AttackersTable(title=title, source_url=source_url, rows=rows)


def format_discord_attackers_table(
    attackers: AttackersTable,
    *,
    max_player_name_width: int = 20,
    max_team_name_width: int = 14,
    limit: int = 10,
) -> str:
    headers = ("#", "Футболіст", "Г", "П", "І", "Хв", "Команда")
    rendered_rows = [
        (
            str(row.position),
            _truncate(row.player_name, max_player_name_width),
            str(row.goals),
            str(row.penalty_goals),
            str(row.matches_played),
            str(row.minutes_played),
            _truncate(row.team_name, max_team_name_width),
        )
        for row in attackers.rows[:limit]
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

    return f"⚽ **{attackers.title} (топ {limit})**\n```text\n" + "\n".join(lines) + "\n```"


def _find_attackers_table(soup: BeautifulSoup) -> Tag:
    for table in soup.find_all("table"):
        headers = tuple(
            header.get_text(" ", strip=True) for header in table.select("thead th")
        )
        if headers == EXPECTED_TABLE_HEADERS:
            return table

    raise UplAttackersParseError("UPL attackers table was not found in the page.")


def _parse_row(position: int, row: Tag) -> AttackerRow:
    cells = row.find_all("td", recursive=False)
    if len(cells) != len(EXPECTED_TABLE_HEADERS):
        raise UplAttackersParseError(
            f"Unexpected attackers row shape: expected {len(EXPECTED_TABLE_HEADERS)} "
            f"cells, got {len(cells)}."
        )

    player_link = cells[0].find("a")
    if player_link is None:
        raise UplAttackersParseError("Player link was not found in attackers row.")

    return AttackerRow(
        position=position,
        player_name=" ".join(player_link.get_text(" ", strip=True).split()),
        goals=_parse_int(cells[1].get_text(strip=True)),
        penalty_goals=_parse_int(cells[2].get_text(strip=True)),
        matches_played=_parse_int(cells[3].get_text(strip=True)),
        minutes_played=_parse_int(cells[4].get_text(strip=True)),
        team_name=" ".join(cells[5].get_text(" ", strip=True).split()),
    )


def _parse_int(value: str) -> int:
    try:
        return int(value)
    except ValueError as error:
        raise UplAttackersParseError(f"Expected integer value, got {value!r}.") from error


def _truncate(value: str, max_width: int) -> str:
    if len(value) <= max_width:
        return value
    return value[: max_width - 3] + "..."


def _format_line(values: tuple[str, ...], widths: list[int]) -> str:
    first_column = values[0].rjust(widths[0])
    player_column = values[1].ljust(widths[1])
    numeric_columns = [
        value.rjust(width)
        for value, width in zip(values[2:6], widths[2:6], strict=True)
    ]
    team_column = values[6].ljust(widths[6])
    return " ".join((first_column, player_column, *numeric_columns, team_column))
