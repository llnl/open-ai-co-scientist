# Local Deployment Helpers

These scripts run a persistent local Gradio instance for manual testing.

## Install Or Reinstall The Service

From the repository root:

```bash
./local-deploy/install-launchagent.sh
```

This writes a macOS LaunchAgent at:

```text
~/Library/LaunchAgents/com.liao.open-ai-co-scientist.local.plist
```

The service starts at login and is kept alive by launchd.

## Refresh After Pulling Changes

From the repository root:

```bash
./local-deploy/restart.sh
```

`refresh.sh` is an alias for the same command:

```bash
./local-deploy/refresh.sh
```

When the service starts, `run.sh` fetches `origin/main`, pulls it if the checkout
is on `main`, updates the virtual environment, sources `.env` when present, and
starts `python app.py`.

## Open The App

```text
http://127.0.0.1:7860
```

## Logs

```bash
tail -f logs/local-deploy.log
```

Launchd stdout and stderr are written to:

```text
logs/launchd.out.log
logs/launchd.err.log
```
