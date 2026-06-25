#!/usr/bin/env bash
#
# setup_env.sh - Create a conda environment for the red-team pipeline.
#
# Creates a conda env (default name "redteam") on Python 3.11 (>= 3.10, compatible with
# all required packages), installs the core dependencies, optionally installs the heavier
# frameworks and ML extras, then verifies the install by importing the core packages and
# running the campaign harness in --dry-run mode.
#
# Usage:
#   bash setup_env.sh [--name NAME] [--python VERSION] [--frameworks] [--ml] [--force]
#                     [--credentials] [--env-out PATH]
#
# Options:
#   --name NAME       Conda environment name (default: redteam)
#   --python VERSION  Python version, must be >= 3.10 (default: 3.11)
#   --frameworks      Also install optional frameworks (garak, deepteam, pyrit), best-effort
#   --ml              Also install sentence-transformers (semantic novelty for autoresearch)
#   --force           Recreate the environment if it already exists
#   --credentials     After install, interactively collect target/judge/HF credentials
#                     into a .env file (target API, judge model, HuggingFace token)
#   --env-out PATH    Where to write the collected .env (default: ./.env)
#
# Output:
#   A ready-to-use conda environment, an optional .env with credentials, and a printed
#   activation command.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="redteam"
PY_VERSION="3.11"
INSTALL_FRAMEWORKS=0
INSTALL_ML=0
FORCE=0
COLLECT_CREDENTIALS=0
ENV_OUT=".env"

usage() {
    # Print usage help extracted from the header and exit.
    sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --name) ENV_NAME="$2"; shift 2 ;;
        --python) PY_VERSION="$2"; shift 2 ;;
        --frameworks) INSTALL_FRAMEWORKS=1; shift ;;
        --ml) INSTALL_ML=1; shift ;;
        --force) FORCE=1; shift ;;
        --credentials) COLLECT_CREDENTIALS=1; shift ;;
        --env-out) ENV_OUT="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

# Verify Python version request is >= 3.10.
PY_MAJOR="${PY_VERSION%%.*}"
PY_MINOR="${PY_VERSION#*.}"; PY_MINOR="${PY_MINOR%%.*}"
if [[ "$PY_MAJOR" -lt 3 || ( "$PY_MAJOR" -eq 3 && "$PY_MINOR" -lt 10 ) ]]; then
    echo "Error: --python must be 3.10 or later (got $PY_VERSION)." >&2
    exit 2
fi

# Locate conda.
if ! command -v conda >/dev/null 2>&1; then
    echo "Error: conda not found on PATH." >&2
    echo "Install Miniconda (https://docs.conda.io/en/latest/miniconda.html) and re-run." >&2
    exit 1
fi
echo "Using $(conda --version)"

# Create or reuse the environment.
if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    if [[ "$FORCE" -eq 1 ]]; then
        echo "Removing existing env '$ENV_NAME' (--force)..."
        conda env remove -y -n "$ENV_NAME"
        conda create -y -n "$ENV_NAME" "python=$PY_VERSION"
    else
        echo "Env '$ENV_NAME' already exists; reusing it (pass --force to recreate)."
    fi
else
    echo "Creating env '$ENV_NAME' on Python $PY_VERSION..."
    conda create -y -n "$ENV_NAME" "python=$PY_VERSION"
fi

# conda run lets us install/verify without sourcing the shell hook.
run() { conda run --no-capture-output -n "$ENV_NAME" "$@"; }

echo "Upgrading pip..."
run python -m pip install --upgrade pip

echo "Installing core requirements..."
run python -m pip install -r "$SCRIPT_DIR/requirements.txt"

if [[ "$INSTALL_ML" -eq 1 ]]; then
    echo "Installing ML extras (sentence-transformers)..."
    run python -m pip install "sentence-transformers>=2.7" || echo "WARN: sentence-transformers failed; autoresearch falls back to token-Jaccard novelty."
fi

if [[ "$INSTALL_FRAMEWORKS" -eq 1 ]]; then
    echo "Installing optional frameworks (best-effort, one at a time)..."
    while IFS= read -r line; do
        pkg="${line%%#*}"; pkg="$(echo "$pkg" | xargs)"
        [[ -z "$pkg" ]] && continue
        echo "  -> $pkg"
        run python -m pip install "$pkg" || echo "WARN: '$pkg' failed to install; skipping (verify the package name/Python compatibility)."
    done < "$SCRIPT_DIR/requirements-frameworks.txt"
fi

echo "Verifying core imports..."
run python -c "import openai, dotenv, yaml, tqdm, tenacity, httpx, aiohttp, rich, pandas, requests; print('core imports OK')"

echo "Running campaign harness dry-run..."
CHECK_DIR="$(mktemp -d)"
if run python "$HOME/.cursor/skills/redteam-campaign/scripts/run_campaign.py" --dry-run --out "$CHECK_DIR/redteam/campaigns" >/dev/null 2>&1; then
    echo "Pipeline dry-run OK"
else
    echo "WARN: dry-run did not complete; check that redteam-campaign is installed at ~/.cursor/skills/."
fi
rm -rf "$CHECK_DIR"

# Optionally collect target/judge/HF credentials into a .env file. Run interactively
# so the operator can type secrets; conda run --no-capture-output forwards the TTY.
if [[ "$COLLECT_CREDENTIALS" -eq 1 ]]; then
    echo
    echo "Collecting credentials into '$ENV_OUT'..."
    run python "$SCRIPT_DIR/collect_credentials.py" --output "$ENV_OUT"
fi

echo
echo "Done. Activate the environment with:"
echo "    conda activate $ENV_NAME"
if [[ "$COLLECT_CREDENTIALS" -eq 0 ]]; then
    echo
    echo "To enter the target API, judge model, and HuggingFace token now, run:"
    echo "    python $SCRIPT_DIR/collect_credentials.py"
fi
