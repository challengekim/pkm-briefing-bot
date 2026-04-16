#!/usr/bin/env bash
# Install gitleaks pre-commit hook
# Usage: bash scripts/install-hooks.sh

set -euo pipefail

# Guard: must be run from the git repo root
if [ ! -d ".git" ]; then
    echo "ERROR: Not a git repository. Run from the project root." >&2
    exit 1
fi

mkdir -p ".git/hooks"
HOOK_PATH=".git/hooks/pre-commit"

# Backup any existing hook before overwriting
if [ -f "$HOOK_PATH" ]; then
    BACKUP="${HOOK_PATH}.backup.$(date +%s)"
    cp "$HOOK_PATH" "$BACKUP"
    echo "Backed up existing hook to $BACKUP"
fi

cat > "$HOOK_PATH" << 'EOF'
#!/usr/bin/env bash
# gitleaks pre-commit hook — blocks commits containing secrets

if command -v gitleaks &>/dev/null; then
    if [ -f .gitleaks.toml ]; then
        gitleaks protect --staged --config .gitleaks.toml || {
            echo "[pre-commit] gitleaks detected potential secrets. Commit blocked."
            echo "  Run: gitleaks protect --staged --verbose  (for details)"
            exit 1
        }
    else
        gitleaks protect --staged || {
            echo "[pre-commit] gitleaks detected potential secrets. Commit blocked."
            echo "  Run: gitleaks protect --staged --verbose  (for details)"
            exit 1
        }
    fi
elif command -v pre-commit &>/dev/null; then
    pre-commit run gitleaks --hook-stage pre-commit
else
    echo "[pre-commit] WARNING: gitleaks not installed. Secret scanning skipped."
    echo "  Install: brew install gitleaks"
fi
EOF

chmod +x "$HOOK_PATH"
echo "✓ pre-commit hook installed at $HOOK_PATH"
echo ""
echo "Next steps:"
echo "  1. Install gitleaks: brew install gitleaks"
echo "  2. Test: gitleaks protect --staged --verbose"
