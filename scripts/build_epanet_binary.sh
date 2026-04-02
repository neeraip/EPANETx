#!/usr/bin/env bash
set -euo pipefail

# Bootstraps an EPANET v2.3.5 reference binary locally without requiring an
# existing EPANET checkout. It clones the tagged upstream repo into a temporary
# directory, builds runepanet, copies the binary into EPANETx/bin, and removes
# the temporary clone directory.

usage() {
  cat <<'EOF'
Usage:
  scripts/build_epanet_binary.sh [--output-name <name>] [--keep-temp]

Options:
  --output-name <name>  Output binary name under EPANETx/bin
                        (default: runepanet-epanet-v2.3.5)
  --keep-temp           Keep temporary clone/build directory for debugging
  -h, --help            Show this help message

Behavior:
  1. Clones https://github.com/OpenWaterAnalytics/EPANET at tag v2.3.5
  2. Configures/builds with CMake in Release mode
  3. Copies build/bin/runepanet to EPANETx/bin/<output-name>
  4. Copies runtime library artifacts required by runepanet
     (for example libepanet2.dylib on macOS)
  5. On macOS, adds @executable_path to runepanet rpath
  6. Deletes temporary clone directory unless --keep-temp is set
EOF
}

OUTPUT_NAME="runepanet-epanet-v2.3.5"
KEEP_TEMP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-name)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: --output-name requires a value" >&2
        exit 2
      fi
      OUTPUT_NAME="$1"
      ;;
    --keep-temp)
      KEEP_TEMP=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
  shift
done

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is required but not found in PATH." >&2
  exit 1
fi

if ! command -v cmake >/dev/null 2>&1; then
  echo "ERROR: cmake is required but not found in PATH." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BIN_DIR="$REPO_ROOT/bin"
DEST_BIN="$BIN_DIR/$OUTPUT_NAME"
TMP_DIR="$(mktemp -d -t epanet-ref-235-XXXXXX)"
CLONE_DIR="$TMP_DIR/EPANET"
BUILD_DIR="$CLONE_DIR/build"

cleanup() {
  if [[ $KEEP_TEMP -eq 0 ]]; then
    rm -rf "$TMP_DIR"
  else
    echo "Kept temporary directory: $TMP_DIR"
  fi
}
trap cleanup EXIT

echo "Cloning EPANET v2.3.5 into temporary directory..."
git clone --depth 1 --branch v2.3.5 https://github.com/OpenWaterAnalytics/EPANET "$CLONE_DIR"

echo "Configuring EPANET build..."
mkdir -p "$BUILD_DIR"
(
  cd "$BUILD_DIR"
  cmake -DCMAKE_BUILD_TYPE=Release ..
)

echo "Building runepanet..."
cmake --build "$BUILD_DIR" --config Release --target runepanet -j

if [[ ! -f "$BUILD_DIR/bin/runepanet" ]]; then
  echo "ERROR: Expected binary not found: $BUILD_DIR/bin/runepanet" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
cp "$BUILD_DIR/bin/runepanet" "$DEST_BIN"
chmod +x "$DEST_BIN"

# Copy any EPANET shared libraries required at runtime.
if [[ -d "$BUILD_DIR/lib" ]]; then
  for lib in "$BUILD_DIR"/lib/libepanet2.*; do
    if [[ -f "$lib" ]]; then
      cp "$lib" "$BIN_DIR/"
    fi
  done
fi

# Ensure macOS can resolve shared libraries from the binary's own directory.
if [[ "$(uname -s)" == "Darwin" ]] && command -v install_name_tool >/dev/null 2>&1; then
  install_name_tool -add_rpath "@executable_path" "$DEST_BIN" 2>/dev/null || true
fi

echo "Installed EPANET reference binary: $DEST_BIN"
