#!/bin/sh
# Install or update IsGPTNerfed.app from the latest GitHub release, then open it.
#   curl -fsSL https://raw.githubusercontent.com/kiyoakii/is-gpt-nerfed/main/install-app.sh | sh
# curl does not set the quarantine flag, so an app installed this way opens without the Gatekeeper block that a
# browser download of a non-notarized app gets. The archive's sha256 (published next to it) is checked first.
set -eu
REPO="kiyoakii/is-gpt-nerfed"
MIN_MACOS=15
OS_MAJOR="$(sw_vers -productVersion 2>/dev/null | cut -d. -f1)"
case "$OS_MAJOR" in
  ''|*[!0-9]*) ;;   # not macOS, or an unreadable version: let the app itself decide
  *) [ "$OS_MAJOR" -ge "$MIN_MACOS" ] || { cat >&2 <<EOF
IsGPTNerfed.app needs macOS $MIN_MACOS or newer; this Mac runs $(sw_vers -productVersion).
The plugin itself has no such requirement and works on its own, without the menu bar app:
  git clone https://github.com/$REPO ~/is-gpt-nerfed && cd ~/is-gpt-nerfed && ./install.sh
EOF
    exit 1; }
    ;;
esac
JSON="$(curl -fsSL -H 'Accept: application/vnd.github+json' "https://api.github.com/repos/$REPO/releases/latest")" \
  || { echo "cannot read the latest release of $REPO (offline, or the repository is not public yet)" >&2; exit 1; }
pick() { printf '%s' "$JSON" | python3 -c '
import json, sys
d = json.load(sys.stdin); key = sys.argv[1]
if key == "tag": print(d.get("tag_name") or ""); sys.exit()
assets = d.get("assets", [])
zips = sorted((x for x in assets if str(x.get("name", "")).lower().endswith(".zip")),
              key=lambda x: (not str(x.get("name", "")).startswith("IsGPTNerfed"), str(x.get("name", ""))))
if not zips: print(""); sys.exit()
if key == "zip": print(zips[0]["browser_download_url"]); sys.exit()
want = zips[0]["name"] + ".sha256"   # the zip'"'"'s own checksum file, never another asset'"'"'s
print(next((x["browser_download_url"] for x in assets if x.get("name") == want), ""))' "$1"; }
TAG="$(pick tag)"; ZIP_URL="$(pick zip)"; SUM_URL="$(pick sha256)"
[ -n "$ZIP_URL" ] || { echo "release $TAG has no zip attached" >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "downloading IsGPTNerfed $TAG …"
curl -fsSL -o "$TMP/app.zip" "$ZIP_URL"
if [ -n "$SUM_URL" ]; then
  EXPECTED="$(curl -fsSL "$SUM_URL" | awk '{print $1}')"
  ACTUAL="$(shasum -a 256 "$TMP/app.zip" | awk '{print $1}')"
  [ "$EXPECTED" = "$ACTUAL" ] || { echo "checksum mismatch: the archive is not the one the release lists" >&2; exit 1; }
fi
ditto -x -k "$TMP/app.zip" "$TMP/x"
APP="$(find "$TMP/x" -maxdepth 2 -name '*.app' | head -1)"
[ -n "$APP" ] || { echo "no .app inside the archive" >&2; exit 1; }
# keep an existing installation where it is; otherwise /Applications when writable, else ~/Applications
if [ -d "$HOME/Applications/IsGPTNerfed.app" ] && [ ! -d "/Applications/IsGPTNerfed.app" ]; then DEST_DIR="$HOME/Applications"
elif [ -w "/Applications" ]; then DEST_DIR="/Applications"
else DEST_DIR="$HOME/Applications"; fi
mkdir -p "$DEST_DIR"
DEST="$DEST_DIR/IsGPTNerfed.app"
pkill -x IsGPTNerfed 2>/dev/null || true
rm -rf "$DEST"; ditto "$APP" "$DEST"
xattr -dr com.apple.quarantine "$DEST" 2>/dev/null || true
open "$DEST"
echo "installed $TAG to $DEST. Click the face in the menu bar and press Install (once) to register the plugin with Codex."
