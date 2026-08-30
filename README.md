<div align="center">

<h1>⚡ OmniServ</h1>

<p><strong>Your own free local web server — native, self-controlled, open-source.</strong></p>

<p>A free alternative to ServBay · Herd · Laragon — with multi-PHP, nginx/Apache/OpenLiteSpeed, databases, caching, trusted HTTPS, one-click WordPress, Node &amp; Python apps, and public sharing via Cloudflare Tunnel.</p>

<p>
  <a href="https://github.com/wpexpertinbd/OmniServ/releases"><img src="https://img.shields.io/github/v/release/wpexpertinbd/OmniServ?style=flat-square&label=latest&color=4f46e5" alt="Latest Release"></a>
  <img src="https://img.shields.io/badge/license-MIT-22c55e?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/macOS-Apple%20Silicon%20%2B%20Intel-black?style=flat-square&logo=apple" alt="macOS">
  <img src="https://img.shields.io/badge/Windows-10%2F11-0078d4?style=flat-square&logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/Linux-Ubuntu%20%2F%20Debian-e95420?style=flat-square&logo=ubuntu" alt="Linux">
</p>

<p>
  <a href="https://github.com/wpexpertinbd/OmniServ/releases"><strong>⬇️ Download</strong></a> ·
  <a href="#-quick-start"><strong>🚀 Quick Start</strong></a> ·
  <a href="docs/MIGRATING.md"><strong>📦 Migrate</strong></a> ·
  <a href="docs/ROADMAP.md"><strong>🗺️ Roadmap</strong></a>
</p>

| 🍎 macOS | 🪟 Windows | 🐧 Linux |
|:---:|:---:|:---:|
| ✅ Stable | ✅ Stable | ✅ Stable |
| Native menu-bar app | Native WinUI app | GTK4 / libadwaita app |
| Apple Silicon + Intel | Windows 10 / 11 | Ubuntu / Debian `.deb` |

> 🟢 **Battle-tested** — runs the author's daily dev work: WordPress, OpenCart, WHMCS, Blesta, Laravel, Next.js.

</div>

---

## ✨ Features

### 🌐 Web Servers

| | nginx | Apache | OpenLiteSpeed *(Linux)* |
|---|:---:|:---:|:---:|
| Default fast server | ✅ | — | — |
| `.htaccess` support | via proxy | ✅ native | ✅ live reload |
| Pick per-site | ✅ | ✅ | ✅ |

### 🐘 PHP

- Versions **7.4 · 8.1 · 8.2 · 8.3 · 8.4 · 8.5 · 8.6** — switchable **per site**, each with its own FPM pool
- ionCube + common extensions pre-enabled (WordPress / OpenCart / WHMCS / Blesta)

### 🗄️ Databases & Caching

- **MariaDB / MySQL** + **PostgreSQL** — create/drop databases and set passwords from the GUI
- **Redis** + **Memcached** — zero-config caching

### 🛠️ Web Tools

| Tool | URL | Notes |
|------|-----|-------|
| phpMyAdmin | `http://phpmyadmin.test` | Uploads up to 2 GB |
| Adminer | `http://adminer.test` | Lightweight alternative |
| Mailpit | `http://mailpit.test` | Catch all outgoing mail |

### 🚀 Site Types

| Type | What OmniServ does for you |
|------|---------------------------|
| **WordPress** | Downloads latest WP, creates DB, pre-fills `wp-config.php` |
| **PHP** | Creates a database named after the site |
| **Others** | Just the domain — static files or any custom app |
| **Node app** | Manages frontend (e.g. Next.js) + optional backend (e.g. Laravel), supervises processes, reverse-proxies at your domain. Edit `.env`, run `npm install` in-app |
| **Python app** | Creates a virtualenv, supervises Flask / Django / FastAPI / Gunicorn / Uvicorn, reverse-proxies at your domain. `pip install` from in-app |

### 🔑 More Highlights

- **Trusted HTTPS** — one click issues a locally-trusted mkcert certificate. No browser warnings.
- **Automatic `*.test` domains** — every site is instantly reachable at `name.test`
- **Per-site custom root folder** — use any folder on disk
- **Multiple Node.js versions** via `fnm`; **managed Python** interpreter for Python apps
- **Cloudflare Tunnel** — one-click temporary public `https://…trycloudflare.com` URL, no account needed
- **Live dashboard** — CPU / RAM / disk / network + per-service status cards
- **Menu bar / system tray** — starts services at login, sits quietly until you need it
- **In-app auto-updater** — Settings ▸ Updates

---

## ⬇️ Download & Install

