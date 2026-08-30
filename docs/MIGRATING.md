# Migrating to OmniServ

Moving a local site from **XAMPP, WAMP, MAMP, Laragon, Local (by WP Engine / Flywheel),
ServBay, Herd, or Laravel Valet** into OmniServ is the same three steps every time:

1. **Copy the site files** into OmniServ's sites folder
2. **Move the database** into OmniServ's MySQL/MariaDB
3. **Point the app at OmniServ** (database credentials + the new `.test` URL) and add the site

This guide works the same on **macOS and Windows** — only the file paths differ, and both are
listed side by side. You don't need the command line; the GUI does everything. CLI equivalents are
shown for power users.

> **Good to know:** OmniServ never touches your old stack. Copy things over, test, and only remove
> XAMPP/Local/etc. once you're happy. Nothing here is destructive to the source.

---

## Before you start

- Install OmniServ and open it once (macOS: [README](../README.md#macos) · Windows: [README](../README.md#windows)).
- In OmniServ, make sure these services are running (Dashboard → **Start all**):
  - **nginx** (or Apache) — serves the site
  - **MariaDB** — holds the database
  - the **PHP** version your site needs (install more from **Services** / `omniserv install php@8.1`)
- Know where things live:

  | | macOS | Windows |
  |---|---|---|
  | **OmniServ sites folder** | `~/OmniServ/www` | `%USERPROFILE%\OmniServ\www` |
  | **OmniServ data dir** (configs, certs) | `~/.omniserv` | `%LOCALAPPDATA%\OmniServ` |
  | **Database** | `127.0.0.1:3306` (MariaDB) | `127.0.0.1:3306` (MariaDB) |
  | **Default site URL** | `https://<name>.test` | `https://<name>.test` |

  > The exact sites folder is shown in **Settings** — there's an **Open folder** button there.

---

## Step 1 — Copy the site files

Copy your project's **web root** (the folder containing `index.php`, `wp-config.php`, or Laravel's
`public/`) into OmniServ's sites folder as its own subfolder. The subfolder name becomes the site
name and URL — e.g. copying to `…/OmniServ/www/myshop` → `https://myshop.test`.

**Where your files are now**, by source stack:

| Source | macOS | Windows |
|---|---|---|
| **XAMPP** | `/Applications/XAMPP/htdocs/<site>` | `C:\xampp\htdocs\<site>` |
| **WAMP** | — | `C:\wamp64\www\<site>` |
| **MAMP** | `/Applications/MAMP/htdocs/<site>` | `C:\MAMP\htdocs\<site>` |
| **Laragon** | — | `C:\laragon\www\<site>` |
| **Local** (WP Engine/Flywheel) | `~/Local Sites/<site>/app/public` | `C:\Users\<you>\Local Sites\<site>\app\public` |
| **ServBay** | `~/ServBay/www/<site>` | — |
| **Herd / Valet** | the folder you "parked" (often `~/Herd` or `~/Sites/<site>`) | `C:\Users\<you>\Herd\<site>` |

> **Local users:** copy the contents of `app/public` (that's the actual web root) into
> `…/OmniServ/www/<site>` — not the whole `Local Sites/<site>` wrapper.

---

## Step 2 — Move the database

### 2a. Export from your old stack

Pick whichever you have:

- **phpMyAdmin / Adminer** (XAMPP, WAMP, MAMP, Laragon all ship one): open it, select your
  database, **Export → Quick → SQL → Go**. You get a `.sql` file.
- **Local (by WP Engine/Flywheel):** right-click the site → **Open site shell**, then
  `wp db export mysite.sql` (the file lands in the site's `app/public`). Or use Local's Adminer.
- **Command line (any stack):**
  ```bash
  mysqldump -u root -p --single-transaction --default-character-set=utf8mb4 <dbname> > mysite.sql
  ```

> **Avoid garbled accents/emoji (`Kov├ícs`):** always export **and** import as `utf8mb4`. The
> phpMyAdmin route handles this for you. On the command line, keep the `--default-character-set=utf8mb4`
> flag on both the dump and the import.

### 2b. Create the database in OmniServ

**GUI:** **Databases** tab → **New database** → name it (e.g. `myshop`).

**CLI:**
```bash
omniserv db create myshop            # root user, no password
omniserv db create myshop secret123  # or create a dedicated user+password
```

### 2c. Import the `.sql` into it

**GUI (easiest):** open **phpMyAdmin** from OmniServ (Databases → phpMyAdmin, or `omniserv pma`) →
pick your `myshop` database → **Import** → choose `mysite.sql` → **Go**.

**CLI:**
```bash
# uses OmniServ's bundled MySQL client; any mysql client works too
mysql -h 127.0.0.1 -P 3306 -u root --default-character-set=utf8mb4 myshop < mysite.sql
```

---

## Step 3 — Point the app at OmniServ (DB + URL)

OmniServ's database lives at **host `127.0.0.1`, port `3306`, user `root`** (empty password by
default, unless you set one). Update your app's config:

### WordPress — `wp-config.php`
```php
define( 'DB_NAME', 'myshop' );
define( 'DB_USER', 'root' );
define( 'DB_PASSWORD', '' );      // or the password you set in Step 2b
define( 'DB_HOST', '127.0.0.1' ); // not "localhost" — keeps it on TCP
```

If your **domain changes** (e.g. `mysite.local` → `mysite.test`), do a **serialized-safe
search-replace** so widget/theme data doesn't break — pick one:
- **WP-CLI:** `wp search-replace 'https://mysite.local' 'https://mysite.test' --all-tables`
- **Plugin:** *Better Search Replace* → run it across all tables
- Don't do a plain SQL `REPLACE` — it corrupts serialized PHP arrays.

### Laravel — `.env`
```dotenv
APP_URL=https://myapp.test
DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=myshop
DB_USERNAME=root
DB_PASSWORD=
```
Then clear caches: `php artisan config:clear && php artisan cache:clear`.

### Plain PHP
Edit the DB credentials in your app's own config file (`config.php`, `db.php`, `includes/config.php`,
etc.) to the host/user/password above.

---

## Step 4 — Add the site in OmniServ + turn on HTTPS

**GUI:** **Sites** tab → in the top bar type the **site name** (matches the folder from Step 1),
pick the **PHP version**, the **type** (WordPress / Laravel / others) and **nginx/Apache** →
**Add site**. Then click the **lock icon** on that row to issue a trusted SSL cert.

**CLI:**
```bash
omniserv site add myshop --php 8.1 --type wordpress     # creates the vhost + myshop.test host entry
omniserv secure myshop.test                              # trusted local HTTPS
omniserv restart nginx
```

Open **https://myshop.test** — done. ✅

> The first time you issue a cert, OmniServ installs its local Certificate Authority (one click /
> one `sudo`). After that every `.test` site is trusted automatically — no browser warnings.

---

## Node / full-stack apps (Next.js, Nuxt, Vite, Express, Laravel+Vite…)

For JavaScript apps (or a Laravel API + a separate frontend), use a **Node site** instead of a PHP
site — OmniServ reverse-proxies a clean `.test` URL to your dev server, and can run a frontend + a
backend (`api.<name>.test`) together.

**GUI:** **Node** tab → **Add** → set the frontend dir/command/port (and optionally a backend).

**CLI:**
```bash
omniserv nodesite add myapp \
  --fe-dir ~/OmniServ/www/myapp --fe-cmd "npm run dev" --fe-port 3000 \
  --be-dir ~/OmniServ/www/myapp-api --be-cmd "php artisan serve" --be-port 8000 --api /api
omniserv nodesite start myapp
```

---

## Troubleshooting

| Symptom | Cause & fix |
|---|---|
| **White screen / 500 error** | Wrong PHP version for the app. Set it on the site row (or `omniserv site php <name> 8.1`). Old apps often need 7.4 / 8.1. |
| **"Connection refused" / can't reach DB** | MariaDB isn't running (**Start all**), or the app uses `localhost` with a socket — change `DB_HOST` to **`127.0.0.1`**. |
| **Garbled text** (`Ã©`, `Kov├ícs`) | Charset mismatch on import. Re-import as **utf8mb4** (phpMyAdmin Import, or the `--default-character-set=utf8mb4` flag). |
| **Old domain still shows / broken links** | You skipped the URL search-replace — run the serialized-safe replace in Step 3. |
| **404 on every page** | Wrong web root. For Laravel the root must be the `public/` subfolder — set it: `omniserv site root <name> <path>/public`. |
| **WHMCS / ionCube-encoded app errors** | OmniServ auto-enables ionCube on PHP install; if needed run `omniserv php ioncube 8.1` for that version. |
| **Browser still warns "not secure"** | Re-issue the cert (lock icon / `omniserv secure <name>.test`) and restart the browser so it picks up OmniServ's local CA. |

---

## Quick cheat-sheet

```bash
# 1. copy files into  ~/OmniServ/www/<name>   (Windows: %USERPROFILE%\OmniServ\www\<name>)
# 2. database
omniserv db create <name>
mysql -h127.0.0.1 -uroot --default-character-set=utf8mb4 <name> < dump.sql
# 3. fix DB creds + URL in wp-config.php / .env  (DB_HOST=127.0.0.1)
# 4. add + secure
omniserv site add <name> --php 8.1 --type wordpress
omniserv secure <name>.test
# open https://<name>.test
```

Stuck on a specific stack? Open an issue at
<https://github.com/plusemon/OmniServ/issues> with your source stack and the error.
