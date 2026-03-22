# RocketCoach

RocketCoach is a Rocket League coaching platform that combines replay parsing, mechanic grading, LLM-generated coaching feedback, progress tracking, and RLBot-based training scenarios.

The product goal is to help a player move through one continuous loop:

1. Create an account and verify it with AWS Cognito.
2. Add the Rocket League usernames the replay parser should track, along with rank and platform.
3. Review past replays and see event-by-event coaching plus mechanic grades.
4. Track improvement over time.
5. Practice the weakest mechanics against targeted bots and scenarios.

This repository already includes the foundations for that flow. Some parts are implemented end to end today, while others are still represented by placeholder UI or backend training infrastructure that has not yet been fully connected to the main dashboard experience.

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

Once the profile is configured, the player enters the dashboard and uploads or opens replays. The replay analysis flow is intended to show:

- replay history
- a graded breakdown of mechanics
- event-by-event feedback
- LLM explanations of what happened and how to improve

### 4. Improvement tracking

RocketCoach is intended to turn replay analysis into trend data over time, so the player can see whether their mechanics are improving across multiple replays instead of only reviewing a single match in isolation.

### 5. Training against bots

The end-state product experience is for the player to select a mechanic that needs work and launch a focused practice session against a hard-coded RL bot or scenario tailored to that skill.

## Dashboard Tabs

The desired product language is:

- `Replay`
- `Improvement`
- `Training`

The current implementation uses:

- `Home`
- `Replays`
- `Studio`
- `Improvement`

Here is how those concepts map today.

### Replay

Target behavior:

- View replay history
- Open past replays
- Review graded mechanics
- Read LLM explanations for specific events and mistakes

Current implementation:

- Replay library lives in `Replays`
- Detailed replay review lives in `Studio`
- Mechanic grades and coaching explanations are already available in the studio experience

### Improvement

Target behavior:

- Show a graph of mechanic score changes over time based on replay analysis

Current implementation:

- Progress charting exists today
- The graph currently appears in `Home`, not in `Improvement`

### Training

Target behavior:

- Rank mechanics by how urgently the player should practice them
- Show the replays or replay evidence behind each recommendation
- Let the player click `Train against a bot`
- Spawn a targeted training session against a hard-coded bot or scenario for that mechanic

Current implementation:

- The current `Improvement` tab contains placeholder `Top 3 Mechanics to Practice` cards
- RLBot scenario and spawning infrastructure exists in the repository
- The dashboard-level `Train against a bot` flow is not fully wired yet as a finished user-facing feature

## Current Implementation Snapshot

The repository already contains these working or partially working pieces:

- Cognito sign-up, sign-in, email verification, and session restore in the React frontend
- Profile setup for username, aliases, rank, and platform
- Replay upload / replay library flow
- Replay studio with 3D playback
- Mechanic grading from replay analysis
- LLM-backed event explanations and coaching feedback
- Progress charting from replay-derived scores
- RLBot live-analysis and scenario-loading infrastructure for training workflows

## Product Status Notes

This README reflects both the current system and the intended product direction.

- The authentication and profile setup flow already matches the intended user journey closely.
- Replay analysis is real today, but it is split across `Replays` and `Studio` instead of being presented as one unified `Replay` tab.
- Improvement tracking exists, but the graph is currently on `Home`.
- The current `Improvement` tab still uses placeholder recommendation cards.
- Bot/scenario training support exists in backend and RLBot infrastructure, but the polished dashboard action for launching skill-specific bot practice is still a planned integration step.

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

### 2. Build or run the React frontend

```powershell
cd frontend\dashboard
npm install
npm run build
cd ..\..
```

Use `npm run dev` during frontend development if you want the Vite development server instead of a production build.

### 3. Start the gateway and replay services

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_gateway.ps1
```

Default gateway URL:

- `http://127.0.0.1:8888`

This gateway fronts the dashboard experience and proxies the replay and live-analysis services behind a single entry point.

For the separate developer dashboard launcher that opens replay and gateway windows for you, use:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_dev_dashboard.ps1
```

### 4. Optional: launch live analysis or training-related flows

```powershell
powershell -ExecutionPolicy Bypass -File scripts/launch_live_analysis.ps1
```

### 5. Optional: run replay extraction directly

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

- `scripts/bootstrap.ps1` - create the Python environment and install dependencies
- `scripts/run_gateway.ps1` - start the gateway plus replay services
- `scripts/launch_live_analysis.ps1` - launch live analysis with helper behavior
- `scripts/replay_extract.ps1` - extract replay data from a `.replay` file
- `scripts/replay_dashboard.ps1` - run the replay dashboard service
- `scripts/train.ps1` - run the training entrypoint
- `scripts/start_dev_dashboard.ps1` - one-step developer dashboard + gateway launcher
- `scripts/start_rlcoach_app.ps1` - one-step startup flow for the broader app stack
- `scripts/prune_accounts.ps1` - remove local accounts, with optional Cognito cleanup

## Deployment Notes

Docker-based deployment is supported for the replay and gateway services.

Relevant files:

- `docker-compose.deploy.yml`
- `.github/workflows/docker-images.yml`
- `Dockerfile.replay`
- `Dockerfile.gateway`

The deployment flow publishes Docker images for the replay and gateway services, then runs them through the deploy compose file.

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
