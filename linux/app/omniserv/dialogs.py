"""Dialog helpers and modal dialogs for OmniServ (Site, Database, App, Share, Updates)."""
from __future__ import annotations

import os
import re
import secrets
import threading
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from . import pages as P
from . import updater
from .prefs import cfg_bool


def _first_line(text: str) -> str:
    raw = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    # The engine marks hard errors "✗ …" (its no() helper) and mere warnings "! …". Among the ✗
    # lines, show the LONGEST (last on ties): the explanatory verdict ("PHP 7.4 needs the Ondřej
    # repo, which has no packages for … yet — …") beats both an earlier intermediate warning and
    # the terse post-check tail ("php@7.4 did not install (binary missing)").
    marked = [ln.lstrip("✗ ").strip() for ln in raw if ln.startswith("✗")]
    if marked:
        return max(reversed(marked), key=len)[:240]
    lines = [ln.lstrip("✗!✓ ").strip() for ln in raw]
    # No ✗ marker (non-engine output): prefer an apt 'E:'/'Err:' or a '… failed' line.
    for ln in lines:
        low = ln.lower()
        if ln.startswith(("E:", "Err")) or "failed" in low or "could not" in low or "unable to" in low:
            return ln[:240]
    return (lines[0] if lines else "")[:240]


def _gen_password(n: int = 16) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(n))


def confirm(win, title: str, body: str, on_ok: Callable[[], None]) -> None:
    dlg = Adw.MessageDialog(transient_for=win, heading=title, body=body)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", "Continue")
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
    dlg.set_default_response("cancel")
    dlg.connect("response", lambda d, r: on_ok() if r == "ok" else None)
    dlg.present()


def choose(win, title: str, body: str, options: list[str], on_pick: Callable[[str], None]) -> None:
    if not options:
        win.toast("No options available")
        return
    dlg = Adw.MessageDialog(transient_for=win, heading=title, body=body)
    dd = Gtk.DropDown.new_from_strings(options)
    dlg.set_extra_child(dd)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", "Apply")
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dlg.connect("response", lambda d, r: on_pick(options[dd.get_selected()]) if r == "ok" else None)
    dlg.present()


def run_progress(win, args: list[str], title: str, working: str, ok_msg: str, refresh: bool = True) -> None:
    """Long verb (install/update/uninstall) with a VISIBLE modal progress dialog: an animated
    progress bar + status that stays up the whole time, then flips to '✓ done' / '✗ error' with a
    Close button. Replaces the easy-to-miss 3s toast for slow actions like installing Apache."""
    dlg = Adw.MessageDialog(transient_for=win, heading=title, body=working)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=8)
    bar = Gtk.ProgressBar(show_text=False)
    status = Gtk.Label(label="Working…", xalign=0, wrap=True, css_classes=["dim-label"])
    box.append(bar)
    box.append(status)
    dlg.set_extra_child(box)
    dlg.add_response("close", "Close")
    dlg.set_response_enabled("close", False)      # can't dismiss until it finishes
    dlg.set_close_response("close")
    dlg.connect("response", lambda d, r: win.refresh() if refresh else None)

    src = GLib.timeout_add(110, lambda: (bar.pulse() or True))   # animate while running
    win.spinner.start()
    win._applog(f"{title}…")
    dlg.present()

    def done(rc, out):
        GLib.source_remove(src)
        win.spinner.stop()
        bar.set_fraction(1.0)
        status.remove_css_class("dim-label")
        if rc == 0:
            status.set_label(f"✓ {ok_msg}")
            status.add_css_class("success")
            win._applog(f"✓ {ok_msg}")
        else:
            err = _first_line(out) or f"{' '.join(args)} failed"
            status.set_label(f"✗ {err}")
            status.add_css_class("error")
            win._applog(f"✗ {err}")
        dlg.set_response_enabled("close", True)

    win.engine.run_async(list(args), done, env=None)


