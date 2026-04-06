# Delphi — World Cup 2026 Prediction Pool: Code Description

## Overview

Delphi is a private web application for running a World Cup 2026 prediction pool among ~30 friends. Users register with an invite code, predict every group stage score and every knockout stage winner before the tournament starts, then earn points as real results come in. A live leaderboard tracks standings throughout the tournament.

The app is built entirely server-side: FastAPI handles routing and business logic, Jinja2 renders HTML templates, HTMX handles dynamic partial updates without a JavaScript framework, and Bootstrap 5 provides styling.

---

## Architecture at a Glance

```
Browser ──HTMX/Form─→ FastAPI Router ──→ Service Layer ──→ SQLAlchemy ORM ──→ DB
                            │                                                  │
                         Jinja2 ←──── Template Response ←── Bracket/Scoring ──┘
```

- **No client-side JavaScript framework** — all state lives on the server; the browser receives pre-rendered HTML fragments.
- **HTMX** drives dynamic updates: form submissions swap partial HTML fragments in-place without full page reloads.
- **SQLite** in development, **PostgreSQL** in production (Azure Flexible Server). The ORM code is identical in both environments.

---

## Directory Structure

```
delphi/
├── app/
│   ├── main.py                    # App factory, lifespan, root route
│   ├── config.py                  # Pydantic-settings config
│   ├── database.py                # SQLAlchemy engine + session
│   ├── models.py                  # ORM models: User, Prediction, ActualResult
│   ├── auth.py                    # Password hashing, sessions, FastAPI deps
│   ├── routers/
│   │   ├── auth.py                # /login, /register, /logout
│   │   ├── predictions.py         # /predictions (group + knockout + view others)
│   │   ├── leaderboard.py         # /leaderboard
│   │   └── admin.py               # /admin/results, backup/restore
│   └── tournament/
│       ├── data.py                # Static WC2026 data + visual bracket constants
│       ├── standings.py           # FIFA group standings + tiebreaker logic
│       ├── bracket.py             # Per-user bracket computation
│       └── scoring.py             # Points calculation
├── templates/
│   ├── base.html                  # Navbar, Bootstrap, HTMX CDN
│   ├── home.html                  # Spanish landing page (unauthenticated)
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── predictions/
│   │   ├── index.html             # Tabbed predictions page
│   │   └── partials/
│   │       ├── group_card.html    # Score input forms + standings table
│   │       └── knockout_bracket.html  # Visual bracket with winner buttons
│   ├── leaderboard.html
│   └── admin/
│       └── results.html           # Result entry + backup/restore
├── static/css/style.css           # Custom CSS (bracket layout, score inputs)
├── images/                        # Static images (served at /images/)
├── alembic/                       # Database migrations
├── alembic.ini
├── requirements.txt
├── .env.example
└── INSTALL.md
```

---

## Python Modules

### `app/main.py` — Application Factory

The entry point. Creates the FastAPI app, mounts static file directories, registers routers, and defines the root route.

**Lifespan handler** (`lifespan`): Runs at startup before the app accepts requests.
1. Calls `Base.metadata.create_all(bind=engine)` as a dev fallback (Alembic handles production migrations).
2. If `ADMIN_USERNAME` env var is set, queries the `User` table and promotes that user to admin if they exist and aren't already.

**Static mounts**:
- `/static` → `static/` directory (CSS, JS assets)
- `/images` → `images/` directory (banner images for the landing page)

**Root route** (`GET /`): Checks if the request carries a valid session cookie via `get_current_user`. Authenticated users are redirected to `/predictions`; unauthenticated users see the Spanish landing page (`home.html`).

**Router registration**: Includes all four routers (`auth`, `predictions`, `leaderboard`, `admin`), each with their own URL prefix.

---

### `app/config.py` — Configuration

Uses **pydantic-settings** to read environment variables (and a `.env` file in development).

```python
class Settings(BaseSettings):
    database_url: str = "sqlite:///./delphi.db"
    secret_key: str
    invite_code: str = "worldcup2026"
    tournament_start: datetime = datetime(2026, 6, 11, 18, 0, 0, tzinfo=UTC)
    admin_username: str | None = None
```

**`is_locked()` method**: Returns `True` if `datetime.now(UTC) >= tournament_start`. This single method controls all prediction locking throughout the app: POST routes return 403 when locked, templates render read-only forms, badges change from green "Open" to red "Locked".

