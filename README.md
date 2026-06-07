# Turnlight

Turnlight is a local Windows utility that watches a small screen region and shows a large visual alert when an AI agent appears to finish its turn.

It is built for AI agent power users, developers, designers, and anyone who runs long AI tasks while doing something else nearby. Turnlight helps you stay focused without constantly checking whether the agent is done.

Turnlight runs locally, does not use accounts, does not send data anywhere, and does not use external services. It does not call AI APIs, does not include telemetry, and is intentionally designed to stay that way.

## Status

Current version: `v0.9.0-beta`

Turnlight is a stable Windows beta for daily use, but it is still being validated on more Windows setups before a `v1.0.0` release.

Tested:

- Windows 11

Expected but not fully verified yet:

- Windows 10

## Download

Download the latest beta installer from GitHub Releases:

[Turnlight v0.9.0-beta](https://github.com/ivanislit/turnlight/releases/tag/v0.9.0-beta)

Installer:

```text
Turnlight-0.9.0-beta-Setup.exe
```

The installer does not require Python to be installed on the target PC.

## Windows SmartScreen And Antivirus

Turnlight is currently unsigned. Because of that, Windows SmartScreen or antivirus software may warn before installation.

This is common for new independent Windows apps, especially beta installers with low reputation. You are encouraged to inspect the source code before installing. The project is intentionally small and simple: it watches pixels from a screen region, compares them to local samples, and displays a local alert.

## Install

1. Open the GitHub Release.
2. Download `Turnlight-0.9.0-beta-Setup.exe`.
3. Run the installer.
4. Keep the default install location unless you have a reason to change it.
5. Keep the desktop shortcut enabled if you want quick access while testing.

Default install location:

```text
%LocalAppData%\Programs\Turnlight
```

Local app data:

```text
%LocalAppData%\Turnlight
```

Turnlight stores config, logs, status, and samples locally in that data folder.

## First Setup

1. Open Turnlight.
2. Click `Set Region`.
3. Select the small screen area that changes between a busy/stop state and a ready/send state.
4. Open `Settings`.
5. Capture several `Busy` samples while the agent is working.
6. Capture several `Ready` samples when the agent is ready for the next message.
7. Capture `Ignored` samples for visual states that should not trigger an alert.
8. Use `Test Alert` to confirm the alert is visible and the sound behavior is right for you.
9. Leave Turnlight watching in the background.

Capture samples across the themes, windows, zoom levels, and hover states you actually use. Better samples make detection more reliable.

## How It Works

Turnlight keeps detection intentionally simple:

```text
busy_stop stable -> typing_arrow -> alert
```

It watches for a stable busy state, then triggers once when that same region changes into a ready state.

Turnlight was primarily tested in my personal Codex workflow. It can also work with other AI tools because the logic is based on local visual samples. In practice, the key is selecting the right region and capturing samples that match your actual UI.

## Personalization

Turnlight includes basic personalization:

- Alert color
- Custom alert title and subtitle
- Optional custom WAV sound
- Sound on/off
- Multi-screen or primary-screen alert mode

The alert text and samples are stored locally.

## Privacy

Turnlight is local-first by design.

- No accounts
- No cloud services
- No telemetry
- No AI APIs
- No external services
- No background server
- No uploaded screenshots

Turnlight captures only the screen region you configure. Samples stay on your machine.

## Screenshots

Screenshots and a visual walkthrough will be added after the beta installer has been validated on more machines.

Planned:

- Main window
- Settings
- Personalization
- Alert overlay
- Installer flow

## Why I Built This

I built Turnlight because I use AI agents for long work sessions and did not want to keep checking the screen every few minutes.

The practical goal is to maximize focus without losing the ability to do other useful things while an agent is running: planning future prompts, doing design work, stepping away from the desk for a moment, or even doing simple stretching and breathing exercises near the workspace when possible.

It is a small tool, but it solves a very real workflow problem for me.

## Limitations

- Windows only for now.
- Windows 11 has been tested; Windows 10 still needs more validation.
- The installer is unsigned and may trigger SmartScreen or antivirus warnings.
- Detection depends on local samples and the selected region.
- Turnlight only sees visible pixels on your desktop.
- It cannot inspect secure desktops such as UAC prompts or protected screens.
- The watched region should stay inside one physical monitor.

## Install From Source

For development or local source installs:

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

Build the Windows installer:

```powershell
.\build.ps1
```

The build uses PyInstaller and Inno Setup.

## Feedback And Contact

Feedback is welcome through GitHub Issues or email.

- GitHub: [github.com/ivanislit](https://github.com/ivanislit/)
- Email: `ivannav.464@gmail.com`

Messages and issues are welcome in English or Spanish.

## Author

Created by `ivanislit`.

In some places I may write it as `ivanIsLit`.

## License

Turnlight is licensed under Apache-2.0. See [LICENSE](LICENSE).

Apache-2.0 is a good fit for Turnlight because it is permissive, standard for open-source software, allows broad reuse, and includes a patent grant while keeping the project simple to adopt.

## Notice

Turnlight is not affiliated with, endorsed by, or sponsored by OpenAI, Anthropic, Cursor, Windsurf, or any AI tool provider. Product names and trademarks belong to their respective owners.