def check_updates(win, force: bool = False) -> None:
    if not force and not cfg_bool("auto_update", True):
        return

    def worker():
        local_v = getattr(win, "app_version", None)
        rel, err = (updater.check(force=force, local_ver=local_v) if local_v
                    else updater.check(force=force))
        if rel:
            GLib.idle_add(offer_update, win, rel)
        elif err and force:
            GLib.idle_add(win.toast, f"Update check failed: {err}")
        elif force:
            GLib.idle_add(win.toast, "You're on the latest version.")
    threading.Thread(target=worker, daemon=True).start()


def offer_update(win, rel: dict) -> bool:
    notes = (rel.get("notes") or "A new version is available.").strip()
    dlg = Adw.MessageDialog(transient_for=win,
                            heading=f"OmniServ {rel['version']} is available",
                            body=notes[:400])
    dlg.add_response("later", "Later")
    dlg.add_response("install", "Install update")
    dlg.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
    dlg.connect("response", lambda d, r: do_update(win, rel) if r == "install" else None)
    dlg.present()
    return False


def do_update(win, rel: dict) -> None:
    win.spinner.start()

    def worker():
        ok, msg = updater.download_and_install(
            rel["deb_url"], lambda s: GLib.idle_add(win.toast, s))
        GLib.idle_add(win.spinner.stop)
        GLib.idle_add(win.toast, msg)
    threading.Thread(target=worker, daemon=True).start()


def about_dialog(win) -> None:
    about_win = Adw.AboutWindow(
        transient_for=win,
        application_name="OmniServ",
        application_icon="com.emon.omniserv",
        version=win.app_version,
        developer_name="Emon Khan",
        website="https://emon.bd",
        comments="A free, self-controlled local web server for Linux —\na clean alternative to XAMPP.",
        license_type=Gtk.License.MIT_X11,
    )
    about_win.present()


def add_site_dialog(win, default_type: str = "wordpress") -> None:
    if default_type in ("node", "py"):
        return app_dialog(win, default_type)
    dlg = Adw.MessageDialog(transient_for=win, heading="Add a website",
                            body="Creates the site folder, vhost and *.test domain.")
    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    form.set_margin_top(12)
    form.set_margin_bottom(12)
    form.set_margin_start(12)
    form.set_margin_end(12)
    name = Gtk.Entry(placeholder_text="site name (e.g. myshop)")
    typ = Gtk.DropDown.new_from_strings(["wordpress", "php", "laravel", "others"])
    # Offer only the PHP versions actually installed (so you can't pick one that isn't there);
    # fall back to the full list if none installed yet.
    installed_php = [s["key"].replace("php@", "") for s in win.last_data.get("services", [])
                     if s["role"] == "php" and s["installed"]]
    php_choices = installed_php or [k.replace("php@", "") for k in P.PHP_KEYS]
    php = Gtk.DropDown.new_from_strings(php_choices)
    # Labels are descriptive; the actual --server value is mapped by index below (nginx / apache / ols).
    srv = Gtk.DropDown.new_from_strings(["nginx — serves PHP",
                                         "Apache — + nginx, for .htaccess",
                                         "OpenLiteSpeed — + nginx, .htaccess + LSCache"])
    srv.set_tooltip_text("nginx serves PHP on its own — all you need for PHP/WordPress. "
                         "Apache and OpenLiteSpeed are for sites needing native .htaccess; both run "
                         "behind nginx, so choosing them uses nginx too. OpenLiteSpeed auto-reloads "
                         "on .htaccess changes and supports the LiteSpeed Cache plugin "
                         "(installed automatically on first use).")
    ssl = Gtk.CheckButton(label="Enable trusted HTTPS (mkcert)", active=True)
    dir_entry = Gtk.Entry(placeholder_text="Default folder (optional)", hexpand=True)
    dir_box = Gtk.Box(spacing=6)
    dir_box.append(dir_entry)
    browse_btn = Gtk.Button(label="Browse…", valign=Gtk.Align.CENTER)
    browse_btn.set_tooltip_text("Select project directory")
    dir_box.append(browse_btn)

    for w, lab in ((name, "Name"), (typ, "Type"), (php, "PHP"), (srv, "Web server"), (dir_box, "Location")):
        row = Gtk.Box(spacing=10)
        row.append(Gtk.Label(label=lab, width_chars=10, xalign=0))
        w.set_hexpand(True)
        row.append(w)
        form.append(row)

    def _pick_dir(btn, entry):
        def on_pick(dialog, result):
            try:
                f = dialog.select_folder_finish(result)
                if f:
                    entry.set_text(f.get_path())
            except Exception:
                pass

        dlg = Gtk.FileDialog()
        dlg.set_title("Select project directory")
        dlg.select_folder(win, None, on_pick)

    browse_btn.connect("clicked", _pick_dir, dir_entry)
    form.append(ssl)
    dlg.set_extra_child(form)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", "Create")
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    def resp(d, r):
        if r != "ok":
            return
        nm = name.get_text().strip()
        if not nm:
            win.toast("Enter a site name")
            return
        args = ["site", "add", nm,
                "--type", ["wordpress", "php", "laravel", "others"][typ.get_selected()],
                "--php", php_choices[php.get_selected()],
                "--server", ["nginx", "apache", "ols"][srv.get_selected()]]
        d = dir_entry.get_text().strip()
        if d:
            args += ["--root", d]
        tld = win.last_data.get("config", {}).get("tld", "test")
        run_add_site(win, nm, args, ssl.get_active(), tld)

    dlg.connect("response", resp)
    dlg.present()