Grab the latest build from the [**Releases**](https://github.com/wpexpertinbd/OmniServ/releases) page.

> [!IMPORTANT]
> OmniServ owns ports **80 / 443** and the `*.test` domain. Quit any other local stack (ServBay / Herd / Laragon / XAMPP) before the first run.

---

### 🍎 macOS

Download **`OmniServ-x.y.z.pkg`** (installer) or **`.dmg`** (drag to Applications).

<details>
<summary><strong>⚠️ "Unidentified developer" / "damaged app" warning — one-time only, read this</strong></summary>

OmniServ is free and open-source but **not notarized by Apple** (requires a paid Apple Developer account), so macOS shows a one-time warning on first launch.

**`.pkg` installer:**
> Right-click the `.pkg` → **Open** → **Open**

**`.dmg` / App bundle:**
> Drag OmniServ to Applications, then open it. If you see *"can't be opened"* or *"is damaged"*:
> **System Settings → Privacy & Security** → scroll to *"OmniServ was blocked…"* → **Open Anyway** → **Open**
>
> *(Older macOS: right-click → Open → Open)*

The "damaged" message is just macOS's download-quarantine flag on an un-notarized app — nothing is actually wrong. After the first launch, **Settings ▸ Updates** handles all future versions.

</details>

---

### 🪟 Windows

1. **Download and run `OmniServ-Setup-x.x.x.exe`.**
2. SmartScreen may show *"Windows protected your PC"* → click **More info → Run anyway** *(one-time — signing certs are costly; the full source is here).*
3. Finish the installer and launch OmniServ.

<details>
<summary><strong>🛡️ Recommended first step — add antivirus folder exclusions</strong></summary>

OmniServ is unsigned and downloads server binaries (PHP, nginx, MariaDB, Redis, Memcached…). Some antivirus engines false-positive and quarantine them — sometimes *after* a clean install on the next scan. Adding exclusions avoids this entirely while **keeping your antivirus on**.

Add **both** folders:

```
C:\Program Files\OmniServ
C:\Users\<your-user>\AppData\Local\OmniServ
```

| Antivirus | Where to add exclusions |
|-----------|------------------------|
| **Windows Defender** | Virus & threat protection → Manage settings → Exclusions → Add or remove exclusions → Add an exclusion → Folder |
| **ESET** | Advanced setup (F5) → Detection engine → Exclusions → Performance exclusions → Edit → Add |
| **Avast / AVG** | Menu → Settings → General → Exceptions → Add exception |
| **Bitdefender** | Protection → Antivirus → Settings → Manage exceptions → Add an exception |
| **Kaspersky** | Settings → Security settings → Exclusions / trusted apps → Manage exclusions → Add |
| **Malwarebytes** | Settings → Allow list → Add → Allow a file or folder |
| **Other** | Look for *Exclusions / Exceptions / Allow list / Trusted folders* |

> **Note:** If OmniServ was already installed and a service won't start (binary was quarantined): add the exclusions above, **restore** the quarantined file from your antivirus, then reinstall that service from the **Services** tab or relaunch OmniServ.

</details>

<details>
<summary><strong>🚫 "Application Control policy has blocked this file" (Smart App Control)</strong></summary>

This is **Smart App Control** (Windows 11), not a virus. It blocks unsigned apps it doesn't recognize.

- **SmartScreen** *(blue dialog — "Windows protected your PC")* → click **More info → Run anyway**, or right-click the installer → **Properties** → tick **Unblock** → **OK**.
- **Smart App Control** *("Application Control policy has blocked…")* — SAC has no per-app allow. To run unsigned apps you must disable it:
  **Settings → Privacy & security → Windows Security → App & browser control → Smart App Control settings → Off**

> ⚠️ **One-way change** — Smart App Control can only be re-enabled by resetting or reinstalling Windows. Only disable it if you understand the trade-off. If you'd prefer not to, wait for a signed build (planned).
>
> **Why this happens:** OmniServ is currently unsigned (code-signing certificates have an ongoing cost). Each new release is a fresh unsigned file with no reputation yet. A signed build removes this entirely.

</details>

---

### 🐧 Linux (Ubuntu / Debian)

```bash
# Download omniserv_<version>_all.deb from the linux-v* release, then:
cd ~/Downloads
sudo dpkg -i ./omniserv_*.deb && sudo apt-get -f install -y
omniserv-gui        # or launch "OmniServ" from your apps menu
```

Future updates: `omniserv self-update`

**What the `.deb` provides:**
- Engine + a **GTK4 / libadwaita** control panel (same 8 panes as macOS / Windows)
- Servers installed on demand via `apt` — PHP from the **Ondřej Surý** repo (7.4 → 8.4), plus a portable static build for versions the distro can't provide
- `*.test` resolves via a managed `/etc/hosts` block by default (wildcard dnsmasq is opt-in)
- Closing the window keeps OmniServ in the **top-bar tray**

Tested on **Ubuntu 24.04 + 26.04 + GNOME**. Full guide → [`linux/README.md`](linux/README.md)

---

## ✅ Before You Start — Services Checklist

On first run OmniServ installs the core service set automatically. Make sure each shows **running / active**, or click **Start All** in the Services tab:

| Service | Why | Required for |
|---------|-----|-------------|
| **nginx** | Web server | Every site |
| **PHP** (≥ one version, e.g. 8.4) | Runs PHP code | Every PHP / WordPress site |
| **MariaDB / MySQL** | Database | WordPress + any DB-backed site |
| **DNS / dnsmasq** | Resolves `*.test` | Every site *(macOS — Windows uses the hosts file automatically)* |
| **mkcert** *(optional)* | Trusted local HTTPS | Only if you want `https://` |

> **"This site can't be reached" / `DNS_PROBE_FINISHED_NXDOMAIN`** → **DNS** service isn't running. Open **Services** and start **dnsmasq** (asks for admin once).
>
> **"502 Bad Gateway"** → the site's **PHP version** or **nginx** isn't running. Start them from the Services tab.

---

## 🚀 Quick Start

1. **Add a site** — Sites ▸ **+** → enter a name (e.g. `myshop`), pick a type & PHP version
2. Open **`http://myshop.test`** in your browser
3. **Want HTTPS?** Site **"…"** menu ▸ **Enable HTTPS** → `https://myshop.test`
4. **WordPress?** Pick the WordPress type → OmniServ downloads WP, creates the DB, and pre-fills `wp-config.php` — just finish the title + admin step in the browser

**Each site row gives you:**

| Action | Description |
|--------|-------------|
| 🌐 Open in browser | Instantly open your site |
| 📁 Open folder | Jump to the site's root folder |
| 📋 View logs | See nginx / PHP / app logs |
| ▶️ / ⏹️ Start / Stop | Control the site |
| 🔗 Share | One-click Cloudflare Tunnel public URL |
| **`…` menu** | Change PHP · switch web server · manage subdomains · enable HTTPS · change root folder · delete |
| Node apps | Start / stop / restart · edit `.env` · `npm install` |

---

## 📦 Migrating from Another Stack

Already using XAMPP, Local, Laragon, ServBay, or Herd? Migration is three steps — copy files, import the database, point the app at OmniServ.

→ **[Migration guide — `docs/MIGRATING.md`](docs/MIGRATING.md)**

---

## 🗄️ Databases & phpMyAdmin

For local convenience, **all databases use `root` with no password** — nothing is reachable from outside your machine.

| Setting | Value |
|---------|-------|
| Host | `localhost` (or `127.0.0.1`) |
| Port | `3306` |
| User | `root` |
| Password | *(leave blank)* |

- **phpMyAdmin** → `http://phpmyadmin.test` · **Adminer** → `http://adminer.test`
  Log in as `root` with an empty password. Toggle each tool on/off from the **Web tools** card.
- **Want a password?** — **Databases ▸ Root password** (then update your app configs to match).

---

## 🌍 Public Sharing — Cloudflare Tunnel

Hit the **Share** button on any site → OmniServ starts a **Cloudflare quick tunnel** and shows a temporary public `https://…trycloudflare.com` URL. No account, no router config. Click **Stop sharing** when done. (`cloudflared` installs on first use.)

---

## 🔒 Security

OmniServ is a **local development** tool, hardened accordingly:

- **Loopback-only** — nginx, Apache, MySQL, Mailpit, and your Node/Python apps listen on `127.0.0.1`. Your sites and tools are **never exposed to your LAN**.
- **Root / no password by design** — safe because nothing is reachable off this machine.
- Site, DB, and log names are validated (no path traversal or config injection); DB inputs are SQL-escaped; passwords are passed via environment variables, never on the command line.
- **Minimal privilege escalation** — only binding `:80/:443` and `*.test` DNS (macOS `sudo` / Windows UAC). The optional macOS password-less helper grants `sudo` to **only** the `nginx` binary.
- **Cloudflare Tunnel** is the one intentional exception — it exposes a single site publicly while it's running, and only when you start it yourself.

---

## 🛠️ Build from Source

Everything is in this repo:

| Platform | Stack | Build command |
|----------|-------|---------------|
| **macOS** | Bash engine + SwiftUI | `cd macos && ./build-app.sh && ./make-dist.sh` → `.dmg` + `.pkg` |
| **Windows** | C# / .NET + WinUI | `windows/build.ps1` — see [`windows/README.md`](windows/README.md) |
| **Linux** | Bash engine + GTK4 / PyGObject | `cd linux && ./build.sh` → `dist/omniserv_<ver>_all.deb` — see [`linux/README.md`](linux/README.md) |

**Engine** (`engine/omniserv`) is also usable directly:

```bash
omniserv doctor
omniserv site add
omniserv secure
omniserv status
```

**Data directories:**
- macOS: `~/.omniserv/` · Sites: `~/OmniServ/www/`
- Windows: `%LOCALAPPDATA%\OmniServ`

<div align="center">

Made with ❤️ by [Emon Khan](https://emon.bd)

</div>
