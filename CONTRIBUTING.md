# Contributing to OmniServ

Thank you for your interest in contributing to OmniServ! OmniServ is an open-source, cross-platform local development server manager with native front-ends for macOS, Windows, and Linux.

---

## 🏗️ Repository Architecture

OmniServ is structured by platform and core components:

```
OmniServ/
├── engine/              # Shared Bash engine (used by Linux & macOS)
│   ├── omniserv         # Main engine CLI entry point
│   └── platform-linux.sh # Linux platform specific routines
├── linux/               # Linux GTK4 / libadwaita front-end & packaging
│   ├── app/             # Python application package
│   │   ├── bin/         # Executable entry points (omniserv-gui, omniserv-tray)
│   │   └── omniserv/    # Python modules
│   │       ├── app.py       # Application lifecycle & GTK application instance
│   │       ├── window.py    # Main window shell & navigation
│   │       ├── engine.py    # Engine IPC client
│   │       ├── dialogs.py   # Modal & configuration dialogs
│   │       ├── prefs.py     # Local GUI preferences store
│   │       ├── metrics.py   # System stats & samplers (/proc)
│   │       ├── widgets.py   # Reusable GTK widgets (PagedList, status_dot, etc.)
│   │       └── pages/       # Individual pane implementations
│   │           ├── dashboard.py
│   │           ├── services.py
│   │           ├── sites.py
│   │           ├── databases.py
│   │           ├── node.py
│   │           ├── python.py
│   │           ├── logs.py
│   │           └── settings.py
│   ├── build.sh         # .deb packaging script
│   └── packaging/       # App icons and metadata
├── windows/             # Windows C# / WinUI 3 application
│   ├── src/
│   │   ├── OmniServ.App/    # WinUI 3 desktop application
│   │   ├── OmniServ.Core/   # Server management core library
│   │   ├── OmniServ.Cli/    # Windows CLI
│   │   └── OmniServ.Elevate/# UAC elevation helper
│   ├── build.ps1        # PowerShell build script
│   └── installer/       # Inno Setup installer script
├── macos/               # macOS Swift / SwiftUI application
│   ├── Sources/OmniServ/# SwiftUI views and AppState
│   ├── build-app.sh     # App bundle build script
│   └── make-dist.sh     # .pkg and .dmg distribution packager
└── docs/                # Architecture docs, porting notes, and roadmaps
```

---

## 🛠️ Development & Building

### 🐧 Linux (Ubuntu / Debian)

**Prerequisites:**
- Python 3.10+
- GTK4 & libadwaita: `sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1`
- Optional tray support: `gir1.2-ayatanaappindicator3-0.1` or `gir1.2-gtk-3.0`

**Running from source:**
```bash
./linux/app/bin/omniserv-gui
```

**Building the `.deb` package:**
```bash
./linux/build.sh
```

---

### 🪟 Windows (10 / 11)

**Prerequisites:**
- .NET 8.0+ SDK
- Visual Studio 2022 / VS Code with C# Dev Kit
- Inno Setup 6 (for packaging)

**Building:**
```powershell
powershell -ExecutionPolicy Bypass -File windows/build.ps1
```

---

### 🍎 macOS (14+)

**Prerequisites:**
- Xcode 15+ & Command Line Tools
- Swift 5.9+

**Building:**
```bash
cd macos
./build-app.sh
./make-dist.sh
```

---

## 📐 Code Style & Conventions

- **Keep single-responsibility modules**: Avoid monolithic files. Split UI pages into dedicated modules.
- **Engine Parity**: When adding or updating a feature, strive to preserve parity across macOS, Windows, and Linux.
- **Non-destructive operations**: Ensure user data (`~/OmniServ/www/`, databases, custom configs) is preserved unless explicit purge is requested.
- **Root / Privilege separation**: Run the minimal required code with elevated privileges (`pkexec` / `sudo` / `UAC`). User-level operations (APIs, logs, status) must remain unprivileged.

---

## 🤝 Submitting Pull Requests

1. Fork the repository and create a descriptive feature branch (`feature/my-feature` or `fix/issue-description`).
2. Verify that your changes build and run without errors on your platform.
3. Commit with clear, concise commit messages.
4. Open a pull request against the `main` branch with a summary of changes and testing performed.
