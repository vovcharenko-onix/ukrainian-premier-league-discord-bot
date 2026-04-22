from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import Tag

from .upl import UPL_CALENDAR_URL, UplSiteFetchError, fetch_upl_page, normalize_team_name

KYIV_TIMEZONE: Final = ZoneInfo("Europe/Kyiv")
CALENDAR_DATE_FORMAT: Final = "%d.%m.%Y"


class UplFixturesError(RuntimeError):
    """Base error for UPL fixtures retrieval and parsing."""


class UplFixturesFetchError(UplFixturesError):
    """Raised when the calendar page cannot be retrieved."""


class UplFixturesParseError(UplFixturesError):
    """Raised when the calendar page cannot be parsed."""


@dataclass(frozen=True, slots=True)
class FixtureMatch:
    round_name: str
    match_date: date
    home_team: str
    away_team: str
    kickoff_or_result: str


@dataclass(frozen=True, slots=True)
class DailyFixtures:
    title: str
    source_url: str
    match_date: date
    matches: tuple[FixtureMatch, ...]


@dataclass(frozen=True, slots=True)
class TourSchedule:
    round_name: str
    source_url: str
    matches: tuple[FixtureMatch, ...]

    @property
    def start_date(self) -> date:
        return min(match.match_date for match in self.matches)

    @property
    def end_date(self) -> date:
        return max(match.match_date for match in self.matches)


class UplFixturesClient:
    def __init__(self, *, source_url: str = UPL_CALENDAR_URL) -> None:
        self._source_url = source_url

    def fetch_calendar_tours(self) -> tuple[TourSchedule, ...]:
        try:
            html = fetch_upl_page(self._source_url)
        except UplSiteFetchError as error:
            raise UplFixturesFetchError(
                f"Failed to fetch UPL calendar page: {self._source_url}"
            ) from error

        return parse_calendar_tours(html, source_url=self._source_url)

    def fetch_matches_for_date(self, target_date: date | None = None) -> DailyFixtures:
        current_date = target_date or datetime.now(KYIV_TIMEZONE).date()
        tours = self.fetch_calendar_tours()
        return select_matches_for_date(
            tours,
            target_date=current_date,
            source_url=self._source_url,
        )

    def fetch_current_tour(self, target_date: date | None = None) -> TourSchedule | None:
        current_date = target_date or datetime.now(KYIV_TIMEZONE).date()
        tours = self.fetch_calendar_tours()
        return select_current_tour(tours, target_date=current_date)

    def fetch_next_tour(self, target_date: date | None = None) -> TourSchedule | None:
        current_date = target_date or datetime.now(KYIV_TIMEZONE).date()
        tours = self.fetch_calendar_tours()
        return select_next_tour(tours, target_date=current_date)


def parse_calendar_page(
    html: str,
    *,
    target_date: date,
    source_url: str = UPL_CALENDAR_URL,
) -> DailyFixtures:
    tours = parse_calendar_tours(html, source_url=source_url)
    return select_matches_for_date(
        tours,
        target_date=target_date,
        source_url=source_url,
    )


def parse_calendar_tours(
    html: str,
    *,
    source_url: str = UPL_CALENDAR_URL,
) -> tuple[TourSchedule, ...]:
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.select("div.table-tour")
    if not blocks:
        raise UplFixturesParseError("No calendar tour blocks were found in the page.")

    tours = [
        _parse_tour_schedule(block, source_url=source_url)
        for block in blocks
    ]
    return tuple(tours)


def select_matches_for_date(
    tours: tuple[TourSchedule, ...],
    *,
    target_date: date,
    source_url: str = UPL_CALENDAR_URL,
) -> DailyFixtures:
    matches = tuple(
        match
        for tour in tours
        for match in tour.matches
        if match.match_date == target_date
    )

    return DailyFixtures(
        title=f"Матчі УПЛ на {target_date.strftime(CALENDAR_DATE_FORMAT)}",
        source_url=source_url,
        match_date=target_date,
        matches=matches,
    )


def select_current_tour(
    tours: tuple[TourSchedule, ...],
    *,
    target_date: date,
) -> TourSchedule | None:
    week_start, week_end = get_playing_week(target_date)
    for tour in tours:
        if week_start <= tour.start_date <= week_end:
            return tour

    return None


def select_next_tour(
    tours: tuple[TourSchedule, ...],
    *,
    target_date: date,
) -> TourSchedule | None:
    current_tour = select_current_tour(tours, target_date=target_date)
    if current_tour is not None:
        current_index = tours.index(current_tour)
        if current_index + 1 < len(tours):
            return tours[current_index + 1]
        return None

    week_start, week_end = get_playing_week(target_date)
    for tour in tours:
        if tour.start_date > week_end:
            return tour

    for tour in tours:
        if tour.start_date >= week_start:
            return tour

    return None


