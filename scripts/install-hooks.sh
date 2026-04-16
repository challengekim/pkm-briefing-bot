#!/usr/bin/env bash
# Install gitleaks pre-commit hook
# Usage: bash scripts/install-hooks.sh

set -euo pipefail

HOOK_PATH=".git/hooks/pre-commit"

cat > "$HOOK_PATH" << 'EOF'
#!/usr/bin/env bash
# gitleaks pre-commit hook
# Blocks commits containing secrets

if command -v gitleaks &>/dev/null; then
    gitleaks protect --staged --config .gitleaks.toml 2>/dev/null || \
    gitleaks protect --staged 2>/dev/null || {
        echo "[pre-commit] gitleaks detected potential secrets. Commit blocked."
        echo "  Run: gitleaks protect --staged --verbose  (for details)"
        exit 1
    }
elif command -v pre-commit &>/dev/null; then
    pre-commit run gitleaks --hook-stage commit
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
