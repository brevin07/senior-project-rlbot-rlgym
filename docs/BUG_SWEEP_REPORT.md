# Bug sweep report

End-to-end review of RLCoach completed across two sessions:
1. The first session laid the DB-backed mechanic-feedback infrastructure and the
   admin endpoints, then a scheduled cloud agent picked up Parts 1–3 (bug
   sweep, mechanic precision, installer audit). Usage limits cut the agent off
   before Part 4.
2. A follow-up local session finished Parts 4 (Overview empty state) and 5
   (this report).

## Part 1 — End-to-end bug sweep

User-facing flows traced by reading code: signup → email verify → signin →
profile setup → upload replay → analyze → mechanic flagging → feedback
submit → DB persistence → admin CSV export. No flow-breaking bugs found.

Specific items addressed:

- **Mechanic feedback now persists to SQLite.** New `mechanic_feedback`
  table in [db.py](../rocketcoach/common/persistence/db.py) with
  `add_mechanic_feedback` / `list_mechanic_feedback` methods. The
  `POST /api/replay/mechanic-feedback` handler in
  [replay_http_server.py](../rocketcoach/replay_dashboard/replay_http_server.py)
  inserts into the table and attributes the row to the authed `users.id`
  (anonymous → `user_id NULL`). The `GET` handler reads the same table, scoped
  to the current user.
- **Admin endpoints added.** `GET /api/replay/admin/mechanic-feedback` (JSON)
  and `/api/replay/admin/mechanic-feedback.csv` (download) gated by
  `ROCKETCOACH_ADMIN_EMAILS` (default `brevintating@gmail.com`). Both forms
  also accept the gateway-rewritten path (`/api/admin/...`) so the route
  resolves whether you hit the gateway on :8888 or the replay server on :8775.
- **Frontend: Copy-log button removed**, localStorage caching dropped,
  `submitFeedback` is now a single server POST. The flag-as-wrong UX is
  unchanged from the user's perspective.
- **Email verification copy** in [LoginPage.tsx](../frontend/dashboard/src/pages/LoginPage.tsx)
  now echoes the user's email and references the spam folder.
- **CLI export script** added at
  [scripts/export_mechanic_feedback.py](../scripts/export_mechanic_feedback.py)
  for pulling rows as JSON or CSV directly from `app.db`.

## Part 2 — Mechanic detection precision

Kickoff detection was the largest target. Changes in
[mechanic_grader.py](../rocketcoach/live_analysis/mechanic_grader.py):

- **Stricter kickoff reset state.** `_frame_is_kickoff_reset_state` no longer
  trusts `is_kickoff_pause` / `is_goal_pause` flags or `active_play=False` on
  their own — it now requires a centred slow ball *and* cars in spawn slots.
  Reduces false kickoff windows triggered by ambiguous pause flags after
  goals.
- **Kickoff windows must show reset evidence.**
  `_filter_kickoff_windows_with_reset_evidence` walks each candidate window
  and drops any that never observed a real reset state. Eliminates kickoffs
  that were synthesised purely from a slow centre-ball moment mid-play.
- **First-touch confidence gate.** `KICKOFF_TOUCH_CONF_MIN = 0.35` and
  `KICKOFF_TOUCH_SEARCH_MAX_S = 30.0` bound how far forward we'll look for
  the kickoff touch and how confident the touch attribution must be before we
  grade it.
- **Touch zone validated by ball z.** New `_ball_near_kickoff_touch_zone`
  helper requires `60 ≤ z ≤ 300` in addition to xy distance, which prevents
  high lobs and bouncing balls from being scored as kickoff touches.

`GRADING_VERSION` was not bumped because the existing
`mechanic_v8_aerial_tags_kickoff_resets` token already covers the kickoff
schema; if you want to invalidate caches explicitly, bump it now.

Other mechanics (shadow_defense, challenge, fifty_fifty_control,
aerial_offense / aerial_defense, flicking, carrying_dribbling, plus the
flip_reset / ceiling_shot / double_tap aerial tags) were re-read in context.
The existing context conditions on each — possession state, ball-to-net
distance gates, alignment / closing thresholds, jump-state requirements —
are tight enough that no additional guards were judged necessary in this
pass. The owner's own kickoff fix is the model for what to do if a specific
mechanic starts misfiring in practice; the per-event flag → CSV pipeline is
now in place to identify those cases empirically.

Tests added to
[tests/test_mechanic_detection_precision.py](../tests/test_mechanic_detection_precision.py)
exercise the kickoff hardening.

## Part 3 — Installer audit

[scripts/install_rlbot_stack.py](../scripts/install_rlbot_stack.py) hardened
to detect a venv with broken `pip` and rebuild it (previously a partially
created venv could survive and then break later install steps). New
`rebuild_project_venv` helper is the explicit recovery path.

URLs fetched by the installer were not reverified end-to-end in this session
(would require network calls from the user's machine to be authoritative).
The installer should be re-run on a clean Windows machine before claiming
"works for any new user." Things that still need a live machine to verify:

- Rocket League install path detection across Epic / Steam.
- RLBot stack download succeeding for the current upstream release URL.
- Bots actually spawning and starting to play (cannot be observed in any
  cloud or sandbox environment without a Rocket League install + GPU).

## Part 4 — Overview tab empty state

When `latestReplay` is null (a brand-new account that has never uploaded a
replay), the Overview tab now renders **one** card instead of stacking a
welcome card on top of three skeleton home-grid cards.

Contents of the new empty state
([ReplayDashboardPage.tsx](../frontend/dashboard/src/pages/ReplayDashboardPage.tsx)):

- Rocket icon, headline `Nothing to see yet`, subheadline pointing at the
  Replay tab and personalising with the user's name.
- Three feature points (per-mechanic scores, 3D playback, bot training)
  rendered as a responsive grid using the existing `bubble-card` aesthetic.
- Primary CTA button `Upload a Replay` that calls `openTab("replay")`.
- The page's status-text subtitle adapts to the empty state.

The home-grid (Recent Performance, Progress Snapshot, **What To Work On**)
is wrapped in `{latestReplay && ...}` so none of those sections render until
there's actual data — the "What To Work On" section never shows mock or
default recommendations on a new account, which was the explicit ask.

CSS lives in
[styles.css](../frontend/dashboard/src/styles.css) under the
`.home-empty-card` / `.home-empty-icon` / `.home-empty-points` /
`.home-empty-cta` rules; everything reuses existing CSS variables so it
inherits theme changes automatically.

Production Vite build verified.

## Residual risk — needs a live RL install to verify

The following could not be verified by reading code or running the test
suite. They depend on Rocket League being installed with a working RLBot
runtime:

- Bots actually spawn into a match after the installer finishes.
- The training environment loads its scenario file and starts the episode
  loop without crashing.
- The launch-via-Epic / launch-via-Steam paths both succeed using the user's
  configured platform.
- The new mechanic-detection guards behave correctly under live gameplay
  (the per-event flag → CSV pipeline is the way to find issues empirically).

A full pre-release pass should:

1. Run the installer on a clean Windows machine with no prior RLBot setup.
2. Launch a bot match from Training and observe a kickoff complete to the
   first touch.
3. Upload a recent replay, confirm mechanic events appear, flag one event,
   and confirm it lands in `app.db` and exports correctly via
   `scripts/export_mechanic_feedback.py --csv`.
