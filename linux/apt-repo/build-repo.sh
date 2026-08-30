#!/usr/bin/env bash
# Build a GPG-signed apt repository from one or more .deb files.
#
# Prereqs: `reprepro` + `gpg` installed, and the OmniServ signing SECRET KEY already imported into the
# gpg keyring (locally: it's in your keyring; in CI: imported from the APT_GPG_PRIVATE_KEY secret).
#
# Usage:  build-repo.sh <output_dir> <deb> [deb ...]
# Output: <output_dir>/{dists,pool,omniserv.gpg,index.html,.nojekyll} — ready to serve as a static site.
set -euo pipefail

OUT="${1:?usage: build-repo.sh <output_dir> <deb> [deb ...]}"; shift
[ $# -ge 1 ] || { echo "error: no .deb files given" >&2; exit 1; }

# The repo's canonical public URL (where GitHub Pages serves this directory).
PAGES_URL="${OMNISERV_PAGES_URL:-https://wpexpertinbd.github.io/OmniServ}"

KEYID="$(gpg --list-secret-keys --with-colons | awk -F: '/^sec:/{print $5; exit}')"
[ -n "$KEYID" ] || { echo "error: no secret signing key found in the gpg keyring" >&2; exit 1; }
echo "==> signing with key $KEYID"

WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/conf"
# reprepro rejects 'all' as an architecture: list the real ones; an Architecture: all .deb is served
# to each of them automatically.
cat > "$WORK/conf/distributions" <<EOF
Origin: Emon Khan
Label: OmniServ
Codename: stable
Suite: stable
Architectures: amd64 arm64
Components: main
Description: OmniServ — free local web server stack (https://github.com/wpexpertinbd/OmniServ)
SignWith: $KEYID
EOF

for deb in "$@"; do
  echo "==> adding $(basename "$deb")"
  reprepro -b "$WORK" includedeb stable "$deb"
done

echo "==> assembling published tree at $OUT"
rm -rf "$OUT"; mkdir -p "$OUT"
cp -r "$WORK/dists" "$WORK/pool" "$OUT"/
gpg --armor --export "$KEYID" > "$OUT/omniserv.gpg"
: > "$OUT/.nojekyll"   # tell GitHub Pages to serve dists/ & pool/ verbatim (no Jekyll processing)

cat > "$OUT/index.html" <<HTML
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OmniServ — apt repository</title>
<style>
 body{font:16px/1.6 system-ui,sans-serif;max-width:760px;margin:3rem auto;padding:0 1rem;color:#1a1a2e}
 h1{margin-bottom:.2rem} .sub{color:#667;margin-top:0}
 pre{background:#0d1117;color:#e6edf3;padding:1rem;border-radius:8px;overflow:auto;font-size:14px}
 code{background:#eef;border-radius:4px;padding:1px 5px} a{color:#0d6efd}
</style></head><body>
<h1>🐧 OmniServ — apt repository</h1>
<p class="sub">Free local web server stack. Install &amp; auto-update natively via <code>apt</code>.</p>
<h2>Install</h2>
<pre># 1. add the signing key
curl -fsSL $PAGES_URL/omniserv.gpg | sudo gpg --dearmor -o /usr/share/keyrings/omniserv.gpg

# 2. add the repository
echo "deb [signed-by=/usr/share/keyrings/omniserv.gpg] $PAGES_URL stable main" \\
  | sudo tee /etc/apt/sources.list.d/omniserv.list

# 3. install
sudo apt update && sudo apt install omniserv</pre>
<h2>Update</h2>
<pre>sudo apt update && sudo apt upgrade omniserv</pre>
<p>Works on any Debian/Ubuntu (the package is architecture-independent).
Source &amp; releases: <a href="https://github.com/wpexpertinbd/OmniServ">github.com/wpexpertinbd/OmniServ</a>.</p>
</body></html>
HTML

echo "==> done. Published tree:"
find "$OUT" -maxdepth 2 -mindepth 1 | sort | sed 's/^/    /'
