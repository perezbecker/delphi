# Delphi — World Cup 2026 Prediction Pool

## What this is

A Python web app for a private World Cup 2026 prediction pool (~30 friends). Users register with an invite code, predict every match result before the tournament starts, and earn points as the real results come in. The organiser enters actual results via an admin panel. A live leaderboard is visible to all participants.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python 3.12) |
| Templating | Jinja2 + HTMX (no JS framework) |
| Styling | Bootstrap 5 + Unicode flag emojis |
| ORM | SQLAlchemy 2.0 (sync) |
| DB (dev) | SQLite (`delphi.db`) |
| DB (prod) | PostgreSQL (Azure Flexible Server) |
| Auth | bcrypt passwords + itsdangerous signed cookies |
| Server (dev) | Uvicorn with `--reload` |
| Server (prod) | Gunicorn + UvicornWorker |
| Migrations | Alembic |
| Hosting | Azure App Service B1 + Azure PostgreSQL B1ms |

---

## Project Structure

```
delphi/
├── app/
│   ├── main.py              # FastAPI app + lifespan startup
│   ├── config.py            # Pydantic-settings config (reads .env)
│   ├── database.py          # SQLAlchemy engine + SessionLocal + Base
│   ├── models.py            # User, Prediction, ActualResult ORM models
│   ├── auth.py              # Password hashing, session cookies, FastAPI deps
│   └── tournament/
│       ├── data.py          # All static WC2026 data (teams, groups, schedule, bracket)
│       ├── standings.py     # Group standings + FIFA tiebreaker logic
│       ├── bracket.py       # Per-user bracket computation + 3rd-place assignment
│       └── scoring.py       # Points calculation per user
│   └── routers/
│       ├── auth.py          # /login, /register, /logout
│       ├── predictions.py   # /predictions (HTMX group + knockout saves, view others)
│       ├── leaderboard.py   # /leaderboard
│       └── admin.py         # /admin/results (result entry)
├── templates/
│   ├── base.html            # Navbar, Bootstrap, HTMX CDN
│   ├── auth/login.html
│   ├── auth/register.html
│   ├── predictions/
│   │   ├── index.html       # Tabbed page: Group Stage | Knockout Bracket
│   │   └── partials/
│   │       ├── group_card.html          # HTMX score input form + live standings table
│   │       └── knockout_bracket.html    # HTMX knockout bracket (click to pick winner)
│   ├── leaderboard.html     # Live-updating score table (HTMX poll every 60s)
│   └── admin/results.html   # Score/winner entry forms for all matches
├── static/css/style.css
├── alembic/                 # Migrations (run: alembic upgrade head)
├── alembic.ini
├── requirements.txt
├── .env.example
└── INSTALL.md               # Full Azure deployment guide
```

---

## Configuration (`.env` / environment variables)

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///./delphi.db` |
| `SECRET_KEY` | 32-byte hex string for signing cookies | *(must set)* |
| `INVITE_CODE` | Shared secret friends need to register | `worldcup2026` |
| `TOURNAMENT_START` | UTC datetime when predictions lock | `2026-06-11T18:00:00Z` |
| `ADMIN_USERNAME` | Username to auto-promote to admin on startup | *(optional)* |

Generate a secret key: `python3 -c "import secrets; print(secrets.token_hex(32))"`

---

## Tournament Data (`app/tournament/data.py`)

### Groups — FIFA draw (December 5, 2025, Washington D.C.)

| Group | Teams |
|---|---|
| A | Mexico 🇲🇽, South Korea 🇰🇷, South Africa 🇿🇦, Czechia 🇨🇿 |
| B | Canada 🇨🇦, Switzerland 🇨🇭, Qatar 🇶🇦, Bosnia-Herz. 🇧🇦 |
| C | Brazil 🇧🇷, Morocco 🇲🇦, Haiti 🇭🇹, Scotland 🏴󠁧󠁢󠁳󠁣󠁴󠁿 |
| D | USA 🇺🇸, Paraguay 🇵🇾, Australia 🇦🇺, Türkiye 🇹🇷 |
| E | Germany 🇩🇪, Curaçao 🇨🇼, Ivory Coast 🇨🇮, Ecuador 🇪🇨 |
| F | Netherlands 🇳🇱, Japan 🇯🇵, Sweden 🇸🇪, Tunisia 🇹🇳 |
| G | Belgium 🇧🇪, Egypt 🇪🇬, Iran 🇮🇷, New Zealand 🇳🇿 |
| H | Spain 🇪🇸, Cape Verde 🇨🇻, Saudi Arabia 🇸🇦, Uruguay 🇺🇾 |
| I | France 🇫🇷, Senegal 🇸🇳, Iraq 🇮🇶, Norway 🇳🇴 |
| J | Argentina 🇦🇷, Algeria 🇩🇿, Austria 🇦🇹, Jordan 🇯🇴 |
| K | Portugal 🇵🇹, DR Congo 🇨🇩, Uzbekistan 🇺🇿, Colombia 🇨🇴 |
| L | England 🏴󠁧󠁢󠁥󠁮󠁧󠁿, Croatia 🇭🇷, Ghana 🇬🇭, Panama 🇵🇦 |

