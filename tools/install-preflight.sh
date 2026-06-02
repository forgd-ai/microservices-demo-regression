#!/usr/bin/env bash
# Extract the bundled Preflight plugin into the project's .claude/ tree
# and register it in .claude/settings.json so Claude Code loads it on
# the next session. Project-local install; does not touch ~/.claude/.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
ARCHIVE="${REPO_ROOT}/tools/preflight.tar.gz"
PLUGIN_DIR="${REPO_ROOT}/.claude/plugins/preflight"
SETTINGS="${REPO_ROOT}/.claude/settings.json"
MARKETPLACE_ROOT="${REPO_ROOT}/.claude/plugins"
MARKETPLACE_MANIFEST="${MARKETPLACE_ROOT}/.claude-plugin/marketplace.json"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "preflight install: archive not found at $ARCHIVE" >&2
  echo "Are you running this from the workshop repo root?" >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "preflight install: jq is required (used by both this installer and the plugin's stamp checks)." >&2
  echo "Install it with: brew install jq   (macOS)   or   apt-get install jq   (Linux)" >&2
  exit 1
fi

if [[ -d "$PLUGIN_DIR" ]]; then
  echo "preflight install: $PLUGIN_DIR already exists. Re-running will overwrite plugin files but keep your settings.json registration."
  read -r -p "Continue? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
  rm -rf "$PLUGIN_DIR"
fi

echo "Extracting Preflight plugin into $PLUGIN_DIR ..."
mkdir -p "$PLUGIN_DIR"
tar -xzf "$ARCHIVE" -C "$PLUGIN_DIR"

# Make sure all bundled shell scripts are executable on this checkout.
find "$PLUGIN_DIR/scripts" "$PLUGIN_DIR/hooks" -type f -name '*.sh' -exec chmod +x {} +
[[ -f "$PLUGIN_DIR/git-hooks/pre-push" ]] && chmod +x "$PLUGIN_DIR/git-hooks/pre-push"

# Expose the bundled plugin through a project-local marketplace. Claude Code's
# enabledPlugins only accepts "<plugin>@<marketplace>: <bool>", so a raw plugin
# directory path is not a valid enabledPlugins value. The marketplace manifest
# lives in .claude/plugins/.claude-plugin/ and points at the extracted plugin
# via the "./preflight" source (resolved relative to the marketplace root).
mkdir -p "$(dirname "$MARKETPLACE_MANIFEST")"
cat > "$MARKETPLACE_MANIFEST" <<'JSON'
{
  "name": "preflight-local",
  "owner": {
    "name": "forgd"
  },
  "metadata": {
    "description": "Project-local marketplace for the bundled Preflight plugin",
    "pluginRoot": "."
  },
  "plugins": [
    {
      "name": "preflight",
      "source": "./preflight",
      "description": "Gates git push behind automated quality checks with parallel diff triage and style review.",
      "version": "0.1.0",
      "author": {
        "name": "forgd"
      }
    }
  ]
}
JSON

# Register the marketplace and enable the plugin in .claude/settings.json,
# merging with whatever is already there so we don't clobber existing settings.
# del(.enabledPlugins.preflight) drops the bare "preflight" key; enabledPlugins
# only accepts the "<plugin>@<marketplace>" form.
mkdir -p "$(dirname "$SETTINGS")"
if [[ ! -f "$SETTINGS" ]]; then
  echo '{}' > "$SETTINGS"
fi

tmp="$(mktemp)"
jq --arg root "$MARKETPLACE_ROOT" '
  .extraKnownMarketplaces["preflight-local"] = {"source": {"source": "directory", "path": $root}}
  | .enabledPlugins["preflight@preflight-local"] = true
  | del(.enabledPlugins.preflight)
' "$SETTINGS" > "$tmp"
mv "$tmp" "$SETTINGS"

echo
echo "Preflight installed."
echo
echo "What landed:"
echo "  .claude/plugins/preflight/                       plugin tree (manifest, agents, hooks, scripts)"
echo "  .claude/plugins/.claude-plugin/marketplace.json  project-local marketplace manifest"
echo "  .claude/settings.json                            preflight-local marketplace + preflight@preflight-local enabled"
echo
echo "Next steps:"
echo "  1. Restart Claude Code so it picks up the new plugin."
echo "  2. Run  /preflight:preflight  to gate your branch (or  /preflight  if there's no naming collision)."
echo "  3. Run  /preflight:install-preflight-hook  to drop the native git pre-push hook."
echo
echo "To uninstall: delete .claude/plugins/ and remove the preflight-local and"
echo "  preflight@preflight-local keys from .claude/settings.json."
