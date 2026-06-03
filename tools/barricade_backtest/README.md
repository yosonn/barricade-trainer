# Barricade Backtest Loop

Backtesting tools for Barricade Trainer.

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