A module-level `settings = Settings()` singleton is imported everywhere that needs configuration.

---

### `app/database.py` — Database Layer

Creates the SQLAlchemy engine. For SQLite, passes `connect_args={"check_same_thread": False}` because FastAPI may run sync handlers in a thread pool. For PostgreSQL (detected from `DATABASE_URL`), no special args are needed.

Exports:
- `engine` — the SQLAlchemy engine
- `SessionLocal` — a `sessionmaker` factory producing sync sessions
- `Base` — `DeclarativeBase` that all ORM models inherit from
- `get_db()` — a FastAPI dependency generator that yields a session and closes it after the request

---

### `app/models.py` — ORM Models

Three tables:

**`User`**
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | auto-increment |
| `username` | String(50) | unique, not null |
| `password_hash` | String | bcrypt output |
| `is_admin` | Boolean | default False |
| `created_at` | DateTime | default `datetime.utcnow` |

**`Prediction`**
| Column | Type | Notes |
|---|---|---|
| `id` | Integer PK | auto-increment |
| `user_id` | Integer FK → User | not null |
| `match_id` | String | e.g. `GS_A_1`, `R32_73`, `F_103` |
| `home_score` | Integer | null for knockout rows |
| `away_score` | Integer | null for knockout rows |
| `winner_code` | String | null for group stage rows |

A `UniqueConstraint` on `(user_id, match_id)` ensures one prediction per match per user. Group stage rows carry `home_score` + `away_score`; knockout rows carry `winner_code` (a team code string like `"MEX"`).

**`ActualResult`**
| Column | Type | Notes |
|---|---|---|
| `match_id` | String PK | same ID scheme as Prediction |
| `home_score` | Integer | null for knockout |
| `away_score` | Integer | null for knockout |
| `winner_code` | String | null for group stage |
| `completed` | Boolean | admin ticks this when done |

Admin enters actual results here; scoring compares `Prediction` rows against `ActualResult` rows.

---

### `app/auth.py` — Authentication

**Password hashing**: `hash_password(plain)` uses `bcrypt.hashpw` with `bcrypt.gensalt(rounds=12)`. `verify_password(plain, hashed)` uses `bcrypt.checkpw`.

**Session tokens**: Uses `itsdangerous.URLSafeTimedSerializer` keyed with `settings.secret_key`.
- `create_session_token(user_id)` — serializes `{"user_id": user_id}` into a signed token string.
- `decode_session_token(token)` — deserializes and validates the token; returns `user_id` or `None` if invalid/expired (max age 30 days).

**FastAPI dependencies**:
- `get_current_user(request, db)` — reads the `session` cookie, decodes it, queries the User. Returns `User | None`. Used on routes that show different content for guests vs. authenticated users (e.g., the root `/` route).
- `require_user(request, db)` — calls `get_current_user`; raises `HTTPException(303, headers={"Location": "/login"})` if no user. Used on all routes that require login.
- `require_admin(user)` — depends on `require_user`; raises `HTTPException(403)` if `user.is_admin` is False.

---

### `app/routers/auth.py` — Auth Routes

**`GET /login`** — renders `auth/login.html`.

**`POST /login`** — looks up user by username, verifies password, creates session token, sets an httponly cookie named `session`, redirects to `/predictions`. On failure, re-renders login with an error message.

**`GET /register`** — renders `auth/register.html`.

**`POST /register`**:
1. Validates that `invite_code` matches `settings.invite_code`.
2. Checks username uniqueness.
3. Hashes password with bcrypt.
4. Checks if this is the first user (`db.query(User).count() == 0`); if so, sets `is_admin=True`.
5. Checks if username matches `settings.admin_username`; if so, sets `is_admin=True`.
6. Saves user, creates session token, sets cookie, redirects to `/predictions`.

**`GET /logout`** — deletes the `session` cookie and redirects to `/`.

---

### `app/routers/predictions.py` — Predictions Routes

The most complex router. Handles group stage score entry, knockout winner picks, and viewing other users' brackets.

**Helper functions**:

`_get_bracket(user_id, db)` — thin wrapper calling `compute_user_bracket(user_id, db)`. Returns a `BracketState` object.

`_knockout_context(bracket, locked, readonly)` — bundles all bracket layout data into a dict for template responses: `matches_by_id` (dict of match_id → MatchState), all `BRACKET_*` layout constants, and flags for whether picks are allowed.

