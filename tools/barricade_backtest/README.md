# Barricade Backtest Loop

Backtesting tools for Barricade Trainer.

Current project version: `2026.06.30.12`

The tool supports two execution modes:

- `api`: call a deployed `/api/analyze` endpoint.
- `local`: import the local Python engine in this workspace and run decisions
  without any network dependency.

## Quick Start

Run a short baseline-vs-candidate tournament:

```powershell
python tools\barricade_backtest\backtest_loop.py --games 10 --baseline-depth 2 --candidate-depth 3 --time 0.05
```

Play the local model against Barricade.gg's online Expert computer:

```powershell
python tools\barricade_external\play_barricade_gg.py `
  --difficulty expert `
  --local-side red `
  --local-engine hybrid `
  --out-dir backtest_runs\barricade-gg-expert-red
```

Collect 20 complete Barricade.gg Expert-vs-Expert games from your computer:

```powershell
.\run_expert_selfplay_20.cmd
```

You can pass extra options through the command file, for example:

```powershell
.\run_expert_selfplay_20.cmd --games 20 --pause-sec 1.5 --retries 2
```

Run the same tournament entirely inside the local repo:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_backtest\backtest_loop.py --mode local --games 10 --baseline-depth 2 --candidate-depth 3 --time 0.05
```

Analyze Expert-vs-Expert logs and rebuild high-confidence cache candidates:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_external\analyze_expert_selfplay.py `
  --input backtest_runs\expert-vs-expert-40-merged-20260630-110206 `
  --out-dir backtest_runs\expert-selfplay-analysis-latest
```

Version `2026.06.30.11` adds the Expert opening/state cache and the self-play
analysis script. Expert mode now tries the high-confidence cache first, then
falls back to Barricade.gg's API on misses.

Version `2026.06.30.12` adds `collect_expert_selfplay.py` plus
`run_expert_selfplay_20.cmd`, expands the self-play analyzer with opening tree,
trap wall, race decision, and optional hybrid ranking reports, and retunes
Hybrid with Expert-like opening walls and Expert wall priors.

Version `2026.06.30.10` changes Hybrid to resolve to the stable alpha-beta
policy by default after a 10-game Expert loss audit. MCTS remains available as
an explicit experimental model, and the opening book now avoids the repeated
red `hd4` self-delay and blue early back-rank walling patterns from that loss
set.

Compare the alpha-beta fallback backend against the production MCTS backend:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_backtest\backtest_loop.py `
  --mode local `
  --games 6 `
  --time 0.05 `
  --baseline-engine alpha-beta `
  --baseline-depth 3 `
  --candidate-engine mcts `
  --candidate-simulations 80 `
  --fail-on-errors
```

Use it as a CI gate:

```powershell
python tools\barricade_backtest\backtest_loop.py --games 50 --baseline-depth 2 --candidate-depth 3 --time 0.05 --fail-on-errors --fail-under-candidate-rate 55
```

Outputs are written to `backtest_runs/<timestamp>/`:

- `games.jsonl`: one JSON record per game.
- `summary.md`: win rate, errors, and replay notes.
- `summary.json`: machine-readable aggregate results.

Audit candidate losses after a run:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_backtest\audit_losses.py `
  backtest_runs\mcts-v3-candidate-12 `
  --engine-name candidate `
  --time 0.05 `
  --depth 3
```

The audit writes `loss_audit.json` and `loss_audit.md` with suspect decisions,
alpha-beta counterfactual moves, regret scores, distance deltas, phase labels,
and tactical reason tags.

## How It Works

In `api` mode, each game calls:

```text
POST https://barricade-trainer.onrender.com/api/analyze
```

with the current move history. The tool plays the returned `state.recommendation`
until a winner, error, repeated state, or max move limit.

In `local` mode, the tool builds the same state directly through
`barricade_trainer.py` and `barricade_web.state_payload()`, so the move selection
matches the local backend logic without waiting for Render.

For tournaments, the candidate and baseline swap colors every game so first-move
and side advantage do not dominate the result.

## Suggested Workflow

1. Run `--games 20` before editing the engine.
2. Save the generated report as the baseline.
3. Change backend search/evaluation logic.
4. Run `--games 100` against the same settings.
5. Only promote a change if candidate win rate improves and illegal/error games
   stay at zero.

Use `local` mode for fast iteration while editing the engine, and reserve `api`
mode for verifying that the deployed service still matches expected behavior.

## Recent Verification

The latest promoted project version is `2026.06.30.03`.

Version `2026.06.30.03` adds `tools/barricade_external/play_barricade_gg.py`,
which talks to Barricade.gg's public Socket.IO AI move flow and records external
Expert matches as reproducible local reports. Initial Expert probes showed
hybrid losing as red in 52 plies and as blue in 73 plies. The resulting engine
tuning adds next-turn wall-trap scoring to alpha-beta and MCTS priors so a move
that allows the opponent to add a severe wall detour is penalized before it is
played. A low-wall safety valve can also prioritize a defensive wall when it
reduces the opponent's next wall threat by at least two steps at acceptable
route cost.
- Verification: 47 unit tests passed; backend and tool `py_compile` passed;
  frontend JS syntax checks passed.
