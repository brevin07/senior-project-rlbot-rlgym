# RocketCoach

RocketCoach is a Rocket League coaching platform that combines replay parsing, mechanic grading, replay-backed coaching feedback, progress tracking, and RLBot/RLDojo-based training scenarios.

## License

RocketCoach is proprietary software. The source code is visible for evaluation, security review, feedback, and project review only. Copying, modifying, redistributing, hosting, or using this code in another project requires prior written permission from the copyright holder. See [LICENSE](LICENSE).

The product goal is to help a player move through one continuous loop:

1. Create an account and verify it with AWS Cognito.
2. Add the Rocket League usernames the replay parser should track, along with rank and platform.
3. Review past replays and see event-by-event coaching plus mechanic grades.
4. Track improvement over time.
5. Practice the weakest mechanics against targeted bots and scenarios.

This repository already includes that loop end to end for replay review, progress tracking, installer delivery, and RLBot-backed training launch. Some subsystems are still in migration, but the packaged dashboard now exposes the main user workflow directly.

## Public Hosting

The production domain is intended to be:

```txt
https://rocketcoach.app
```

RocketCoach is easiest to host with the dashboard gateway as the single public service. The React app uses same-origin `/api/...` calls, so `rocketcoach.app` can serve both the website and replay API through the gateway. On the hosted server, set:

```powershell
ROCKETCOACH_PUBLIC_BASE_URL=https://rocketcoach.app
```

Then point DNS for `rocketcoach.app` at the server or hosting provider and route HTTPS traffic to the gateway on port `8888`. A reverse proxy should preserve the public `Host` header and send `X-Forwarded-Proto=https`; the gateway forwards those headers to the replay service so local companion callbacks and session cookies use the real public domain.

A Caddy reverse-proxy example lives at `deploy/Caddyfile.rocketcoach.app`.

## User Flow

### 1. Account creation and verification

The React frontend includes Cognito-backed sign-up, sign-in, email verification, and resend-code flows. A player creates an account, verifies their email, then signs in to access the dashboard.

### 2. Player profile setup

After authentication, the player configures the identity used for replay analysis:

- in-game username
- alternate usernames / aliases
- rank tier
- platform

This gives the replay pipeline enough information to match parsed replay data back to the correct player.

### 3. Replay review and coaching

Once the profile is configured, the player enters the dashboard and uploads or opens replays. The replay analysis flow shows:

- replay history
- a graded breakdown of mechanics
- event-by-event feedback
- event-by-event coaching explanations that continue generating in the background if needed

### 4. Improvement tracking

RocketCoach is intended to turn replay analysis into trend data over time, so the player can see whether their mechanics are improving across multiple replays instead of only reviewing a single match in isolation.

### 5. Training against bots

The player can select a replay-backed mechanic recommendation and launch a focused practice session against a mapped RLBot bot and RLDojo playlist tailored to that mechanic and difficulty tier.

## Dashboard Tabs

The current packaged dashboard uses these primary tabs:

- `Home`
- `Replay`
- `Improvement`
- `Training`
- `Installer`

### Home

- shows the latest replay, upload prompt, quick progress trend, and short replay-backed recommendations
- acts as the main landing page after sign-in

### Replay

- combines the replay library and replay studio into one surface
- supports upload, replay selection, 3D playback, mechanic grading, and coaching review
- no longer blocks opening a replay just because priority coaching text is still generating

### Improvement

- shows replay-derived progress trends and mechanic history
- keeps the long-view tracking experience separate from the per-replay studio

### Training

- ranks recommended mechanics to practice
- lets the player choose difficulty and drill mode, then click `Train Against Bot`
- runs RLBot preflight checks directly in the UI, including `Verify Dependencies` and `Re-run Checks`
- verifies both shared dependencies and mapped bot readiness before launch
- launches RLDojo playlists through the dedicated Windows local companion / training bridge

### Installer

- exposes the downloadable Windows installer from the dashboard
- gives new users a direct path to install RLBot GUI, RLBotPack, playlist assets, and Python dependencies

