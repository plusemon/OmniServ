# OmniServ for Windows

Native Windows build of OmniServ (C# / .NET 8 + WinUI 3). See the full architecture
and port mapping in [`../docs/WINDOWS-PORT.md`](../docs/WINDOWS-PORT.md).

> Build and test this **on Windows** — WinUI, Windows services, the hosts file, and
> the installer can't be built or verified on macOS/Linux.

## Layout

```
windows/
  OmniServ.sln
  src/OmniServ.Core/   shared brains (paths, models, php-cgi mgr, engine) — net8.0
  src/OmniServ.Cli/    omniserv.exe — transparent CLI over Core           — net8.0
  src/OmniServ.App/    WinUI 3 GUI (unpackaged)                          — net8.0-windows
  installer/          Inno Setup script → OmniServ-Setup.exe
  build.ps1           dotnet publish + iscc
```

## Prerequisites

- Visual Studio 2022 (17.10+) with **.NET desktop** + **Windows App SDK** workloads,
  or the standalone .NET 8 SDK + Windows App SDK.
- (For the installer) [Inno Setup 6](https://jrsoftware.org/isdl.php).

## Develop

```powershell
git clone https://github.com/plusemon/OmniServ
cd OmniServ\windows
dotnet build OmniServ.sln
dotnet run --project src\OmniServ.Cli -- init      # try the CLI
dotnet run --project src\OmniServ.Cli -- status
# the GUI (run from Visual Studio for the best XAML/debug experience, or:)
dotnet run --project src\OmniServ.App
```

### Status

**Phases 1–4 are implemented and working** (CLI `omniserv.exe` + a functional WinUI GUI):

- `init`, `install <nginx|php@8.4|mkcert>` (portable-zip downloads; falls back to a
  local Laragon install on dev boxes), `site add/rm/php`, `start/stop/restart`,
  `enable/disable`, `secure <domain>`, `status`/`api`, `db {list|create|drop}`, `adminer`.
- PHP runs as **`php-cgi.exe` over TCP** (no php-fpm on Windows) — port scheme
  `9100 + maj*10 + min` (8.4→9184); nginx uses `fastcgi_pass 127.0.0.1:<port>`.
- **HTTPS** via mkcert (`secure`) — issues a trusted cert, re-renders the vhost's
  ssl block, reloads nginx.
- **Databases**: OmniServ runs its own MySQL/MariaDB on `127.0.0.1:3306` (fresh data
  dir under `data\`, passwordless root) + `db create/list/drop`. **Adminer** is a
  one-command DB UI served at `adminer.<tld>`.
- **Mailpit** (`mailpit`): catches outgoing mail (SMTP `:1025`), web UI fronted at
  `mailpit.<tld>`. **Node** (`node list|install|use|uninstall`) via fnm.
- Admin-only steps (hosts file, mkcert CA install) go through
  **`omniserv-elevate.exe`** (requireAdministrator) for a single UAC prompt.
  (CI/automation can set `OMNISERV_SKIP_HOSTS=1` to skip the hosts step.)
- **WinUI GUI** (`OmniServ.App`): Dashboard (live status, start/stop all, log),
  Sites, Services, Settings (autostart). Run it from a **self-contained** build (or
  install the Windows App Runtime 1.6) — see Release below.

Also implemented: **system tray** (close hides to tray, right-click → Open/Quit),
`php ini path|reload`, **`php ioncube <ver>`** (downloads the matching Windows loader
and enables it via a per-version `conf.d`), `php status`, and an **in-app updater**
(Settings → Check for updates → downloads + runs the latest `OmniServ-Setup.exe`).

### Code signing (TODO before public distribution)

The installer + exes are currently **unsigned**, so Windows SmartScreen shows
"Windows protected your PC" → users click **More info → Run anyway** (the analog of
macOS "Open Anyway"). To sign, get an OV/EV code-signing certificate and run, after
`build.ps1`:

```powershell
$st = "${env:ProgramFiles(x86)}\Windows Kits\10\bin\<ver>\x64\signtool.exe"
& $st sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
    /f mycert.pfx /p <pwd> `
    installer\dist\OmniServ-Setup-0.1.0.exe
```

Sign the three payload exes (`OmniServ.App.exe`, `omniserv.exe`, `omniserv-elevate.exe`)
*before* packaging, then the installer itself. An EV cert clears SmartScreen
immediately; an OV cert builds reputation over time.

## Release

```powershell
.\build.ps1                 # -> windows\installer\dist\OmniServ-Setup-<ver>.exe
```

Then cut a GitHub release with the `.exe` so the in-app updater (asset matcher:
`.exe`) finds it — same flow as the mac `.pkg`.
