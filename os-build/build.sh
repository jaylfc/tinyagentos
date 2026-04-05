#!/bin/bash
# Build TinyAgentOS image for a specific board
# Usage: ./build.sh [BOARD] [EXTRA_ARGS...]
#
# Examples:
#   ./build.sh orangepi5plus
#   ./build.sh rock5b BRANCH=current
#   ./build.sh                        # defaults to orangepi5plus

set -euo pipefail

BOARD="${1:-orangepi5plus}"
shift 2>/dev/null || true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ARMBIAN_DIR="$SCRIPT_DIR/../armbian-build"

# Clone Armbian build framework if not present
if [ ! -d "$ARMBIAN_DIR" ]; then
    echo ">>> Cloning Armbian build framework..."
    git clone --depth 1 https://github.com/armbian/build "$ARMBIAN_DIR"
fi

# Copy userpatches into the build tree
echo ">>> Copying TinyAgentOS userpatches..."
cp -r "$SCRIPT_DIR/userpatches" "$ARMBIAN_DIR/"

# Run the build
echo ">>> Building TinyAgentOS image for board: $BOARD"
cd "$ARMBIAN_DIR"
./compile.sh \
    BOARD="$BOARD" \
    BRANCH=vendor \
    RELEASE=bookworm \
    BUILD_DESKTOP=no \
    ENABLE_EXTENSIONS=tinyagentos \
    COMPRESS_OUTPUTIMAGE=sha,gpg,xz \
    "$@"
