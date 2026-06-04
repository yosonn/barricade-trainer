# Barricade Backtest Loop

Backtesting tools for Barricade Trainer.

Current project version: `2026.06.04.05`

The tool supports two execution modes:

- `api`: call a deployed `/api/analyze` endpoint.
- `local`: import the local Python engine in this workspace and run decisions
  without any network dependency.

## Quick Start

Run a short baseline-vs-candidate tournament:

```powershell
python tools\barricade_backtest\backtest_loop.py --games 10 --baseline-depth 2 --candidate-depth 3 --time 0.05
```

Run the same tournament entirely inside the local repo:

```powershell
& 'C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  tools\barricade_backtest\backtest_loop.py --mode local --games 10 --baseline-depth 2 --candidate-depth 3 --time 0.05
```

Compare the normal alpha-beta backend against the experimental MCTS-lite
backend:

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

The latest promoted backend version is `2026.06.04.05`.

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
