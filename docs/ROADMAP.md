# OmniServ — progress & next steps

## Decisions locked
- **Form:** native **SwiftUI menu-bar app** driving a transparent **bash engine** (`engine/omniserv`).
- **Driver:** a free, fully self-controlled stack (no vendor lock-in), latest versions via Homebrew.
- **Scope:** multi-PHP (per-site), **Nginx AND Apache** (either/both), MySQL/MariaDB + PostgreSQL + Redis, phpMyAdmin + Adminer + Mailpit + Node, `*.test` + trusted HTTPS.
- **Config root:** `~/.omniserv/` (separate from system/brew). Engine: `/Applications/ServBay/www/OmniServ/engine/omniserv`.
- **Coexistence with ServBay: DECIDED (2026-06-24) — option (b): OmniServ owns 80/443 + `*.test`.**
  ServBay must be quit before OmniServ web/DNS binds those ports; ports 80/443 + dnsmasq use sudo.

## Done — Phase 1 (foundation)
- `engine/omniserv` with `doctor` (deps + ports + ServBay check), `init` (creates `~/.omniserv`), `status`, and a service registry (php/php@8.1-8.4, nginx, httpd, mariadb, mysql, postgresql@17, redis, dnsmasq, mkcert, mailpit, node).
- Env confirmed: macOS 26.6 arm64, **Xcode 26.5 + Swift 6.3.2** (can build the GUI), Homebrew 6. Installed already: php@8.1-8.4 (+ default `php` symlink oddly points to 7.4 — OmniServ should normalize), nginx 1.31, mariadb 12.3.

## Done — Phase 2 (web + sites)
1. ✅ `omniserv install <svc|all>` — brew install wrapper over the registry.
2. ✅ nginx main conf (`~/.omniserv/nginx/nginx.conf`, catch-all default + `include sites/*.conf`) + per-site vhosts; `omniserv site add <name> [--php 8.4] [--root path] [--server nginx|apache]`, `site list`, `site rm`.
3. ✅ `omniserv dns` — writes OmniServ dnsmasq conf for `*.test` and prints the sudo activation steps (dnsmasq.d + `/etc/resolver/test`).
4. ✅ `omniserv secure <domain>` — `mkcert -install` (once) + per-site cert into `~/.omniserv/certs/`, then re-renders the vhost to turn on the HTTPS listener.
5. ✅ Per-site PHP-FPM pools — one socket per PHP version in `~/.omniserv/run/php-<ver>.sock`; vhost fastcgi wired to the chosen version. **Verified live**: pool starts + binds socket; `nginx -t` passes.
6. ✅ `omniserv start|stop|restart <svc|all>` — nginx (sudo when port <1024), FPM pools (pid tracking in `run/`), and brew-services daemons (mariadb/mysql/postgresql@17/redis/mailpit/dnsmasq). `status` shows running state + sites.
7. ✅ Version probes capture `2>&1` (nginx/httpd version goes to stderr).

### Not yet executed (privileged — run when going live, ServBay quit)
- `omniserv dns` activation steps (sudo: dnsmasq + `/etc/resolver/test`).
- `mkcert -install` (keychain prompt) on first `omniserv secure`.
- `omniserv start all` binding 80/443 (sudo).
- Optional: normalize the default `php` symlink (currently 7.4); OmniServ sidesteps it by defaulting to `php@8.4`.

