#!/usr/bin/env bash
set -euo pipefail

# Builds the EPANETx CLI executable and installs it into EPANETx/bin.
# This script follows the documented EPANET build flow style:
#   mkdir build
#   cd build
#   cmake ..
#   cmake --build . --config Release

usage() {
  cat <<'EOF'
Usage:
  scripts/build_epanetx_binary.sh [--build-dir <dir>] [--output-name <name>] [--clean]

Options:
  --build-dir <dir>     Build directory to use (default: build-release)
  --output-name <name>  Installed binary name under EPANETx/bin (default: epanetx)
  --clean               Remove build directory before configuring
  -h, --help            Show this help message

Behavior:
  1. Configures EPANETx with CMake using the selected build directory
  2. Builds the epanetx target in Release mode
  3. Copies build/bin/epanetx to EPANETx/bin/<output-name>
  4. Copies runtime library artifacts (for example libepanetx.dylib)
  5. On macOS, adds @executable_path to rpath for local library resolution
EOF
}

BUILD_DIR_NAME="build-release"
OUTPUT_NAME="epanetx"
CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-dir)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: --build-dir requires a value" >&2
        exit 2
      fi
      BUILD_DIR_NAME="$1"
      ;;
    --output-name)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: --output-name requires a value" >&2
        exit 2
      fi
      OUTPUT_NAME="$1"
      ;;
    --clean)
      CLEAN=1
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

if ! command -v cmake >/dev/null 2>&1; then
  echo "ERROR: cmake is required but not found in PATH." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$REPO_ROOT/$BUILD_DIR_NAME"
BIN_DIR="$REPO_ROOT/bin"
SRC_BIN="$BUILD_DIR/bin/epanetx"
DEST_BIN="$BIN_DIR/$OUTPUT_NAME"

if [[ $CLEAN -eq 1 ]]; then
  rm -rf "$BUILD_DIR"
fi

mkdir -p "$BUILD_DIR"

echo "Configuring EPANETx build in $BUILD_DIR..."
(
  cd "$BUILD_DIR"
  cmake -DCMAKE_BUILD_TYPE=Release ..
)

echo "Building epanetx (Release)..."
cmake --build "$BUILD_DIR" --config Release --target epanetx -j

if [[ ! -f "$SRC_BIN" ]]; then
  echo "ERROR: Expected binary not found: $SRC_BIN" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
cp "$SRC_BIN" "$DEST_BIN"
chmod +x "$DEST_BIN"

# Copy any EPANETx shared libraries required at runtime.
if [[ -d "$BUILD_DIR/lib" ]]; then
  for lib in "$BUILD_DIR"/lib/libepanetx.* "$BUILD_DIR"/lib/libepanet2.*; do
    if [[ -f "$lib" ]]; then
      cp "$lib" "$BIN_DIR/"
    fi
  done
fi

# Ensure macOS can resolve shared libraries from the binary's own directory.
if [[ "$(uname -s)" == "Darwin" ]] && command -v install_name_tool >/dev/null 2>&1; then
  install_name_tool -add_rpath "@executable_path" "$DEST_BIN" 2>/dev/null || true
fi

echo "Installed EPANETx binary: $DEST_BIN"