### Match ID scheme

- Group stage: `GS_{group}_{n}` — e.g. `GS_A_1` through `GS_A_6` (72 total)
- Round of 32: `R32_{match_num}` — matches 73–88
- Round of 16: `R16_{match_num}` — matches 89–96
- Quarterfinals: `QF_{match_num}` — matches 97–100
- Semifinals: `SF_{match_num}` — matches 101–102
- Final: `F_103`

### Round of 32 bracket (official FIFA structure)

```
M73:  RU_A   vs RU_B
M74:  W_E    vs 3rd(A/B/C/D/F)
M75:  W_F    vs RU_C
M76:  W_C    vs RU_F
M77:  W_I    vs 3rd(C/D/F/G/H)
M78:  RU_E   vs RU_I
M79:  W_A    vs 3rd(C/E/F/H/I)
M80:  W_L    vs 3rd(E/H/I/J/K)
M81:  W_D    vs 3rd(B/E/F/I/J)
M82:  W_G    vs 3rd(A/E/H/I/J)
M83:  RU_K   vs RU_L
M84:  W_H    vs RU_J
M85:  W_B    vs 3rd(E/F/G/I/J)
M86:  W_J    vs RU_H
M87:  W_K    vs 3rd(D/E/I/J/L)
M88:  RU_D   vs RU_G
```

R16: W(M74) vs W(M77), W(M73) vs W(M75), W(M76) vs W(M78), W(M79) vs W(M80), W(M83) vs W(M84), W(M81) vs W(M82), W(M86) vs W(M88), W(M85) vs W(M87)

No third-place playoff — excluded from all predictions and scoring.

---

## Database Models

### `User`
`id`, `username` (unique, max 50), `password_hash`, `is_admin` (bool), `created_at`

### `Prediction`
`id`, `user_id` (FK → User), `match_id` (str), `home_score` (int|null), `away_score` (int|null), `winner_code` (str|null)
- Group stage rows: `home_score` + `away_score` set; `winner_code` null
- Knockout rows: `winner_code` set (team code, e.g. `"MEX"`); scores null
- Unique constraint: `(user_id, match_id)`

### `ActualResult`
`match_id` (PK), `home_score`, `away_score`, `winner_code`, `completed` (bool)
- Group stage: `home_score` + `away_score` used for outcome; `winner_code` null
- Knockout: `winner_code` is the actual winner after ET/pens; scores unused

---

## Prediction Rules

### Group Stage
- Users predict **exact scores** (e.g. 2–1) for all 72 group matches.
- Winner/draw outcome is derived from the score: `sign(home - away)`.
- Points are awarded for correct **outcome** (W/D/L) only — not exact score.
- Predicted scores are used for FIFA tiebreaker calculations.

### Knockout Stage
- Users **click the team they predict will win** each knockout match.
- The bracket is dynamically pre-filled based on the user's group stage predictions.
- Points are awarded if the predicted winner matches the actual winner, regardless of whether the match went to extra time or penalties.

### Prediction Lock
- All predictions are locked at `TOURNAMENT_START` (UTC).
- After lock: all prediction pages become read-only; POST routes return 403.

---

## Scoring

| Round | Points (correct winner) |
|---|---|
| Group Stage (W/D/L outcome) | 1 |
| Round of 32 | 1 |
| Round of 16 | 2 |
| Quarterfinals | 4 |
| Semifinals | 8 |
| Final | 16 |

---

## Authentication