## In progress — Phase 4 (native GUI, our own — no ServBay/Herd dependency)
Engine contract: `omniserv api` emits JSON (config + services{installed,running,version} + sites).
SwiftUI app in `macos/` (SwiftPM, macOS 14+, builds with `swift build` / opens in Xcode):
- ✅ `Engine.swift` — Process bridge: `run` (user) + `runPrivileged` (osascript admin prompt for :80/:443 + dns, shell+AppleScript escaped), `snapshot()` decodes `api` JSON.
- ✅ `AppState` (@Observable) — resolves engine path (env → ~/.omniserv → dev checkout), reload/control/install/addSite/secure/removeSite, runs engine off the main actor.
- ✅ UI — `Window` + `MenuBarExtra`; NavigationSplitView (Services / Sites). Services grouped by role with status dots + Start/Stop/Install; Sites list with open-in-browser, one-click Secure, add-site sheet (PHP picker), remove. Start/Stop All in sidebar footer + menu bar.
- ✅ Live auto-refresh (4s), per-site PHP version switch.
- ✅ Databases: engine `db {list|create|drop|passwd} [name] [--engine mysql|pg] [--password PW]` (mysql auth auto-detect: OS user → -u root; name validation). Optional per-DB user (named after the DB) with password — set on create, set/change after, dropped with the DB; password passed via `$OMNISERV_DB_PASSWORD` (never argv); SQL-escaped. GUI Databases tab: server start/stop, create with engine picker + optional password + Generate, per-row Set/Change password sheet (hasUser-aware), drop with confirm.
- ✅ DB root user: engine `db root-status` / `db root-passwd` (empty = blank); GUI root-user card with Set/Change password (blank allowed) + Generate. Only touches root@localhost (the OS-user socket account we operate through is untouched).
- ✅ Fixed mysql/mariadb collision: probe keg-specific `opt/<formula>/bin/...` (bin/mysql is a mariadb symlink, was falsely flagging mysql installed → broken Start).
- ✅ Settings: engine `config {show|set <key> <value>}` (validates; tld/port changes regenerate all vhosts + nginx.conf) + GUI Settings tab (TLD, http/https port, sites_root, default PHP/web; Save restarts nginx on port/tld change via admin prompt).
- ✅ Logs: engine `logs [file|--list] [lines]` + GUI Logs tab (pick a log, monospaced tail, reload).
- ✅ Node multi-version: registry `node` → **fnm**; engine `node {list|remote|install|use|uninstall}` (versions under `~/.omniserv/fnm`; `use` sets fnm default + links node/npm/npx into `~/.omniserv/bin`). GUI Node tab: install by version/quick-buttons (18/20/22/24/lts/latest), installed list with default badge + Use/Uninstall.
- ✅ Apache (`--server apache`): reverse-proxy model — nginx fronts :80/:443, proxies the host to Apache on 127.0.0.1:8080 which serves with `AllowOverride All` (**native .htaccess**) + php-fpm via mod_proxy_fcgi. Per-site nginx OR apache; both run together. Verified: .htaccess RewriteRule works.
- ▶️ Next: Adminer/Mailpit one-click; GUI server picker; LaunchAgent.

## Phase 5 (packaging) — in progress
- ✅ `macos/build-app.sh` → self-contained **OmniServ.app** (bundles the engine in Resources; app prefers the bundled engine, then `~/.omniserv/engine`, then dev checkout). Info.plist (`com.emon.omniserv`), ad-hoc signed last (Apple-Silicon "damaged" trap avoided). Engine prepends `/opt/homebrew/{bin,sbin}` to PATH so a Finder-launched app still finds `brew`.
- ✅ App icon (.icns, BH blue). Menu-bar-resident: close window → .accessory (no Dock icon, stays running); reopen → .regular.
- ✅ Distributables: `macos/make-dist.sh` → `OmniServ-<ver>.dmg` (drag-to-Applications, +Applications symlink) and `OmniServ-<ver>.pkg` (pkgbuild → /Applications). Ad-hoc signed; DMG checksum verified, PKG payload verified.
- ▶️ Next: LaunchAgent (launch-at-login / autostart services), optional Developer-ID sign + notarize for clean distribution to other Macs.
- Run now: `cd macos && swift run OmniServ`  (engine must be initialized; privileged actions prompt for admin).

## Paused 2026-06-24 (all committed) — resume notes
OmniServ is feature-complete for daily use: Dashboard (live CPU/RAM/disk + sparkline,
service cards, Websites list, Web-tools), Services (+★ auto-start), Sites, Databases,
Node, Logs, Settings; menu-bar-resident; BH-blue icon; `.app` + `.dmg`/`.pkg`.
Engine covers PHP 8.1–8.6 + FPM, nginx + Apache (.htaccess), MariaDB/PG + phpMyAdmin/
Adminer, Mailpit, Node (fnm), HTTPS (mkcert), `*.test` (dnsmasq), 2GB uploads, ionCube
(7.4/8.1), per-service auto-start set, and a privileged helper for password-less nginx.

**To finish promptless auto-start:** Settings ▸ "Enable password-less control" (once) +
Launch-at-login + Start-services-on-launch.

### Next features (later)
- Developer-ID sign + notarize so `.dmg`/`.pkg` open clean on other Macs.
- Optional root LaunchDaemon so nginx starts before login (true headless boot).
- GUI ionCube / php-status panel; per-app nginx rewrite presets; more polish.
