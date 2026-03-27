#!/usr/bin/env sh
set -eu

API_URL="https://api.github.com/repos/whoisjayd/notewise/releases/latest"
INSTALL_DIR="${NOTEWISE_INSTALL_DIR:-$HOME/.local/bin}"
PATH_EXPORT="export PATH=\"$INSTALL_DIR:\$PATH\""

ensure_path() {
  case ":$PATH:" in
    *":$INSTALL_DIR:"*) return ;;
  esac

  for profile in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$profile" ]; then
      if ! grep -F "$PATH_EXPORT" "$profile" >/dev/null 2>&1; then
        printf '\n%s\n' "$PATH_EXPORT" >> "$profile"
      fi
      return
    fi
  done

  printf '%s\n' "$PATH_EXPORT" >> "$HOME/.profile"
}

fetch() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1"
    return
  fi

  if command -v wget >/dev/null 2>&1; then
    wget -qO- "$1"
    return
  fi

  echo "error: curl or wget is required" >&2
  exit 1
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
    return
  fi

  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
    return
  fi

  echo "error: sha256sum or shasum is required" >&2
  exit 1
}

detect_os() {
  case "$(uname -s)" in
    Linux) printf '%s' "linux" ;;
    Darwin) printf '%s' "macos" ;;
    *)
      echo "error: unsupported operating system" >&2
      exit 1
      ;;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64) printf '%s' "x64" ;;
    arm64|aarch64) printf '%s' "arm64" ;;
    *)
      echo "error: unsupported CPU architecture" >&2
      exit 1
      ;;
  esac
}

OS_NAME="$(detect_os)"
ARCH_NAME="$(detect_arch)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM

RELEASE_JSON="$(fetch "$API_URL")"
ASSET_NAME="$(printf '%s' "$RELEASE_JSON" | grep -Eo "notewise-v[^\"]*-${OS_NAME}-${ARCH_NAME}\.(zip|tar\.gz)" | head -n1)"
CHECKSUM_URL="$(printf '%s' "$RELEASE_JSON" | tr ',' '\n' | grep '"browser_download_url"' | grep 'SHA256SUMS.txt' | head -n1 | cut -d '"' -f4)"
ASSET_URL="$(printf '%s' "$RELEASE_JSON" | tr ',' '\n' | grep '"browser_download_url"' | grep "$ASSET_NAME" | head -n1 | cut -d '"' -f4)"

if [ -z "${ASSET_NAME:-}" ] || [ -z "${ASSET_URL:-}" ] || [ -z "${CHECKSUM_URL:-}" ]; then
  echo "error: could not resolve release assets for ${OS_NAME}-${ARCH_NAME}" >&2
  exit 1
fi

ARCHIVE_PATH="$TMP_DIR/$ASSET_NAME"
CHECKSUM_PATH="$TMP_DIR/SHA256SUMS.txt"

fetch "$ASSET_URL" > "$ARCHIVE_PATH"
fetch "$CHECKSUM_URL" > "$CHECKSUM_PATH"

EXPECTED_SUM="$(awk -v target="$ASSET_NAME" '$2 == target || $2 == "*" target { print $1 }' "$CHECKSUM_PATH" | head -n1)"
ACTUAL_SUM="$(sha256_file "$ARCHIVE_PATH")"

if [ -z "${EXPECTED_SUM:-}" ] || [ "$EXPECTED_SUM" != "$ACTUAL_SUM" ]; then
  echo "error: checksum verification failed for $ASSET_NAME" >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
if printf '%s' "$ASSET_NAME" | grep -q '\.zip$'; then
  unzip -qo "$ARCHIVE_PATH" -d "$TMP_DIR/extracted"
else
  tar -xzf "$ARCHIVE_PATH" -C "$TMP_DIR/extracted"
fi

install -m 755 "$TMP_DIR/extracted/notewise" "$INSTALL_DIR/notewise"
ensure_path

printf 'Installed NoteWise to %s/notewise\n' "$INSTALL_DIR"
printf 'Run: notewise version\n'
printf 'Open a new shell or run: %s\n' "$PATH_EXPORT"