- Registration requires matching `INVITE_CODE` — prevents unwanted signups.
- The **first registered user** is automatically admin.
- `ADMIN_USERNAME` env var: any user with this username is promoted to admin on startup.
- Session: signed cookie (`itsdangerous.URLSafeTimedSerializer`), 30-day max age, httponly.
- Passwords: bcrypt with cost factor 12.

---

## Key Algorithms

### Group Standings (`standings.py`)
FIFA tiebreaker order:
1. Points (W=3, D=1, L=0)
2. Goal difference
3. Goals scored
4. Points in head-to-head matches among tied teams
5. GD in head-to-head matches
6. GF in head-to-head matches
7. FIFA ranking (lower = better) — used as final deterministic tiebreaker

### Best-3rd-Place Assignment (`bracket.py`)
1. Sort all 12 third-place teams by points → GD → GF → FIFA ranking.
2. Top 8 qualify. Record their 8 source groups.
3. Assign to R32 slots via backtracking: sort slots by most-constrained first (fewest eligible qualifying groups), then greedily assign best available team whose group is eligible.
4. Returns `{"3rd_M74": Team, "3rd_M77": Team, ...}`.

Note: FIFA Annex C of the tournament regulations contains a pre-computed table of 495 combinations (C(12,8)). The backtracking algorithm produces a valid consistent assignment but may differ from the exact FIFA table in some edge cases. The FIFA table can be added later as a `frozenset → dict` lookup for exact compliance.

### Per-User Bracket (`bracket.py: compute_user_bracket`)
1. Load all user predictions from DB.
2. Compute group standings for all 12 groups.
3. Build slot map: `W_A → team`, `RU_A → team`, `3rd_M74 → team`, etc.
4. Iterate knockout matches in order; resolve home/away from slot map + previous predicted winners.
5. Return `BracketState` with all match states and completion flag.

---

## HTMX Interaction Pattern

### Group score inputs
```
hx-post="/predictions/group/{match_id}"
hx-trigger="change"
hx-target="#group-{group}"
hx-swap="outerHTML"
```
Response returns the updated group card (standings + forms) and sets `HX-Trigger: refreshKnockout` header to trigger the knockout bracket to reload.

### Knockout winner buttons
```
hx-post="/predictions/knockout/{match_id}"
hx-trigger="click"
hx-target="#knockout-bracket"
hx-swap="outerHTML"
```
Response returns the full updated knockout bracket partial.

### Knockout bracket loading
The knockout bracket tab loads lazily on first click (`hx-trigger="click once"`) and also listens for `refreshKnockout` events from the body (fired after group score saves).

### Leaderboard auto-refresh
```
hx-get="/leaderboard"
hx-trigger="every 60s"
hx-select="#leaderboard-table"
hx-swap="outerHTML"
```

---

## Running Locally

```bash
# First time
cp .env.example .env        # edit values
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Then open http://localhost:8000, register at `/register` using the invite code.

---

## Admin Workflow

1. Navigate to `/admin/results` (admin navbar link).
2. **Group stage**: Enter home and away scores for each completed match; tick "Done"; Save.
3. **Knockout stage**: Select the winner from the dropdown; tick "Done"; Save.
4. Scores on the leaderboard update immediately after saving.

---

## Azure Deployment Summary

See `INSTALL.md` for full step-by-step Azure CLI commands. Summary:

1. Create resource group + Azure PostgreSQL Flexible Server (B1ms, ~$12/mo).
2. Create Azure App Service Plan (B1 Linux, ~$13/mo) + Web App (Python 3.12).
3. Set all env vars via `az webapp config appsettings set`.
4. Set startup command: `gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app`
5. Deploy via `git push azure main` or GitHub Actions.
6. SSH in and run `alembic upgrade head` once after first deploy.

Total cost: ~$25/month. Can stop the PostgreSQL server between tournaments to save ~$12/mo.

---

## Decisions & Rationale

| Decision | Reason |
|---|---|
| No exact-score points | Owner only wants to award correct outcome prediction |
| Exact scores collected anyway | Needed for FIFA group stage tiebreaker rules |
| HTMX not React/Vue | Python-friendly, no build step, sufficient for this scale |
| SQLite for dev | Zero-config local setup |
| Invite code (not email verification) | Simple, no email infrastructure needed |
| Backtracking for 3rd-place slots | FIFA Annex C table not publicly available; backtracking is correct and fast for 8 items |
| No 3rd-place playoff | Owner's decision — not predicted, not scored |
| First user = admin | Bootstrapping convenience; ADMIN_USERNAME env var also available |
