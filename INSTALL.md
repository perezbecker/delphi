# Delphi — Installation & Deployment Guide

This guide covers:
1. [Local development setup](#1-local-development-setup)
2. [Azure PostgreSQL setup](#2-azure-postgresql-setup)
3. [Azure App Service deployment](#3-azure-app-service-deployment)
4. [First-run tasks](#4-first-run-tasks)
5. [Updating the app](#5-updating-the-app)
6. [Database backup & restore](#6-database-backup--restore)

---

## Prerequisites

Install these on your machine before starting:

| Tool | Install |
|---|---|
| Python 3.12+ | https://python.org/downloads |
| Git | https://git-scm.com |
| Azure CLI | `brew install azure-cli` or https://docs.microsoft.com/en-us/cli/azure/install-azure-cli |
| PostgreSQL client (prod only) | `brew install postgresql` or https://www.postgresql.org/download/ |

Verify:
```bash
python3 --version   # should show 3.12+
git --version
az --version
```

---

## 1. Local Development Setup

### 1.1 Clone & create virtual environment

```bash
git clone <your-repo-url> delphi
cd delphi

python3 -m venv .venv
source .venv/bin/activate       # macOS/Linux
# OR on Windows:
# .venv\Scripts\activate
```

### 1.2 Install dependencies

```bash
pip install -r requirements.txt
```

### 1.3 Configure environment

```bash
cp .env.example .env
```

Open `.env` and set:

```env
DATABASE_URL=sqlite:///./delphi.db    # SQLite for local dev
SECRET_KEY=<generate a random key>
INVITE_CODE=<a secret word your friends will use to register>
TOURNAMENT_START=2026-06-11T18:00:00Z
ADMIN_USERNAME=<your username>
```

Generate a strong `SECRET_KEY`:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 1.4 Run database migrations

```bash
alembic upgrade head
```

This creates `delphi.db` (SQLite file) with all tables.

### 1.5 Start the development server

```bash
uvicorn app.main:app --reload
```

Open http://localhost:8000 in your browser.

**What to do next:**
1. Go to http://localhost:8000/register
2. Enter your username, a password, and the `INVITE_CODE` you set
3. The first registered user is automatically made admin
4. Share the `INVITE_CODE` with friends so they can register

---

## 2. Azure PostgreSQL Setup

We use **Azure Database for PostgreSQL – Flexible Server** (Burstable B1ms, ~$12/month).

### 2.1 Login to Azure

```bash
az login
```

### 2.2 Set variables (edit these)

```bash
RESOURCE_GROUP="delphi-rg"
LOCATION="eastus"                  # or "westeurope", etc.
PG_SERVER="delphi-db-server"       # must be globally unique
PG_ADMIN_USER="delphiadmin"
PG_ADMIN_PASSWORD="<strong-password>"   # min 8 chars, upper+lower+digit
PG_DB_NAME="delphi"
APP_NAME="delphi-wc2026"           # must be globally unique
APP_PLAN="delphi-plan"
```

### 2.3 Create resource group

```bash
az group create --name $RESOURCE_GROUP --location $LOCATION
```

### 2.4 Create PostgreSQL Flexible Server

```bash
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $PG_SERVER \
  --location $LOCATION \
  --admin-user $PG_ADMIN_USER \
  --admin-password "$PG_ADMIN_PASSWORD" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 16 \
  --yes
```

This takes ~3 minutes.

### 2.5 Create the database

```bash
az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $PG_SERVER \
  --database-name $PG_DB_NAME
```

### 2.6 Allow Azure App Service to connect

```bash
az postgres flexible-server firewall-rule create \
  --resource-group $RESOURCE_GROUP \
  --name $PG_SERVER \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0
```

### 2.7 Get your connection string

```bash
az postgres flexible-server show-connection-string \
  --server-name $PG_SERVER \
  --admin-user $PG_ADMIN_USER \
  --admin-password "$PG_ADMIN_PASSWORD" \
  --database-name $PG_DB_NAME \
  --query connectionStrings.psycopg2 \
  --output tsv
```

Copy this — it looks like:
```
host=delphi-db-server.postgres.database.azure.com port=5432 dbname=delphi user=delphiadmin password=... sslmode=require
```

Convert it to SQLAlchemy URL format:
```
postgresql://delphiadmin:<password>@delphi-db-server.postgres.database.azure.com:5432/delphi?sslmode=require
```

---

## 3. Azure App Service Deployment

### 3.1 Create App Service Plan (B1 — ~$13/month)

```bash
az appservice plan create \
  --name $APP_PLAN \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku B1 \
  --is-linux
```

### 3.2 Create the Web App

```bash
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan $APP_PLAN \
  --name $APP_NAME \
  --runtime "PYTHON:3.12" \
  --deployment-source-url ""
```

### 3.3 Configure environment variables

Run each of these, replacing the values with your own:

```bash
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --settings \
    DATABASE_URL="postgresql://delphiadmin:<password>@<server>.postgres.database.azure.com:5432/delphi?sslmode=require" \
    SECRET_KEY="<your-32-byte-hex-key>" \
    INVITE_CODE="<your-invite-code>" \
    TOURNAMENT_START="2026-06-11T18:00:00Z" \
    ADMIN_USERNAME="<your-username>" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true"
```

### 3.4 Set the startup command

```bash
az webapp config set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --startup-file "gunicorn -w 2 -k uvicorn.workers.UvicornWorker app.main:app"
```

### 3.5 Deploy the app

#### Option A — Git deploy (simplest)

```bash
# Configure Azure as a git remote
az webapp deployment source config-local-git \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP

# Get the remote URL (copy the "url" field from the output)
az webapp deployment list-publishing-credentials \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query scmUri --output tsv

# Add the remote and push
git remote add azure <url-from-above>
git push azure main
```

#### Option B — GitHub Actions (recommended for ongoing use)

1. Push your code to a GitHub repository.
2. In the Azure Portal, go to your App Service → Deployment Center.
3. Select **GitHub** as the source, authorise, and select your repo and branch.
4. Azure will auto-generate a `.github/workflows/main_delphi.yml` file.
5. Every push to `main` will auto-deploy.

### 3.6 Run database migrations on Azure

After deployment, run migrations once:

```bash
az webapp ssh --resource-group $RESOURCE_GROUP --name $APP_NAME

# Inside the SSH session:
cd /home/site/wwwroot
source antenv/bin/activate
alembic upgrade head
exit
```

Or use the Kudu console: https://<APP_NAME>.scm.azurewebsites.net/DebugConsole

### 3.7 Verify

```bash
az webapp browse --name $APP_NAME --resource-group $RESOURCE_GROUP
```

This opens your app at `https://<APP_NAME>.azurewebsites.net`.

---

## 4. First-Run Tasks

Once the app is running (locally or on Azure):

1. **Register your account** at `/register` — use the `INVITE_CODE` you set.
   - If `ADMIN_USERNAME` matches your username, you are automatically admin.
   - Otherwise, the first registered user is admin.

2. **Verify admin access** — the navbar should show an "Admin" link.

3. **Share the invite code** with friends so they can register at `/register`.

4. **Before the tournament starts** — friends predict all matches at `/predictions`.

5. **During the tournament** — enter actual results at `/admin/results`.
   - For group stage: enter the score (e.g. 2–1) and tick "Done".
   - For knockout matches: select the winner and tick "Done".
   - Scores on the leaderboard update immediately.

6. **After tournament kickoff** — all predictions are automatically locked. The
   `TOURNAMENT_START` env var controls this (UTC datetime). Adjust if needed.

---

## 5. Updating the App

### Local

```bash
git pull
source .venv/bin/activate
pip install -r requirements.txt   # pick up new deps if any
alembic upgrade head               # run any new migrations
uvicorn app.main:app --reload
```

### Azure (Git deploy)

```bash
git add -A && git commit -m "update"
git push azure main
```

After deploy, run migrations if there are new ones:

```bash
az webapp ssh --resource-group $RESOURCE_GROUP --name $APP_NAME
cd /home/site/wwwroot && source antenv/bin/activate && alembic upgrade head
```

### Azure (GitHub Actions)

Just push to `main` — Actions handles the deploy. SSH in to run migrations.

---

## 6. Database Backup & Restore

### Backup (PostgreSQL on Azure)

```bash
# Install pg_dump if not present: brew install postgresql
pg_dump \
  "postgresql://delphiadmin:<password>@<server>.postgres.database.azure.com:5432/delphi?sslmode=require" \
  --no-password \
  -Fc \
  -f delphi_backup_$(date +%Y%m%d).dump
```

### Restore

```bash
pg_restore \
  --clean \
  --no-acl \
  --no-owner \
  -d "postgresql://delphiadmin:<password>@<server>.postgres.database.azure.com:5432/delphi?sslmode=require" \
  delphi_backup_YYYYMMDD.dump
```

### SQLite backup (local dev)

```bash
cp delphi.db delphi_backup_$(date +%Y%m%d).db
```

---

## Cost Estimate (Azure)

| Resource | SKU | $/month |
|---|---|---|
| App Service Plan | B1 Linux | ~$13 |
| PostgreSQL Flexible Server | Burstable B1ms | ~$12 |
| **Total** | | **~$25/month** |

To minimise cost: stop the PostgreSQL server when not in use (before/after the tournament).

```bash
# Stop (saves ~$12/mo when idle)
az postgres flexible-server stop --resource-group $RESOURCE_GROUP --name $PG_SERVER

# Start again
az postgres flexible-server start --resource-group $RESOURCE_GROUP --name $PG_SERVER
```

---

## Troubleshooting

**App shows 500 error after deploy**
- Check logs: `az webapp log tail --name $APP_NAME --resource-group $RESOURCE_GROUP`
- Most common cause: missing env vars or migrations not run.

**"Table not found" error**
- Run `alembic upgrade head` (see §3.6).

**Predictions not locked even though tournament started**
- Verify `TOURNAMENT_START` is set correctly in UTC: `2026-06-11T18:00:00Z`
- Check via Azure portal → App Service → Configuration → Application settings.

**Friends can't register**
- They need the exact `INVITE_CODE` you set (case-sensitive).

**Forgot admin password**
- SSH into the app, open a Python shell:
  ```python
  from app.database import SessionLocal
  from app.models import User
  from app.auth import hash_password
  db = SessionLocal()
  u = db.query(User).filter(User.username == "yourusername").first()
  u.password_hash = hash_password("newpassword")
  db.commit()
  ```