**Routes**:

`GET /predictions` — The main predictions page for the logged-in user. Loads the user's bracket, their group stage predictions (filtered to `GS_%` match IDs), and all users (for the post-lock user-switcher dropdown). Renders `predictions/index.html` with `readonly=False`.

`POST /predictions/group/{match_id}` — Saves a group stage score:
1. Rejects if locked (403).
2. Validates scores are 0–20.
3. Upserts the `Prediction` row (updates if exists, inserts if not).
4. **Wipes all knockout predictions** for this user (`match_id.notlike("GS_%")`). This is necessary because changing a group score changes which teams qualify, invalidating all previously saved knockout picks.
5. Recomputes the bracket and returns the updated group card partial (`group_card.html`).
6. Sets `HX-Trigger: refreshKnockout` response header, which instructs the browser's HTMX listener to reload the knockout bracket.

`GET /predictions/knockout` — Returns just the knockout bracket partial for HTMX lazy loading (on tab click) or on `refreshKnockout` trigger.

`POST /predictions/knockout/{match_id}` — Saves a knockout winner pick:
1. Rejects if locked.
2. Validates `winner_code` is a known team code.
3. Upserts the `Prediction` row.
4. Recomputes the bracket and returns the full updated knockout partial.

`GET /predictions/{username}` — View another user's predictions (read-only). **Returns 403 if not locked** — predictions stay private until the tournament starts. After lock, renders the same `predictions/index.html` with `readonly=True` and `target_user` set.

`GET /predictions/{username}/knockout` — Returns the knockout bracket partial for another user. **Returns 403 if not locked.**

---

### `app/routers/leaderboard.py` — Leaderboard

`GET /leaderboard` — Computes scores for all users via `compute_all_scores`, assigns ranks (ties share the same rank — multiple users can share rank 1, etc.), renders `leaderboard.html`.

The leaderboard uses HTMX auto-polling every 60 seconds (`hx-trigger="every 60s"`) with `hx-select="#leaderboard-table"` to replace only the table element, keeping page scroll position stable.

---

### `app/routers/admin.py` — Admin Panel

All routes require `require_admin`.

**Result entry**:

`POST /admin/results/group/{match_id}` — Upserts an `ActualResult` row with `home_score`, `away_score`, and `completed` flag.

`POST /admin/results/knockout/{match_id}` — Upserts an `ActualResult` row with `winner_code` and `completed` flag.

`GET /admin/results` — Renders the full admin results page with all matches pre-loaded.

**Backup/Restore** (data safety for migration or disaster recovery):

`GET /admin/export/backup` — Builds an in-memory ZIP archive containing three CSV files:
- `users.csv` — all user records (id, username, password_hash, is_admin, created_at)
- `predictions.csv` — all predictions
- `results.csv` — all actual results
Returns the ZIP as a downloadable file response.

`POST /admin/import/backup` — Accepts a ZIP file upload and performs a full restore:
1. Deletes all predictions, results, and users (in that order to respect FK constraints).
2. Re-inserts users first (to re-establish FK targets), then predictions and results.
This is an all-or-nothing restore — intended for migrating between databases (SQLite → PostgreSQL) or recovering from data loss.

---

## Tournament Module

### `app/tournament/data.py` — Static Tournament Data

The single source of truth for all tournament structure. No database reads — everything here is a Python constant.

**`Team` dataclass**:
```python
@dataclass
class Team:
    code: str        # e.g. "MEX"
    name: str        # e.g. "Mexico"
    flag: str        # Unicode emoji e.g. "🇲🇽"
    group: str       # "A" through "L"
    fifa_rank: int   # Used as final tiebreaker in group standings
```

48 teams are defined (4 per group × 12 groups). `TEAM_BY_CODE` is a dict for O(1) lookup. `TEAMS_BY_GROUP` groups them by group letter. `GROUPS` is the list `["A", "B", ..., "L"]`.

**`GroupMatch` dataclass**: `match_id`, `home` (Team), `away` (Team), `group`. `GROUP_MATCHES` contains all 72 round-robin matches (each pair within each group of 4 plays once). `GROUP_MATCHES_BY_GROUP` indexes them by group for the template.