def run_add_site(win, nm: str, args: list[str], do_secure: bool, tld: str) -> None:
    """Creates a site with a modal progress dialog so the user gets clear visual feedback."""
    win._applog(f"Creating {nm}…")
    win.spinner.start()

    # ── progress dialog: stays up the whole time, can't be dismissed early ──
    dlg = Adw.MessageDialog(transient_for=win,
                            heading=f"Creating {nm}…",
                            body="Setting up vhost, folder, and TLS certificate. This may take a moment.")
    prog_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=8)
    bar = Gtk.ProgressBar(show_text=False)
    status_lbl = Gtk.Label(label="Working…", xalign=0, wrap=True, css_classes=["dim-label"])
    prog_box.append(bar)
    prog_box.append(status_lbl)
    dlg.set_extra_child(prog_box)
    dlg.add_response("close", "Close")
    dlg.set_response_enabled("close", False)   # disabled until the job finishes
    dlg.set_close_response("close")
    dlg.connect("response", lambda d, r: win.refresh())
    pulse_src = GLib.timeout_add(110, lambda: (bar.pulse() or True))
    dlg.present()

    def finish(ok: bool, output: str) -> None:
        GLib.source_remove(pulse_src)
        win.spinner.stop()
        bar.set_fraction(1.0)
        status_lbl.remove_css_class("dim-label")
        if ok:
            status_lbl.set_label("✓ Site created successfully")
            status_lbl.add_css_class("success")
            win._applog(f"✓ {nm} created")
        else:
            err = _first_line(output) or f"Creating {nm} failed"
            status_lbl.set_label(f"✗ {err}")
            status_lbl.add_css_class("error")
            win._applog(f"✗ {err}")
        dlg.set_response_enabled("close", True)
        # Close the progress dialog and open the result summary
        dlg.close()
        win.refresh()
        site_result_dialog(win, ok, output, nm, tld)

    def after_add(rc: int, out: str) -> None:
        if rc != 0:
            finish(False, out)
        elif do_secure:
            status_lbl.set_label("Securing with mkcert…")
            win.engine.run_async(["secure", f"{nm}.{tld}"],
                                 lambda rc2, out2: finish(True, out + "\n" + out2))
        else:
            finish(True, out)

    win.engine.run_async(list(args), after_add)