- External Expert repeat after initial tuning: local hybrid as red still lost,
  but survived 62 plies instead of the pre-tuning 52-ply loss.
- Local sanity: hybrid vs MCTS, 4 games, 50% / 50%, errors 0; hybrid vs
  alpha-beta depth 3, 2 games, hybrid 100%, errors 0.

Version `2026.06.30.02` aligns local backtests with the live API's root avoid
filters and improves hybrid routing for close-contact wall-trap openings.

- Local backtest mode now uses `web.root_avoid_actions(...)`, so reversal and
  repeat-state filters match live `/api/analyze`.
- Hybrid now routes early close pawn-contact positions with many walls to
  alpha-beta. The reported strong-computer loss reproduced as current hybrid
  matching the losing red moves; the new route recommends `hd4` in the critical
  `e2 e8 e3 e7 e4 e6` family instead of the previous MCTS `he2` branch.
- Verification: 44 unit tests passed; `py_compile` passed for web, alpha-beta,
  MCTS, and backtest modules; `node --check` passed for frontend scripts.
- Hybrid vs MCTS, 6 games: hybrid 66.67%, MCTS 33.33%, errors 0.
- Hybrid vs alpha-beta depth 3, 6 games: 50% / 50%, errors 0.

Version `2026.06.30.01` hardens live play against stuck thinking states and
recent-position loops.

- Frontend analyze requests now abort on timeout and show an explicit error
  instead of leaving the UI in a permanent loading state.
- Backend root recommendations avoid moves that recreate a recent board state.
- Verification: 42 unit tests passed; frontend JS checks passed; local HTTP
  smoke confirmed `app_version=2026.06.30.01`.

Version `2026.06.06.04` adds the hybrid engine to both local and API-mode
backtests. The API mode now forwards the requested engine kind, and the default
web/API engine is hybrid rather than plain MCTS.

- Hybrid strategy: use MCTS for general planning, but switch to alpha-beta for
  immediate goal threats, tactical endgames, and low-wall races.
- Frontend now exposes model switching for both the trainer page and the AI
  battle page.
- Verification: 39 unit tests passed; `py_compile` passed for web, alpha-beta,
  MCTS, and backtest modules; `node --check` passed for frontend scripts.
- Hybrid vs MCTS, 8 games: 50% / 50%, errors 0.
- Hybrid vs alpha-beta depth 3, 8 games: hybrid 62.5%, alpha-beta 37.5%,
  errors 0.
- API-mode smoke against a local HTTP server: MCTS candidate vs alpha-beta
  baseline, 2 games, MCTS 100%, errors 0.

Version `2026.06.06.03` promotes MCTS 120 to the production web/API default.
The API and backtest API mode now pass an explicit engine kind, so deployed
checks can compare `engine: "mcts"` against `engine: "alpha-beta"` instead of
implicitly using only the default.

- Production default: MCTS, 120 simulations, max actions 20, rollout depth 2,
  exploration 1.35.
- Fallback: alpha-beta remains available through `engine: "alpha-beta"` and the
  backtest `--baseline-engine` / `--candidate-engine` flags.
- Local promotion tournament: MCTS 120 vs alpha-beta depth 3, 16 games, MCTS
  100%, alpha-beta 0%, errors 0.
- Reverse confirmation: MCTS baseline vs alpha-beta candidate, 8 games, MCTS
  87.5%, alpha-beta 12.5%, errors 0.
- API-mode local smoke: MCTS vs alpha-beta, 2 games, MCTS 100%, errors 0.
- Verification: 38 unit tests passed; `py_compile` passed for web, alpha-beta,
  MCTS, and backtest modules.

Version `2026.06.06.02` improves the production alpha-beta backend with audited
tempo and delay-wall tuning.

- Early/midgame tempo: when both sides are close in path distance and the engine
  still has many walls, prefer direct progress over weak delay walls or walls
  that slow the engine's own path.
- Low-wall trailing race: when behind, holding 2 or fewer walls, and the
  opponent has no walls, a wall that delays the opponent by 2 steps without
  self-delay is no longer over-penalized.
- Verification: 37 unit tests passed; `py_compile` passed for
  `barricade_web.py`, `barricade_trainer.py`, and `barricade_mcts.py`.
- Alpha-beta depth 3 vs alpha-beta depth 2, 4 games: candidate 75%, baseline
  25%, errors 0.
- MCTS 120 simulations vs alpha-beta depth 3, 8 games: MCTS 62.5%, alpha-beta
  37.5%, errors 0. MCTS remains experimental but is the next promotion
  candidate to test more deeply.