**`KnockoutMatch` dataclass**: `match_id`, `round` (e.g. `"R32"`), `match_num` (73–103), `home_slot`, `away_slot`. Slots use a string encoding:
- `"W_A"` — winner of Group A
- `"RU_B"` — runner-up of Group B
- `"3rd_M74"` — best 3rd-place team assigned to match 74's slot
- `"W_M73"` — winner of knockout match 73

`KNOCKOUT_MATCHES` contains all 31 knockout matches in order (R32: M73–M88, R16: M89–M96, QF: M97–M100, SF: M101–M102, F: M103). The 3rd-place playoff is excluded.

**Scoring constants**:
```python
ROUND_POINTS = {"GS": 1, "R32": 1, "R16": 2, "QF": 4, "SF": 8, "F": 16}
ROUND_LABELS = {"R32": "Round of 32", "R16": "Round of 16", ...}
```

**Visual bracket layout constants**: Pre-computed positions for the visual bracket rendered in `knockout_bracket.html`.

`BRACKET_R32_ORDER` through `BRACKET_F_ORDER` — lists of match IDs in the visual top-to-bottom order for each column.

`_compute_bracket_layout()` — generates pixel Y positions for each match card, spacing them evenly within each round column. Returns `BRACKET_CENTERS` (center Y per match) and `BRACKET_TOPS` (top Y per match, for CSS `top:` values).

`BRACKET_HEIGHT = 1600` — total SVG/layout height in pixels.

`BRACKET_SVG_PATHS` — a list of 4 SVG path strings, one per connector column (between R32↔R16, R16↔QF, QF↔SF, SF↔F). Each path string is a series of `M` (moveto) and `L` (lineto) commands drawing horizontal and vertical connector lines between adjacent rounds' match cards.

All these constants are computed once at module import and passed to templates via `_knockout_context()`.

---

### `app/tournament/standings.py` — Group Standings

Computes where each team finishes in their group based on predicted (or actual) scores.

**`TeamStanding` dataclass**:
```python
@dataclass
class TeamStanding:
    team: Team
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int

    @property
    def points(self): return self.wins * 3 + self.draws
    @property
    def gd(self): return self.goals_for - self.goals_against
```

**`compute_group_standings(group, scores)`**:
- `scores` is a dict mapping `match_id → (home_score, away_score)`
- Initializes a `TeamStanding` for each of the 4 teams in the group
- Iterates all 6 group matches; for each match with a predicted score, updates wins/draws/losses and goal tallies for both teams
- Returns the 4 standings sorted by `_sort_standings`

**`_sort_standings(standings)`**: Applies FIFA tiebreaker logic:
1. Points (descending)
2. Goal difference (descending)
3. Goals for (descending)
4. Points in head-to-head matches among tied teams
5. GD in head-to-head matches
6. GF in head-to-head matches
7. FIFA ranking (ascending — lower ranking number = better)

When multiple teams are tied on overall points, `_resolve_tie` is called on the tied subset. It computes H2H statistics by looking only at matches played between those tied teams. If H2H stats still produce a tie among a subset, the process recurses on that subset.

**`_h2h_points(team, opponents, scores)`**: For a given team and its opponents, sums points earned only in direct matches against those opponents. Returns `(points, gd, gf)` tuple.

This logic is used both for bracket computation (predicted scores) and for scoring verification.

---

### `app/tournament/bracket.py` — Bracket Computation

Computes the full predicted bracket state for one user.

**`MatchState` dataclass**:
```python
@dataclass
class MatchState:
    match_id: str
    round: str
    match_num: int
    home_team: Team | None      # None = not yet determinable (TBD)
    away_team: Team | None
    predicted_winner: Team | None  # None = user hasn't picked yet
```

**`BracketState` dataclass**:
```python
@dataclass
class BracketState:
    group_standings: dict[str, list[TeamStanding]]  # group → sorted standings
    slot_map: dict[str, Team | None]                # slot string → Team
    knockout_matches: list[MatchState]
    is_complete: bool                               # True if all matches have a predicted winner
```

**`load_user_predictions(user_id, db)`**: Queries all `Prediction` rows for the user. Returns a dict:
- For group stage rows: `match_id → (home_score, away_score)`
- For knockout rows: `match_id → winner_code`

**`_assign_third_place_teams(standings_by_group, slot_map)`**: This is the most complex function. FIFA's R32 bracket has 8 specific slots for 3rd-place teams, each with a constraint on which source groups are eligible (e.g., slot `3rd_M74` accepts teams from groups A, B, C, D, or F).