def site_result_dialog(win, ok: bool, output: str, nm: str, tld: str) -> None:
    m = re.search(r"https://\S+", output) or re.search(r"https?://\S+", output)
    url = (m.group(0).rstrip(".") if m else f"http://{nm}.{tld}")
    dlg = Adw.MessageDialog(
        transient_for=win,
        heading=("Site created" if ok else "Couldn’t create site"),
        body=(f"{nm}.{tld} is ready." if ok else f"Something went wrong creating {nm}."))
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_size_request(480, -1)   # widen the dialog so long paths read on one/two lines
    if ok:
        box.append(Gtk.Label(label=url, xalign=0, selectable=True,
                              css_classes=["bh-brand"], wrap=True))
    # step lines (✓ / ✗ / ! from the engine output), color-coded
    steps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, css_classes=["card"],
                    margin_top=6, margin_bottom=6, margin_start=10, margin_end=10)
    shown = 0
    cls = {"✓": "bh-step-ok", "✗": "bh-step-err", "!": "bh-step-warn"}
    for raw in output.replace("\r", "").split("\n"):
        t = raw.strip()
        if not t or t[0] not in cls:
            continue
        steps.append(Gtk.Label(label=t, xalign=0, wrap=True, css_classes=[cls[t[0]]]))
        shown += 1
        if shown >= 14:
            break
    if shown:
        sc = Gtk.ScrolledWindow(max_content_height=260, propagate_natural_height=True)
        sc.set_min_content_width(460)
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_child(steps)
        box.append(sc)
    dlg.set_extra_child(box)
    dlg.add_response("close", "Close")
    if ok:
        dlg.add_response("open", "Open site")
        dlg.set_response_appearance("open", Adw.ResponseAppearance.SUGGESTED)
    dlg.connect("response", lambda d, r: P._open(url) if r == "open" else None)
    dlg.present()


def app_dialog(win, kind: str) -> None:
    title = "Add a Node app" if kind == "node" else "Add a Python app"
    dlg = Adw.MessageDialog(transient_for=win, heading=title,
                            body="A managed, supervised app served behind a *.test reverse proxy.")
    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    name = Gtk.Entry(placeholder_text="app name", hexpand=True)
    folder = Gtk.Entry(placeholder_text="/path/to/project", hexpand=True)
    folder_box = Gtk.Box(spacing=8)
    folder_box.append(folder)
    browse_btn = Gtk.Button(label="Browse…", valign=Gtk.Align.CENTER)

    def _pick_folder(btn, entry):
        def on_pick(dialog, result):
            try:
                f = dialog.select_folder_finish(result)
                if f:
                    entry.set_text(f.get_path())
            except Exception:
                pass

        dlg = Gtk.FileDialog()
        dlg.set_title("Select project directory")
        dlg.select_folder(win, None, on_pick)

    browse_btn.connect("clicked", _pick_folder, folder)
    folder_box.append(browse_btn)

    cmd = Gtk.Entry(text="python app.py" if kind == "py" else "npm run dev")
    port = Gtk.SpinButton.new_with_range(1024, 65535, 1)
    port.set_value(8000 if kind == "py" else 3000)
    venv = Gtk.CheckButton(label="Create a virtualenv (.venv)", active=True)
    rows = [(name, "Name"), (folder_box, "Folder"), (cmd, "Command"), (port, "Port")]
    for w, lab in rows:
        row = Gtk.Box(spacing=10)
        row.append(Gtk.Label(label=lab, width_chars=10, xalign=0))
        if w is not folder_box:
            w.set_hexpand(True)
        row.append(w)
        form.append(row)
    if kind == "py":
        form.append(venv)
    dlg.set_extra_child(form)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", "Create")
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    def resp(d, r):
        if r != "ok":
            return
        nm, fd = name.get_text().strip(), folder.get_text().strip()
        if not nm or not fd:
            win.toast("Name and folder are required")
            return
        p = str(int(port.get_value()))
        if kind == "py":
            args = ["pysite", "add", nm, "--dir", fd, "--port", p,
                    "--cmd", cmd.get_text(), "--venv", "yes" if venv.get_active() else "no"]
        else:
            args = ["nodesite", "add", nm, "--fe-dir", fd, "--fe-port", p, "--fe-cmd", cmd.get_text()]
        win.run_verb(args, f"Creating {nm}…")

    dlg.connect("response", resp)
    dlg.present()


