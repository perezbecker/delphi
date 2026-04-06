"""
Static World Cup 2026 tournament data.
Groups confirmed from the official FIFA draw (December 5, 2025, Washington D.C.).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Team:
    code: str        # 3-letter code used as primary key in predictions
    name: str
    flag: str        # Unicode flag emoji
    group: str       # "A" through "L"
    fifa_ranking: int  # Lower = better; used as final tiebreaker


# ── All 48 teams ──────────────────────────────────────────────────────────────

TEAMS: list[Team] = [
    # Group A
    Team("MEX", "Mexico",         "🇲🇽", "A",  16),
    Team("KOR", "South Korea",    "🇰🇷", "A",  22),
    Team("RSA", "South Africa",   "🇿🇦", "A",  60),
    Team("CZE", "Czechia",        "🇨🇿", "A",  37),
    # Group B
    Team("CAN", "Canada",         "🇨🇦", "B",  44),
    Team("SUI", "Switzerland",    "🇨🇭", "B",  19),
    Team("QAT", "Qatar",          "🇶🇦", "B",  37),
    Team("BIH", "Bosnia-Herz.",   "🇧🇦", "B",  65),
    # Group C
    Team("BRA", "Brazil",         "🇧🇷", "C",   5),
    Team("MAR", "Morocco",        "🇲🇦", "C",  14),
    Team("HAI", "Haiti",          "🇭🇹", "C", 140),
    Team("SCO", "Scotland",       "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "C",  39),
    # Group D
    Team("USA", "USA",            "🇺🇸", "D",  11),
    Team("PAR", "Paraguay",       "🇵🇾", "D",  62),
    Team("AUS", "Australia",      "🇦🇺", "D",  23),
    Team("TUR", "Türkiye",        "🇹🇷", "D",  29),
    # Group E
    Team("GER", "Germany",        "🇩🇪", "E",  12),
    Team("CUW", "Curaçao",        "🇨🇼", "E", 100),
    Team("CIV", "Ivory Coast",    "🇨🇮", "E",  48),
    Team("ECU", "Ecuador",        "🇪🇨", "E",  42),
    # Group F
    Team("NED", "Netherlands",    "🇳🇱", "F",   7),
    Team("JPN", "Japan",          "🇯🇵", "F",  17),
    Team("SWE", "Sweden",         "🇸🇪", "F",  25),
    Team("TUN", "Tunisia",        "🇹🇳", "F",  34),
    # Group G
    Team("BEL", "Belgium",        "🇧🇪", "G",   3),
    Team("EGY", "Egypt",          "🇪🇬", "G",  35),
    Team("IRN", "Iran",           "🇮🇷", "G",  21),
    Team("NZL", "New Zealand",    "🇳🇿", "G",  96),
    # Group H
    Team("ESP", "Spain",          "🇪🇸", "H",   6),
    Team("CPV", "Cape Verde",     "🇨🇻", "H",  73),
    Team("KSA", "Saudi Arabia",   "🇸🇦", "H",  58),
    Team("URU", "Uruguay",        "🇺🇾", "H",  18),
    # Group I
    Team("FRA", "France",         "🇫🇷", "I",   2),
    Team("SEN", "Senegal",        "🇸🇳", "I",  20),
    Team("IRQ", "Iraq",           "🇮🇶", "I",  63),
    Team("NOR", "Norway",         "🇳🇴", "I",  26),
    # Group J
    Team("ARG", "Argentina",      "🇦🇷", "J",   1),
    Team("ALG", "Algeria",        "🇩🇿", "J",  36),
    Team("AUT", "Austria",        "🇦🇹", "J",  24),
    Team("JOR", "Jordan",         "🇯🇴", "J",  87),
    # Group K
    Team("POR", "Portugal",       "🇵🇹", "K",   8),
    Team("COD", "DR Congo",       "🇨🇩", "K",  56),
    Team("UZB", "Uzbekistan",     "🇺🇿", "K",  74),
    Team("COL", "Colombia",       "🇨🇴", "K",   9),
    # Group L
    Team("ENG", "England",        "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "L",   4),
    Team("CRO", "Croatia",        "🇭🇷", "L",  10),
    Team("GHA", "Ghana",          "🇬🇭", "L",  66),
    Team("PAN", "Panama",         "🇵🇦", "L",  79),
]

# Fast lookups
TEAM_BY_CODE: dict[str, Team] = {t.code: t for t in TEAMS}
TEAMS_BY_GROUP: dict[str, list[Team]] = {}
for _t in TEAMS:
    TEAMS_BY_GROUP.setdefault(_t.group, []).append(_t)

GROUPS: list[str] = list("ABCDEFGHIJKL")


# ── Group stage match schedule ────────────────────────────────────────────────
# Round-robin within each group (6 matches per group, 72 total).
# Match day pairing order: (0v1, 2v3), (0v2, 1v3), (0v3, 1v2)  [0-indexed]

@dataclass(frozen=True)
class GroupMatch:
    match_id: str          # e.g. "GS_A_1"
    group: str
    match_day: int         # 1, 2, or 3
    home_code: str
    away_code: str

    @property
    def home(self) -> Team:
        return TEAM_BY_CODE[self.home_code]

    @property
    def away(self) -> Team:
        return TEAM_BY_CODE[self.away_code]


def _build_group_matches() -> list[GroupMatch]:
    matches = []
    pairings = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
    match_days = [1, 1, 2, 2, 3, 3]
    for group in GROUPS:
        teams = TEAMS_BY_GROUP[group]
        for n, ((i, j), md) in enumerate(zip(pairings, match_days), start=1):
            matches.append(GroupMatch(
                match_id=f"GS_{group}_{n}",
                group=group,
                match_day=md,
                home_code=teams[i].code,
                away_code=teams[j].code,
            ))
    return matches


GROUP_MATCHES: list[GroupMatch] = _build_group_matches()
GROUP_MATCH_BY_ID: dict[str, GroupMatch] = {m.match_id: m for m in GROUP_MATCHES}
GROUP_MATCHES_BY_GROUP: dict[str, list[GroupMatch]] = {}
for _m in GROUP_MATCHES:
    GROUP_MATCHES_BY_GROUP.setdefault(_m.group, []).append(_m)


# ── Knockout bracket structure ────────────────────────────────────────────────

@dataclass(frozen=True)
class KnockoutMatch:
    match_id: str          # e.g. "R32_73", "R16_89", "QF_97", "SF_101", "F_103"
    round: str             # "R32", "R16", "QF", "SF", "F"
    match_num: int
    # Each slot is one of:
    #   "W_{group}"   → group winner
    #   "RU_{group}"  → group runner-up
    #   "3rd_M{n}"    → best 3rd place assigned to this match (eligible groups in slot_groups)
    #   "W_M{n}"      → winner of knockout match n
    home_slot: str
    away_slot: str
    # For 3rd-place slots: the set of eligible source groups (empty for other slot types)
    third_eligible: frozenset[str] = field(default_factory=frozenset)

    @property
    def home(self) -> Team | None:
        return TEAM_BY_CODE.get(self.home_slot)

    @property
    def away(self) -> Team | None:
        return TEAM_BY_CODE.get(self.away_slot)


KNOCKOUT_MATCHES: list[KnockoutMatch] = [
    # ── Round of 32 ──────────────────────────────────────────────────────────
    KnockoutMatch("R32_73",  "R32",  73,  "RU_A",   "RU_B"),
    KnockoutMatch("R32_74",  "R32",  74,  "W_E",    "3rd_M74",  frozenset("ABCDF")),
    KnockoutMatch("R32_75",  "R32",  75,  "W_F",    "RU_C"),
    KnockoutMatch("R32_76",  "R32",  76,  "W_C",    "RU_F"),
    KnockoutMatch("R32_77",  "R32",  77,  "W_I",    "3rd_M77",  frozenset("CDFGH")),
    KnockoutMatch("R32_78",  "R32",  78,  "RU_E",   "RU_I"),
    KnockoutMatch("R32_79",  "R32",  79,  "W_A",    "3rd_M79",  frozenset("CEFHI")),
    KnockoutMatch("R32_80",  "R32",  80,  "W_L",    "3rd_M80",  frozenset("EHIJK")),
    KnockoutMatch("R32_81",  "R32",  81,  "W_D",    "3rd_M81",  frozenset("BEFIJ")),
    KnockoutMatch("R32_82",  "R32",  82,  "W_G",    "3rd_M82",  frozenset("AEHIJ")),
    KnockoutMatch("R32_83",  "R32",  83,  "RU_K",   "RU_L"),
    KnockoutMatch("R32_84",  "R32",  84,  "W_H",    "RU_J"),
    KnockoutMatch("R32_85",  "R32",  85,  "W_B",    "3rd_M85",  frozenset("EFGIJ")),
    KnockoutMatch("R32_86",  "R32",  86,  "W_J",    "RU_H"),
    KnockoutMatch("R32_87",  "R32",  87,  "W_K",    "3rd_M87",  frozenset("DEIJL")),
    KnockoutMatch("R32_88",  "R32",  88,  "RU_D",   "RU_G"),
    # ── Round of 16 ──────────────────────────────────────────────────────────
    KnockoutMatch("R16_89",  "R16",  89,  "W_M74",  "W_M77"),
    KnockoutMatch("R16_90",  "R16",  90,  "W_M73",  "W_M75"),
    KnockoutMatch("R16_91",  "R16",  91,  "W_M76",  "W_M78"),
    KnockoutMatch("R16_92",  "R16",  92,  "W_M79",  "W_M80"),
    KnockoutMatch("R16_93",  "R16",  93,  "W_M83",  "W_M84"),
    KnockoutMatch("R16_94",  "R16",  94,  "W_M81",  "W_M82"),
    KnockoutMatch("R16_95",  "R16",  95,  "W_M86",  "W_M88"),
    KnockoutMatch("R16_96",  "R16",  96,  "W_M85",  "W_M87"),
    # ── Quarterfinals ────────────────────────────────────────────────────────
    KnockoutMatch("QF_97",   "QF",   97,  "W_M89",  "W_M90"),
    KnockoutMatch("QF_98",   "QF",   98,  "W_M93",  "W_M94"),
    KnockoutMatch("QF_99",   "QF",   99,  "W_M91",  "W_M92"),
    KnockoutMatch("QF_100",  "QF",  100,  "W_M95",  "W_M96"),
    # ── Semifinals ───────────────────────────────────────────────────────────
    KnockoutMatch("SF_101",  "SF",  101,  "W_M97",  "W_M98"),
    KnockoutMatch("SF_102",  "SF",  102,  "W_M99",  "W_M100"),
    # ── Final ────────────────────────────────────────────────────────────────
    KnockoutMatch("F_103",   "F",   103,  "W_M101", "W_M102"),
]

KNOCKOUT_BY_ID: dict[str, KnockoutMatch] = {m.match_id: m for m in KNOCKOUT_MATCHES}
KNOCKOUT_BY_NUM: dict[int, KnockoutMatch] = {m.match_num: m for m in KNOCKOUT_MATCHES}
KNOCKOUT_BY_ROUND: dict[str, list[KnockoutMatch]] = {}
for _km in KNOCKOUT_MATCHES:
    KNOCKOUT_BY_ROUND.setdefault(_km.round, []).append(_km)

ROUND_POINTS: dict[str, int] = {
    "GS": 1,
    "R32": 1,
    "R16": 2,
    "QF": 4,
    "SF": 8,
    "F": 16,
}

ROUND_LABELS: dict[str, str] = {
    "R32": "Round of 32",
    "R16": "Round of 16",
    "QF": "Quarterfinals",
    "SF": "Semifinals",
    "F": "Final",
}

# ── Visual bracket layout ─────────────────────────────────────────────────────
# Matches ordered top-to-bottom for the visual bracket display.
# Derived from the bracket feeder structure: pairs feed into next-round matches.

BRACKET_R32_ORDER = [
    "R32_74", "R32_77", "R32_73", "R32_75", "R32_83", "R32_84", "R32_81", "R32_82",
    "R32_76", "R32_78", "R32_79", "R32_80", "R32_86", "R32_88", "R32_85", "R32_87",
]
BRACKET_R16_ORDER = ["R16_89", "R16_90", "R16_93", "R16_94", "R16_91", "R16_92", "R16_95", "R16_96"]
BRACKET_QF_ORDER  = ["QF_97", "QF_98", "QF_99", "QF_100"]
BRACKET_SF_ORDER  = ["SF_101", "SF_102"]
BRACKET_F_ORDER   = ["F_103"]

_BRACKET_ALL_ORDERS = [
    BRACKET_R32_ORDER, BRACKET_R16_ORDER, BRACKET_QF_ORDER,
    BRACKET_SF_ORDER, BRACKET_F_ORDER,
]


def _compute_bracket_layout() -> tuple[dict[str, int], dict[str, int]]:
    S = 100  # vertical slot height per R32 match (px)
    centers: dict[str, int] = {}
    prev_order: list[str] | None = None
    for order in _BRACKET_ALL_ORDERS:
        if prev_order is None:
            for i, mid in enumerate(order):
                centers[mid] = i * S + S // 2
        else:
            for j, mid in enumerate(order):
                a = centers[prev_order[2 * j]]
                b = centers[prev_order[2 * j + 1]]
                centers[mid] = (a + b) // 2
        prev_order = order
    tops = {mid: c - 40 for mid, c in centers.items()}  # 40 = half card height (80px)
    return centers, tops


BRACKET_CENTERS, BRACKET_TOPS = _compute_bracket_layout()
BRACKET_HEIGHT = 1600   # 16 R32 slots × 100px
BRACKET_CARD_WIDTH = 170

# SVG connector path strings — one per inter-round gap.
# Each path draws "]"-shaped connectors from two source match centers to
# the midpoint (→ next-round match center).  viewBox="0 0 30 {BRACKET_HEIGHT}"
BRACKET_SVG_PATHS: dict[str, str] = {
    "R32_R16": (
        "M 0 50 H 15 V 150 M 0 150 H 15 M 15 100 H 30 "
        "M 0 250 H 15 V 350 M 0 350 H 15 M 15 300 H 30 "
        "M 0 450 H 15 V 550 M 0 550 H 15 M 15 500 H 30 "
        "M 0 650 H 15 V 750 M 0 750 H 15 M 15 700 H 30 "
        "M 0 850 H 15 V 950 M 0 950 H 15 M 15 900 H 30 "
        "M 0 1050 H 15 V 1150 M 0 1150 H 15 M 15 1100 H 30 "
        "M 0 1250 H 15 V 1350 M 0 1350 H 15 M 15 1300 H 30 "
        "M 0 1450 H 15 V 1550 M 0 1550 H 15 M 15 1500 H 30"
    ),
    "R16_QF": (
        "M 0 100 H 15 V 300 M 0 300 H 15 M 15 200 H 30 "
        "M 0 500 H 15 V 700 M 0 700 H 15 M 15 600 H 30 "
        "M 0 900 H 15 V 1100 M 0 1100 H 15 M 15 1000 H 30 "
        "M 0 1300 H 15 V 1500 M 0 1500 H 15 M 15 1400 H 30"
    ),
    "QF_SF": (
        "M 0 200 H 15 V 600 M 0 600 H 15 M 15 400 H 30 "
        "M 0 1000 H 15 V 1400 M 0 1400 H 15 M 15 1200 H 30"
    ),
    "SF_F": "M 0 400 H 15 V 1200 M 0 1200 H 15 M 15 800 H 30",
}