The algorithm:
1. Sorts all 12 groups' 3rd-place teams by overall quality (points → GD → GF → FIFA rank).
2. Takes the top 8.
3. Uses **backtracking** to assign them to the 8 R32 slots:
   - Sorts slots by most-constrained first (fewest eligible qualifying groups).
   - Greedily assigns the best available team whose source group is eligible.
   - If assignment fails (no eligible team for a slot), backtracks and tries the next candidate.
4. Writes assigned teams into `slot_map` as `"3rd_M74"`, `"3rd_M77"`, etc.

**`_resolve_slot(slot, slot_map)`**: Converts a slot string into a `Team | None`. Handles:
- `"W_A"` → looks up `slot_map["W_A"]`
- `"W_M73"` → looks up `slot_map["W_M73"]` (winner of match 73, set after that match is processed)
- `"3rd_M74"` → looks up `slot_map["3rd_M74"]` (set by `_assign_third_place_teams`)

**`compute_user_bracket(user_id, db)`**: Full pipeline:
1. Calls `load_user_predictions` to get all predictions.
2. Computes `group_standings` for all 12 groups using `compute_group_standings`.
3. Builds the initial `slot_map`: `W_A → 1st place team`, `RU_A → 2nd place team`, for all 12 groups.
4. Calls `_assign_third_place_teams` to populate the 8 third-place slots.
5. Iterates all 31 knockout matches in order:
   - Resolves `home_team` and `away_team` via `_resolve_slot`.
   - Looks up the user's predicted winner (if any) from their stored `Prediction`.
   - If predicted winner matches home or away team, records it; otherwise treats as no pick (handles the case where bracket changed after a group update wiped knockout picks).
   - Writes the predicted winner into `slot_map["W_M{match_num}"]` for downstream matches.
6. Returns a `BracketState`.

---

### `app/tournament/scoring.py` — Points Calculation

**`ScoreBreakdown` dataclass**:
```python
@dataclass
class ScoreBreakdown:
    total: int
    by_round: dict[str, int]   # e.g. {"GS": 5, "R32": 2, "R16": 4, ...}
    correct: int               # total correct predictions
    total_predicted: int       # total predictions made
```

**`compute_user_score(user_id, db)`**:
1. Loads all `ActualResult` rows where `completed=True`.
2. Loads all `Prediction` rows for the user.
3. For group stage matches: derives the outcome (W/D/L) from `sign(home - away)` for both the prediction and the actual result. Awards `ROUND_POINTS["GS"] = 1` if they match.
4. For knockout matches: compares `Prediction.winner_code` to `ActualResult.winner_code`. Awards `ROUND_POINTS[round]` if they match.
5. Returns a `ScoreBreakdown`.

**`compute_all_scores(db)`**: Runs `compute_user_score` for every user. Returns `dict[user_id, ScoreBreakdown]`. Used by the leaderboard route.

---

## Templates

### `templates/base.html` — Base Layout

All pages extend this. Provides:
- Bootstrap 5 CSS (via CDN)
- HTMX (via CDN)
- Custom stylesheet: `static/css/style.css`
- Navbar: brand "⚽ Delphi 2026", links to Predictions / Leaderboard / Admin (if admin) / Logout
- `{% block content %}` for page content
- `{% block title %}` for the page `<title>`

---

### `templates/home.html` — Landing Page

Shown to unauthenticated visitors. All text is in Spanish. Sections:
- **Hero**: `images/quiniela.png` banner image, "Quiniela Mundialista Miau 2026" heading, Login and Register buttons.
- **Fase de Grupos card**: Explains group stage prediction rules (predict exact scores, 1 point per correct outcome, scores used for FIFA tiebreakers).
- **Fase Eliminatoria card**: Explains knockout predictions (pick the winner of each match), includes the points-per-round scoring table (1/2/4/8/16).
- **Reglas Generales card**: Lock time (June 11 2026 18:00 UTC), visibility of other brackets after lock, knockout reset on group stage changes, leaderboard update process.

---

### `templates/predictions/index.html` — Main Predictions Page

Used for both own predictions (`readonly=False`) and viewing others (`readonly=True`).