## Current Implementation Snapshot

The repository already contains these working or partially working pieces:

- Cognito sign-up, sign-in, email verification, and session restore in the React frontend
- Profile setup for username, aliases, rank, and platform
- Replay upload / replay library flow
- Unified replay tab with 3D playback and studio review
- Mechanic grading from replay analysis
- Event coaching that can continue generating after the replay is already open
- Progress charting from replay-derived scores
- RLBot/RLDojo training launch through the packaged dashboard
- Deep RLBot preflight that verifies launcher readiness, shared dependencies, and per-bot import readiness
- Installer download flow in both `Training` and `Installer`

## Product Status Notes

This README reflects the current packaged app behavior.

- The authentication and profile setup flow already matches the intended user journey closely.
- Replay analysis, replay library, and studio playback now live under the same `Replay` tab.
- Improvement tracking exists both in `Home` summaries and in the dedicated `Improvement` tab.
- Training recommendations are replay-backed and can launch mapped RLBot/RLDojo drills from the dashboard.
- RLBot launches depend on the Windows training bridge and host-side dependency verification, not on the replay container guessing host installs.

## Quick Start

### Prerequisites

- Windows PowerShell
- Python 3.11 or 3.12
- Node.js and npm for the React frontend
- Rocket League installed for live analysis and training workflows

### 1. Bootstrap Python dependencies

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
```

This creates the `venv` runtime virtual environment and installs the base Python dependencies.

### Optional: build a Windows bootstrap installer `.exe`

If you want a user-run installer that prepares RLBot GUI, a local RLBotPack copy, and this repo's Python dependencies, build the standalone installer with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_rlbot_installer.ps1
```

This produces `dist/RLBotStackInstaller.exe`.

Installer behavior:

- downloads and installs the RLBot GUI MSI from the configured release URL
- downloads the `RLBotPack` repository snapshot as a fallback to the GUI's `Download Bot Pack` action
- creates the repo `venv` and installs `requirements/base.txt`
- installs common bot-related extras such as `stable-baselines3==1.7.0` and `pygame`
- attempts to install discovered bot-pack `requirements*.txt` files into the repo `venv`

Current limitation:

- RLBot GUI still owns its own bot-launch behavior, so some bots may still trigger first-run dependency setup inside RLBot depending on how that bot is packaged.

If you only want to install the RocketCoach RLDojo playlists on a user's machine, build the smaller playlist installer with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/build_rldojo_playlists_installer.ps1
```

This produces `dist/RLDojoPlaylistsInstaller.exe`, which writes the generated RocketCoach `RC ...` playlists into the user's `AppData\Roaming\RLBot\Dojo\Playlists` folder.

### 2. Build or run the React frontend for local development

```powershell
cd frontend\dashboard
npm install
npm run build
cd ..\..
```

Use `npm run dev` during frontend development if you want the Vite development server instead of a production build.

### 3. Start the packaged RLCoach app stack

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_rlcoach_app.ps1
```

This Docker-first launcher:

- validates the required `.env` values
- reuses previously built Docker images when the relevant inputs have not changed
- rebuilds only the replay or gateway image whose inputs changed, unless `-RebuildContainers` is passed
- starts the self-contained replay and gateway containers without repo bind mounts
- bind-mounts the shared packaged app data directory into the replay container so the server `app.db` is stored on the host
- is intended to be the canonical app entrypoint when using the ngrok-served dashboard
- waits for the gateway health check, then starts ngrok for the dashboard surface

Default local gateway URL:

- `http://127.0.0.1:8888`

Default packaged app data path:

- `artifacts\data\app.db`

If you want the ngrok-served app to use a different host storage location for the shared backend database and replay data, set `RLBOT_APP_DATA_DIR` in `.env` before startup.

For a full reset of the packaged stack, add `-ResetCompose`. For a forced rebuild, add `-RebuildContainers`.