def create_db_dialog(win) -> None:
    dlg = Adw.MessageDialog(transient_for=win, heading="Create database", body="")
    form = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    name = Gtk.Entry(placeholder_text="database name")
    eng = Gtk.DropDown.new_from_strings(["mysql", "pg"])
    pw = Gtk.Entry(placeholder_text="user password (MySQL, optional)", hexpand=True)
    pwrow = Gtk.Box(spacing=8)
    pwrow.append(pw)
    gen = Gtk.Button(label="Generate", valign=Gtk.Align.CENTER)
    gen.connect("clicked", lambda *_: pw.set_text(_gen_password()))
    pwrow.append(gen)
    for w, lab in ((name, "Name"), (eng, "Engine")):
        row = Gtk.Box(spacing=10)
        row.append(Gtk.Label(label=lab, width_chars=10, xalign=0))
        w.set_hexpand(True)
        row.append(w)
        form.append(row)
    prow = Gtk.Box(spacing=10)
    prow.append(Gtk.Label(label="Password", width_chars=10, xalign=0))
    prow.append(pwrow)
    form.append(prow)
    dlg.set_extra_child(form)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", "Create")
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    def resp(d, r):
        if r != "ok":
            return
        nm = name.get_text().strip()
        if not nm:
            return
        args = ["db", "create", nm, "--engine", ["mysql", "pg"][eng.get_selected()]]
        env = {"OMNISERV_DB_PASSWORD": pw.get_text()} if pw.get_text() else None
        win.run_verb(args, f"Creating {nm}…", env=env)  # password via env, not argv/ps

    dlg.connect("response", resp)
    dlg.present()


def pw_dialog(win, heading: str, body: str, hint: str, on_apply: Callable[[str], None], apply_label: str = "Apply", initial: str = "") -> None:
    dlg = Adw.MessageDialog(transient_for=win, heading=heading, body=body)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    entry = Gtk.Entry(placeholder_text=hint, text=initial, hexpand=True)
    rowb = Gtk.Box(spacing=8)
    entry.set_hexpand(True)
    rowb.append(entry)
    gen = Gtk.Button(label="Generate", valign=Gtk.Align.CENTER)
    gen.connect("clicked", lambda *_: entry.set_text(_gen_password()))
    rowb.append(gen)
    box.append(rowb)
    dlg.set_extra_child(box)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", apply_label)
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dlg.connect("response", lambda d, r: on_apply(entry.get_text()) if r == "ok" else None)
    dlg.present()


def db_root_dialog(win) -> None:
    # Pass the password via OMNISERV_DB_PASSWORD env, not argv — keeps it out of `ps`.
    _rc, out = win.engine.run("db", "root-status")
    root_status = out.strip().splitlines()[-1].strip() if out.strip() else ""
    is_set = (root_status == "set")

    dlg = Adw.MessageDialog(
        transient_for=win,
        heading="Root password",
        body="Sets or removes the MySQL/MariaDB root password. Leave blank to remove it. Local-dev only.")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_top(12)
    box.set_margin_bottom(12)
    box.set_margin_start(12)
    box.set_margin_end(12)

    old_entry = Gtk.Entry(placeholder_text="Current root password", hexpand=True)
    if is_set:
        old_row = Gtk.Box(spacing=10)
        old_row.append(Gtk.Label(label="Current", width_chars=10, xalign=0))
        old_row.append(old_entry)
        box.append(old_row)

    new_entry = Gtk.Entry(
        placeholder_text="New root password (blank = remove)" if is_set else "New root password",
        hexpand=True)
    new_row_box = Gtk.Box(spacing=8)
    new_row_box.append(new_entry)
    gen = Gtk.Button(label="Generate", valign=Gtk.Align.CENTER)
    gen.connect("clicked", lambda *_: new_entry.set_text(_gen_password()))
    new_row_box.append(gen)

    new_row = Gtk.Box(spacing=10)
    new_row.append(Gtk.Label(label="New", width_chars=10, xalign=0))
    new_row.append(new_row_box)
    box.append(new_row)

    dlg.set_extra_child(box)
    dlg.add_response("cancel", "Cancel")
    dlg.add_response("ok", "Apply")
    dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)

    def resp(d, r):
        if r != "ok":
            return
        old_pw = old_entry.get_text() if is_set else ""
        new_pw = new_entry.get_text()
        msg = ("Removing root password…" if not new_pw else
               ("Changing root password…" if is_set else "Setting root password…"))
        env = {"OMNISERV_DB_PASSWORD": new_pw}
        if old_pw:
            env["OMNISERV_OLD_DB_PASSWORD"] = old_pw
        win.run_verb(["db", "root-passwd"], msg, env=env)

    dlg.connect("response", resp)
    dlg.present()