**Header**: Shows username (own or other user's) and locked/unlocked badge.

**Alert**: Shown only when `not readonly and not locked` — instructs user to fill in group scores.

**User-switcher dropdown**: Shown only when `locked=True`. A Bootstrap select element lists all users; `onchange="window.location='/predictions/'+this.value"` navigates to that user's predictions. A "← My Bracket" button appears when viewing another user's bracket.

**Two Bootstrap tabs**:

1. **Group Stage tab** (`#tab-groups`): Renders all 12 group cards using the `group_card.html` partial via Jinja2 `{% include %}`.

2. **Knockout Stage tab** (`#tab-knockout`): Uses a two-div HTMX pattern to avoid a nesting bug:
   ```html
   <!-- Stable outer wrapper — never swapped, holds HTMX event listener -->
   <div id="knockout-wrapper"
        hx-get="/predictions/knockout"
        hx-target="#knockout-bracket"
        hx-swap="outerHTML"
        hx-trigger="refreshKnockout from:body">
     <!-- Inner swappable target -->
     <div id="knockout-bracket">
       <spinner>Loading…</spinner>
     </div>
   </div>
   ```
   The tab button also loads the bracket via `hx-get` with `hx-trigger="click once"` — lazy-loading only on first click.

   **Why the two-div pattern**: If both the HTMX trigger listener and the swap target share the same element ID, replacing the inner element via `outerHTML` destroys the HTMX attributes on the outer wrapper, breaking all future `refreshKnockout` events and winner-pick interactions. The stable `#knockout-wrapper` keeps `hx-trigger` alive indefinitely; `#knockout-bracket` is freely replaced by HTMX responses.

---

### `templates/predictions/partials/group_card.html` — Group Card

Rendered for each of the 12 groups. Contains:

**FIFA standings table** (`.standings-table`): 4 rows, one per team. Shows Pos, Flag+Name, W, D, L, GF, GA, GD, Pts. Top 2 rows highlighted green (qualifiers), 3rd row highlighted yellow (potential best-3rd).

**6 match rows**: For each group match, an inline form:
```html
<form hx-post="/predictions/group/{match_id}"
      hx-trigger="change"
      hx-target="#group-{group}"
      hx-swap="outerHTML">
  <input type="number" name="home_score" class="score-input" min="0" max="20">
  <span>–</span>
  <input type="number" name="away_score" class="score-input" min="0" max="20">
</form>
```
When a user changes a score input (on blur/change), HTMX posts the form and replaces the entire group card with the server response. Inputs are disabled when `locked=True`.

The card is identified by `id="group-{group}"` (e.g. `id="group-A"`) so HTMX knows where to swap it.

---

### `templates/predictions/partials/knockout_bracket.html` — Knockout Bracket

Renders the visual bracket with absolute CSS positioning. The entire partial is wrapped in `<div id="knockout-bracket">` — this is the element that gets outerHTML-swapped on every update.

**Layout**: Uses a `position: relative` container (`.bracket-layout`) 970px wide and 1600px tall. Five round columns are placed at left offsets 0, 200, 400, 600, 800px. Each column shows match cards (`.bk-card`) absolutely positioned using the pre-computed `BRACKET_TOPS` values.

**Column headers**: Absolutely positioned `.bracket-header-cell` elements at top: 0 for each column.

**SVG connectors**: Four `<svg>` elements (`class="bk-svg"`) rendered between each pair of adjacent columns. Each SVG uses the pre-computed `BRACKET_SVG_PATHS` strings — series of `M x,y L x,y` commands drawing the connector lines.

**Jinja2 `match_card` macro**: Takes `(ms, left, top, locked, readonly)` and renders a `.bk-card` positioned at the given pixel coordinates. Inside the card:
- Match number (small, gray)
- Two team rows — for each team (home/away):
  - If `locked or readonly`: renders a static `.bk-team` span, highlighted green if this team is the predicted winner.
  - If not locked and the team is known (not TBD): renders a `.bk-team-btn` button inside a form:
    ```html
    <form hx-post="/predictions/knockout/{match_id}"
          hx-trigger="click"
          hx-target="#knockout-bracket"
          hx-swap="outerHTML">
      <input type="hidden" name="winner_code" value="{team.code}">
      <button type="submit" class="bk-team-btn {winner_class}">{team.flag} {team.name}</button>
    </form>
    ```
    Clicking picks that team as the winner; HTMX posts and replaces the bracket.
  - If the team is TBD: renders a `.bk-team.tbd` span showing "TBD".

---

### `templates/leaderboard.html` — Leaderboard

Shows a ranked table of all users. Uses HTMX auto-refresh:
```html
<div hx-get="/leaderboard"
     hx-trigger="every 60s"
     hx-select="#leaderboard-table"
     hx-swap="outerHTML">
  <table id="leaderboard-table">...</table>
</div>
```

Columns: Rank (medal emoji for top 3), Username (clickable link to their predictions, only when locked), Total Score, per-round score breakdown (GS / R32 / R16 / QF / SF / F). The logged-in user's row is highlighted.

---

### `templates/admin/results.html` — Admin Panel

**Backup/Restore card**: Download backup (GET link) and upload restore (file upload form).

**Group stage section**: One form per match. Inputs for `home_score` and `away_score`, a "Completed" checkbox. On submit, posts to `/admin/results/group/{match_id}`.

**Knockout section**: One form per knockout match. A dropdown to select the winning team from the two known participants (or "TBD" if not yet resolved). A "Completed" checkbox. On submit, posts to `/admin/results/knockout/{match_id}`.

---

## Static Assets

### `static/css/style.css`

Custom styles on top of Bootstrap:

- `.score-input` — 52px wide number inputs for group score entry
- `.team-flag-name` — truncates long team names with ellipsis
- `.standings-table` — tighter padding/font-size for the 4-column standings table
- `.bracket-layout` — `position: relative; min-width: 970px` — the bracket container
- `.bk-card` — `position: absolute; width: 170px; height: 80px` — individual match cards
- `.bk-team`, `.bk-team-btn` — team name rows within cards; `.winner` variant is green
- `.bk-svg` — `position: absolute; top: 0` — SVG connector overlays
- `.bracket-scroll` — `overflow-x: auto` — makes bracket scrollable on small screens
- `.match-row` — group match row styling with bottom border
- Navbar and body background color overrides

---

## Key Patterns and Design Decisions

### HTMX Partial Updates

The app avoids full page reloads wherever possible. Three main patterns:

1. **Group score save → group card swap + bracket refresh**: Posting a score returns the updated group card HTML. The `HX-Trigger: refreshKnockout` response header then fires a separate request to reload the knockout bracket.

2. **Knockout winner pick → bracket swap**: Posting a winner returns the entire updated knockout bracket HTML.

3. **Leaderboard auto-poll**: Uses `hx-select` to extract just the table from the full leaderboard page response, avoiding a full page replacement.

### Prediction Locking

`settings.is_locked()` is a pure function checking the current UTC time. It's called at the start of every POST handler and every view-other-user GET handler. There's no stored "locked" flag — the lock is purely time-based and requires no admin action.

### Knockout Invalidation on Group Stage Changes

When any group stage score is updated, all knockout predictions for that user are deleted in the same transaction as the group score save. This prevents a consistency problem: if a user picked Germany to win a R32 match but their group stage update now has Germany finishing 3rd (not qualifying for that slot), the stored winner pick would reference an impossible bracket state. Wiping knockout picks forces the user to re-select winners based on the new bracket.

### Pre-Lock Privacy

Routes `GET /predictions/{username}` and `GET /predictions/{username}/knockout` both check `is_locked()` and return 403 if not yet locked. This ensures no user can spy on competitors' predictions before the tournament begins. After lock, the user-switcher dropdown in `predictions/index.html` becomes visible, enabling everyone to browse the full bracket of any participant.

### Bracket Computation is Always Fresh

`compute_user_bracket` is called on every request — it's never cached. This guarantees the bracket is always consistent with the latest predictions in the database. Given ~30 users and SQLite/PostgreSQL with indexed queries, this is fast enough (sub-millisecond bracket computation for any user).

### No JavaScript Framework

All interactivity is achieved through HTMX attributes on HTML elements. The only custom JavaScript on the page is the single `onchange` handler on the user-switcher dropdown (`onchange="window.location='/predictions/'+this.value"`). Everything else — form submission, DOM swapping, tab loading, leaderboard polling — is driven by HTMX declarative attributes.

### Backup/Restore Design

The backup ZIP approach was chosen over SQL dump because it's database-agnostic. The CSV format works whether the source is SQLite and the destination is PostgreSQL. The restore is a full replace (delete-all + re-insert), not a merge, to avoid conflict on unique constraints. This means restores are destructive — intended as a one-time migration tool or disaster recovery, not a merge mechanism.
