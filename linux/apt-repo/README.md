# OmniServ apt repository (Phase 1 — native `apt install`)

A GPG-signed apt repository hosted on **GitHub Pages**, so Debian/Ubuntu users can install and
**auto-update** OmniServ with plain `apt` instead of downloading a `.deb` by hand:

```bash
# 1. add the signing key
curl -fsSL https://wpexpertinbd.github.io/OmniServ/omniserv.gpg | sudo gpg --dearmor -o /usr/share/keyrings/omniserv.gpg
# 2. add the repository
echo "deb [signed-by=/usr/share/keyrings/omniserv.gpg] https://wpexpertinbd.github.io/OmniServ stable main" \
  | sudo tee /etc/apt/sources.list.d/omniserv.list
# 3. install + update like any package
sudo apt update && sudo apt install omniserv
sudo apt upgrade omniserv     # future updates
```

The package is `Architecture: all` (pure scripts + Python), so a single build works on **every**
Debian/Ubuntu release — including brand-new ones the Ondřej-style per-series builders can't cover yet.
No new accounts: hosting is GitHub Pages on this repo, and the signing key is generated locally.

---

## How it works

`.github/workflows/apt-repo.yml` runs on every published `linux-v*` release (and on demand). It:
downloads that release's `.deb`, imports the signing key from a secret, runs
`linux/apt-repo/build-repo.sh` (which calls `reprepro` to produce a signed `dists/` + `pool/` tree and
exports the public key as `omniserv.gpg`), then deploys the tree to GitHub Pages.

`build-repo.sh` is self-contained and also runnable locally (see “Local build” below).

---

## One-time maintainer setup (≈5 min, do once)

### 1. Generate the repo signing key (local, no passphrase)
A dedicated key whose only job is signing this repo. No passphrase so CI can sign non-interactively;
the private key is protected by being stored only as an encrypted GitHub secret.

```bash
gpg --batch --gen-key <<'EOF'
%no-protection
Key-Type: RSA
Key-Length: 4096
Name-Real: OmniServ Repository
Name-Email: bdemon00@gmail.com
Expire-Date: 0
%commit
EOF

# export the PRIVATE key — this becomes the GitHub secret
gpg --armor --export-secret-keys bdemon00@gmail.com > omniserv-apt-private.asc
```

### 2. Add the private key as a repository secret
GitHub → repo **Settings → Secrets and variables → Actions → New repository secret**:
- **Name:** `APT_GPG_PRIVATE_KEY`
- **Value:** the entire contents of `omniserv-apt-private.asc` (including the
  `-----BEGIN/END PGP PRIVATE KEY BLOCK-----` lines).

Then **delete the local copy** so it doesn't linger:
```bash
shred -u omniserv-apt-private.asc   # or: rm -P / rm
```

### 3. Enable GitHub Pages with the Actions source
GitHub → repo **Settings → Pages → Build and deployment → Source: GitHub Actions**.
(That's all — the workflow deploys the artifact; you don't pick a branch.)

### 4. Publish the repo the first time
GitHub → **Actions → “Publish apt repo” → Run workflow** (manual `workflow_dispatch`). After it
finishes, the repo is live at `https://wpexpertinbd.github.io/OmniServ/` and every future `linux-v*`
release re-publishes it automatically.

> The user-facing key (`omniserv.gpg`) is **derived from** the signing key and published automatically —
> you never commit any key material to the repo.

---

## Local build (for testing, without CI)

With the signing secret key in your local gpg keyring:

```bash
# build from the newest built .deb into ./public, then eyeball / serve it
bash linux/apt-repo/build-repo.sh public linux/dist/omniserv_*_all.deb
( cd public && python3 -m http.server 8080 )   # then add http://127.0.0.1:8080 as a test repo
```

---

## Notes
- **Rotation:** to rotate the signing key, regenerate (step 1), update the `APT_GPG_PRIVATE_KEY` secret,
  re-run the workflow. Existing users re-import the new `omniserv.gpg` on their next setup; until then
  `apt update` will warn about the changed key — announce rotations.
- **`omniserv self-update`** stays as the manual fallback for anyone not using the repo (and for
  bleeding-edge boxes).
- **Phase 2 (rpm):** Fedora COPR / openSUSE OBS for dnf/zypper distros — blocked on a `platform-rhel.sh`
  engine port first. Tracked separately.