def db_password_dialog(win, name: str) -> None:
    pw_dialog(
        win,
        f"Set password · {name}",
        f"Creates/updates a dedicated user “{name}” (@localhost + @127.0.0.1) for this database.",
        "new password",
        lambda pw: win.run_verb(["db", "passwd", name, "--engine", "mysql"],
                                 f"Setting password for {name}…",
                                 env={"OMNISERV_DB_PASSWORD": pw}) if pw else None,
        apply_label="Set")


def db_drop(win, name: str, engine: str = "mysql") -> None:
    confirm(
        win,
        f"Drop database “{name}”?",
        f"Permanently drops '{name}' ({'PostgreSQL' if engine == 'pg' else 'MySQL/MariaDB'}). "
        "This cannot be undone.",
        lambda: win.run_verb(["db", "drop", name, "--engine", engine], f"Dropping {name}…"))


def copy_text(win, text: str) -> None:
    try:
        win.get_clipboard().set(text)
        win.toast("Link copied")
    except Exception:  # noqa: BLE001
        pass


def site_share(win, name: str) -> None:
    site = next((x for x in win.last_data.get("sites", []) if x.get("name") == name), None)
    url = (site or {}).get("tunnel", "")
    if url:                       # already sharing → just show the manage sheet
        share_dialog(win, name, url)
        return
    win.toast(f"Starting public share for {name}…")
    win._applog(f"Sharing {name} via Cloudflare…")
    win.spinner.start()

    def done(rc, out):
        win.spinner.stop()
        win.refresh()
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", out)
        if m:
            share_dialog(win, name, m.group(0))
        else:
            err = Adw.MessageDialog(
                transient_for=win, heading="Couldn’t share publicly",
                body=(_first_line(out) or "The tunnel didn’t return a public URL. "
                      "Check Logs and try again."))
            err.add_response("close", "Close")
            err.present()

    # First share auto-downloads cloudflared — can take a few extra seconds.
    win.engine.run_async(["tunnel", "start", name], done)


def share_dialog(win, name: str, url: str) -> None:
    dlg = Adw.MessageDialog(
        transient_for=win, heading=f"Share “{name}” publicly",
        body="Cloudflare Tunnel gives this site a temporary public https address — no account "
             "or port-forwarding. The link works while sharing is on.")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    box.set_size_request(460, -1)
    live = Gtk.Box(spacing=8)
    live.append(Gtk.Label(label="●", css_classes=["dot-on"]))
    live.append(Gtk.Label(label="Live — anyone with this link can reach your site.",
                          xalign=0, css_classes=["bh-step-ok"]))
    box.append(live)
    row = Gtk.Box(spacing=6)
    entry = Gtk.Entry(text=url, hexpand=True)
    entry.set_editable(False)
    row.append(entry)
    cp = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Copy link", valign=Gtk.Align.CENTER)
    cp.connect("clicked", lambda *_: copy_text(win, url))
    row.append(cp)
    ob = Gtk.Button(icon_name="web-browser-symbolic", tooltip_text="Open in browser", valign=Gtk.Align.CENTER)
    ob.connect("clicked", lambda *_: P._open(url))
    row.append(ob)
    box.append(row)
    dlg.set_extra_child(box)
    dlg.add_response("close", "Close")
    dlg.add_response("stop", "Stop sharing")
    dlg.set_response_appearance("stop", Adw.ResponseAppearance.DESTRUCTIVE)
    dlg.connect("response", lambda d, r: win.run_verb(["tunnel", "stop", name],
                f"Stopped sharing {name}") if r == "stop" else None)
    dlg.present()