Version `2026.06.06.01` improves the production alpha-beta backend with a
late-goal wall threat guard. Near the goal, if the opponent still has walls and
can create a severe next-turn detour, root search can value a defensive wall
that slightly lengthens the current path but reduces that future trap. This
targets positions where a player is almost home but one opponent wall would
force a long reroute.

- Verification: 34 unit tests passed; `py_compile` passed for
  `barricade_web.py`, `barricade_trainer.py`, and `barricade_mcts.py`.
- Local smoke: alpha-beta depth 3 candidate vs alpha-beta depth 2 baseline,
  4 games, candidate 75%, baseline 25%, errors 0.
- Production web/API play still defaults to alpha-beta; MCTS remains
  experimental and backtest-selected only.

Version `2026.06.04.13` improves the experimental MCTS backend with low-wall
race filtering in candidate generation, priors, and rollout selection. Shortest
path progress can override reversal avoidance, fixing the repeated `f5` vs
`f7` MCTS loss-audit pattern. This is for backtest-selected MCTS only;
production web/API play still defaults to alpha-beta.

- Verification: MCTS 120 / max_actions 20 / rollout depth 2 vs alpha-beta depth
  3, 12 games, candidate 58.33%, baseline 41.67%, errors 0.
  `f5` vs `f7` no longer appears as the top loss-audit suspect; the next issue
  is midgame wall timing (`hb8` vs `ha7`).

Version `2026.06.04.12` improves the production alpha-beta backend in no-wall
endgames. Pure pawn races now prioritize safe shortest-path progress when the
side to move is not behind, reducing lateral drift during winning races.
Verification: 30 unit tests passed; local smoke depth3 candidate vs depth2
baseline over 8 games returned candidate 75%, baseline 25%, errors 0.

Version `2026.06.04.11` restores the original `ai.html` battle layout and
removes the visible realtime analysis panel. The board rail now shows the
simpler current-hint copy again, while `/api/analyze` can still expose analysis
metadata for tools.

Version `2026.06.04.10` tightens the AI page responsive breakpoint and board
height cap so the board is not clipped on mid-width desktop browsers.

Version `2026.06.04.09` fixes the `ai.html` UI layout so the board and realtime
analysis panel remain readable on desktop and narrower browser widths.

Version `2026.06.04.08` adds `audit_losses.py` for loss decision audits. A full
audit of `backtest_runs/mcts-v3-candidate-12` reviewed 6 candidate losses. The
top pattern was low-wall race regression: MCTS stepped away from goal while
alpha-beta preferred forward progress.

Version `2026.06.04.07` adds the AI real-time analysis visualization and
explainability payload to `/api/analyze`. The production search model remains
alpha-beta.

Version `2026.06.04.06` improves tournament diagnostics and MCTS tuning
controls. Summary output now includes engine-side results, and CLI flags expose
MCTS `max_actions`, `rollout_depth`, and exploration constants for both baseline
and candidate engines.

- Extended MCTS v2 tournament: alpha-beta depth 3 vs MCTS 80 simulations,
  20 games, candidate 50%, baseline 50%, errors 0.
- Parameter sweep best short sample: rollout depth 2, max actions 20,
  simulations 120, 6 games, candidate 100%, errors 0.
- Confirmation run for that setting: 12 games, candidate 50%, baseline 50%,
  errors 0.
- Decision: do not promote MCTS to production yet; keep alpha-beta as the web/API
  backend.

Version `2026.06.04.05` improves the experimental MCTS path with tactical
policy priors, short rollout value, and root avoid-action fallback. The web/API
production backend remains alpha-beta unless MCTS is explicitly selected in the
local backtest runner.

- Unit tests: 26 passed.
- MCTS v2 smoke tournament: alpha-beta depth 3 vs MCTS 80 simulations, 6 games,
  candidate win rate 83.33%, baseline 16.67%, errors 0.

Version `2026.06.04.04` adds an experimental `barricade_mcts.py` backend and
backtest switches for `--baseline-engine` / `--candidate-engine`. MCTS-lite uses
the current alpha-beta move ordering as policy priors, PUCT-style selection, and
static evaluation as a value estimate. It is useful for AlphaGo/AlphaZero-style
experiments, but it is not promoted as stronger than alpha-beta yet.

- Unit tests: 24 passed.
- MCTS-lite smoke tournament: alpha-beta depth 3 vs MCTS-lite 80 simulations,
  6 games, candidate win rate 50%, errors 0.
- Local baseline tournament: candidate depth 3 vs baseline depth 2, 30 games,
  candidate win rate 80%, errors 0.
- Historical synthesis tournament: the worktree synthesis engine vs 8 historical
  engine commits at depth 4 / 0.12 seconds, 16 games, synthesis win rate 68.75%.

Useful reports from the latest tuning session:

- `backtest_runs/synth-vs-history-depth4-20260604/summary.json`
- `backtest_runs/synth-depth-gated-local-30/summary.json`

`backtest_runs/` is intentionally ignored by git. Keep generated reports locally
unless a specific report needs to be attached or summarized in documentation.