def get_playing_week(target_date: date) -> tuple[date, date]:
    days_since_tuesday = (target_date.weekday() - 1) % 7
    week_start = target_date - timedelta(days=days_since_tuesday)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def format_discord_daily_matches(
    fixtures: DailyFixtures,
    *,
    include_empty_message: bool = True,
    max_team_name_width: int = 18,
) -> str | None:
    if not fixtures.matches:
        if not include_empty_message:
            return None
        return f"📅 **{fixtures.title}**\nСьогодні матчів немає."

    sections = [f"📅 **{fixtures.title}**"]
    sections.extend(
        _format_tour_section(
            round_name,
            round_matches,
            headers=("Час", "Господарі", "Гості"),
            row_builder=lambda match: (
                match.kickoff_or_result,
                _truncate(match.home_team, max_team_name_width),
                _truncate(match.away_team, max_team_name_width),
            ),
        )
        for round_name, round_matches in _group_matches_by_round(fixtures.matches).items()
    )

    return "\n".join(sections)


def format_discord_tour_schedule(
    tour: TourSchedule,
    *,
    title_prefix: str,
    max_team_name_width: int = 18,
) -> str:
    return "\n".join(
        [
            f"📋 **{title_prefix}: {tour.round_name}**",
            _format_tour_section(
                None,
                list(tour.matches),
                headers=("Дата", "Час", "Господарі", "Гості"),
                row_builder=lambda match: (
                    match.match_date.strftime(CALENDAR_DATE_FORMAT),
                    match.kickoff_or_result,
                    _truncate(match.home_team, max_team_name_width),
                    _truncate(match.away_team, max_team_name_width),
                ),
            ),
        ]
    )


def _parse_tour_schedule(block: Tag, *, source_url: str) -> TourSchedule:
    round_name = _extract_required_text(block, ".tour-title", "tour title")
    matches = tuple(_parse_all_matches_for_block(block, round_name))
    if not matches:
        raise UplFixturesParseError(f"Tour {round_name!r} does not contain any matches.")

    return TourSchedule(
        round_name=round_name,
        source_url=source_url,
        matches=matches,
    )


def _parse_all_matches_for_block(
    block: Tag,
    round_name: str,
) -> list[FixtureMatch]:
    matches: list[FixtureMatch] = []
    current_date: date | None = None

    for child in block.children:
        if not isinstance(child, Tag):
            continue

        raw_classes = child.get("class")
        if raw_classes is None:
            classes: set[str] = set()
        elif isinstance(raw_classes, str):
            classes = {raw_classes}
        else:
            classes = set(raw_classes)
        if "tour-date" in classes:
            current_date = _parse_date_value(child.get_text(" ", strip=True))
            continue

        if "tour-match" not in classes:
            continue

        if current_date is None:
            raise UplFixturesParseError(
                f"Encountered a match before its date in round {round_name!r}."
            )

        matches.append(_parse_match(child, round_name, current_date))

    return matches


def _parse_match(match: Tag, round_name: str, match_date: date) -> FixtureMatch:
    home_team = normalize_team_name(
        _extract_required_text(match, ".first-team", "home team")
    )
    away_team = normalize_team_name(
        _extract_required_text(match, ".second-team", "away team")
    )
    kickoff_or_result = _extract_required_text(match, ".resualt", "match status")

    return FixtureMatch(
        round_name=round_name,
        match_date=match_date,
        home_team=home_team,
        away_team=away_team,
        kickoff_or_result=kickoff_or_result,
    )


def _parse_date_value(raw_date: str) -> date:
    try:
        return datetime.strptime(raw_date, CALENDAR_DATE_FORMAT).date()
    except ValueError as error:
        raise UplFixturesParseError(f"Unexpected calendar date value: {raw_date!r}.") from error


def _extract_required_text(parent: Tag, selector: str, label: str) -> str:
    element = _extract_required_element(parent, selector, label)
    value = element.get_text(" ", strip=True)
    if not value:
        raise UplFixturesParseError(f"Missing {label} text for selector {selector!r}.")

    return value


def _extract_required_element(parent: Tag, selector: str, label: str) -> Tag:
    element = parent.select_one(selector)
    if element is None:
        raise UplFixturesParseError(f"Missing {label} element for selector {selector!r}.")
    return element


def _truncate(value: str, max_width: int) -> str:
    if len(value) <= max_width:
        return value
    return value[: max_width - 3] + "..."


def _format_line(values: tuple[str, ...], widths: list[int]) -> str:
    return " ".join(value.ljust(width) for value, width in zip(values, widths, strict=True))


def _group_matches_by_round(
    matches: tuple[FixtureMatch, ...],
) -> OrderedDict[str, list[FixtureMatch]]:
    grouped_matches: OrderedDict[str, list[FixtureMatch]] = OrderedDict()
    for match in matches:
        grouped_matches.setdefault(match.round_name, []).append(match)

    return grouped_matches


def _format_tour_section(
    round_name: str | None,
    matches: list[FixtureMatch],
    *,
    headers: tuple[str, ...],
    row_builder: Callable[[FixtureMatch], tuple[str, ...]],
) -> str:
    rows = [row_builder(match) for match in matches]
    widths = [
        max(len(header), *(len(row[index]) for row in rows))
        for index, header in enumerate(headers)
    ]
    lines = [
        _format_line(headers, widths),
        _format_line(tuple("-" * width for width in widths), widths),
    ]
    lines.extend(_format_line(row, widths) for row in rows)

    body = "```text\n" + "\n".join(lines) + "\n```"
    if round_name is None:
        return body
    return f"**{round_name}**\n{body}"