### 4. Start the gateway and replay services for local non-Docker development

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_gateway.ps1
```

This local wrapper expects the `venv` environment from `scripts/bootstrap.ps1` and fronts the dashboard experience without Docker.

For the separate developer dashboard launcher that opens replay and gateway windows for you, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_dev_dashboard.ps1
```

### 5. Optional: launch live analysis or the dedicated training bridge

```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

For RLBot/RLDojo training from the dashboard, start the host training bridge with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_training_bridge.ps1
```

The Training tab will verify:

- `Dependencies installed`
- `Training launcher running`
- per-bot readiness for every mapped training bot

If the cached training preflight is stale, the UI refreshes it before launching a drill. Users can also trigger the same host-side verification with `Re-run Checks`.

For end users, the intended flow is the website `Verify Dependencies` button. The Windows installer now registers a `rocketcoach://` protocol handler so the dashboard can ask the local RocketCoach companion to start in the background and then poll for readiness.

### 6. Optional: run replay extraction directly

```powershell
powershell -ExecutionPolicy Bypass -File scripts/replay_extract.ps1
```

## Cognito Configuration

The React login flow uses AWS Cognito for account creation and verification, then exchanges the Cognito ID token with the backend.

Frontend environment variables:

- `VITE_COGNITO_AUTHORITY`
- `VITE_COGNITO_USER_POOL_ID`
- `VITE_COGNITO_CLIENT_ID`
- `VITE_COGNITO_SCOPE`

Backend environment variables:

- `COGNITO_ISSUER`
- `COGNITO_CLIENT_ID`

If you are deploying with Docker or running the hosted-style stack, copy `.env.example` to `.env` and fill in the required Cognito values there.

## Key Scripts

These are the main entry points still used in the repo:

- `scripts/bootstrap.ps1` - create the local Python environment for non-Docker workflows and install dependencies
- `scripts/run_gateway.ps1` - start the gateway plus replay services
- `scripts/launch_live_analysis.ps1` - launch live analysis with helper behavior
- `scripts/replay_extract.ps1` - extract replay data from a `.replay` file
- `scripts/replay_dashboard.ps1` - run the replay dashboard service
- `scripts/train.ps1` - run the training entrypoint
- `scripts/start_dev_dashboard.ps1` - one-step developer dashboard + gateway launcher
- `scripts/start_rlcoach_app.ps1` - packaged RLCoach launcher; uses self-contained Docker images, smart image reuse, gateway health checks, and ngrok startup by default
- `scripts/launch_training_bridge.ps1` - start the Windows host training bridge used by RLBot/RLDojo bot drills from the dashboard
- `scripts/prune_accounts.ps1` - remove local accounts, with optional Cognito cleanup

## Deployment Notes

Docker-based deployment is supported for the replay and gateway services.

Relevant files:

- `docker-compose.deploy.yml`
- `docker-compose.rlcoach-app.yml`
- `.github/workflows/docker-images.yml`
- `Dockerfile.replay`
- `Dockerfile.gateway`

The deployment flow publishes Docker images for the replay and gateway services, then runs them through the deploy compose file.

For the packaged ngrok launcher, account/profile data and replay session records are read from the shared backend database mounted at `RLBOT_APP_DATA_DIR` on the host. If all users access the same hosted app instance, they will see the same server-backed data across devices after signing in.

## Repository Layout

```text
.
|-- artifacts/               # External artifact pointers and generated outputs
|-- configs/                 # Config stubs
|-- data/                    # Lightweight tracked data only
|-- docs/                    # Architecture and workflow notes
|-- frontend/                # React dashboard frontend
|-- scripts/                 # PowerShell workflow wrappers
|-- src/                     # Migration scaffold
|-- rocketcoach/             # Replay, live analysis, gateway, and persistence code
`-- rlbot_training/          # RLBot / training runtime code
```

## Artifact Policy

Do not commit large generated artifacts such as:

- model binaries and checkpoints
- replay dumps and large JSON / CSV exports
- generated plots and logs
- local tool binaries and bundles

Track external artifact metadata under `artifacts/pointers/` when needed.
