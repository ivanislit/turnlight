# Turnlight

Turnlight is a local Windows utility that watches a small screen region and shows a full-screen visual alert when an AI agent appears to finish its turn.

It is built for people who keep long-running AI coding sessions open while working elsewhere. Turnlight does not use any AI provider API, account, cloud service, telemetry, or background server. It only compares pixels from a region you select on your own screen.

## Requirements

- Windows 10 or Windows 11
- Python 3.12+
- PowerShell

## Install From Source

```powershell
git clone git@github.com:ivanislit/turnlight.git
cd turnlight
.\install.ps1
.\create-desktop-shortcut.ps1
```

Run manually:

```powershell
.\run.ps1
```

`install.ps1` creates a local virtual environment, installs Python dependencies, and prepares runtime icon assets from the SVG sources.

## First Setup

1. Open Turnlight.
2. Click `Set Region`.
3. Select the AI tool button area you want to watch.
4. Open `Settings`.
5. Capture several `Busy` samples while the agent is working.
6. Capture several `Ready` samples when the arrow/send state is valid.
7. Capture `Ignored` samples for visual states you do not want to treat as ready.
8. Leave Turnlight watching in the background.

Capture samples across the themes, windows, zoom levels, and hover states you actually use. Samples stay on your PC under `samples/`.

## Detection Model

Turnlight keeps detection intentionally simple:

```text
busy_stop stable -> typing_arrow -> alert
```

The app watches for a stable busy state, then triggers once when that same region changes into a ready arrow state.

## Settings

- `Capture Busy`
- `Capture Ready`
- `Capture Ignored`
- `Test Alert`
- `Personalization`
- `Sound On/Off`
- `Open Samples`
- `Multi-Screen / Principal Screen`
- `Reset Samples`

Personalization controls the alert color and optional WAV sound. If no custom sound is selected, Turnlight uses the default system sound.

## Privacy

Turnlight captures only the screen region you configure. Screenshots are used locally for classification and sample storage. Nothing is uploaded.

Ignored local files include `config.json`, `status.json`, logs, generated icon assets, and PNG samples.

## Limitations

- Turnlight only sees visible pixels on your desktop.
- It cannot inspect secure desktops such as UAC prompts or protected screens.
- It is currently Windows-only.
- The watched region should stay inside one physical monitor.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Notice

Turnlight is not affiliated with, endorsed by, or sponsored by OpenAI. Codex, ChatGPT, and OpenAI are trademarks or registered trademarks of their respective owners.
