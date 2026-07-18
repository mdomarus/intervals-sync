#!/usr/bin/env bash
set -euo pipefail

LABEL="com.michaldomarus.intervals-sync"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
UV_BIN="$(command -v uv)"
LOG="$HOME/Library/Logs/intervals-sync.log"

if [[ -z "$UV_BIN" ]]; then
    echo "error: uv not found in PATH" >&2
    exit 1
fi

if launchctl list "$LABEL" &>/dev/null; then
    launchctl unload "$PLIST"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>$UV_BIN</string>
        <string>run</string>
        <string>intervals-sync</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>$LOG</string>

    <key>StandardErrorPath</key>
    <string>$LOG</string>
</dict>
</plist>
EOF

launchctl load "$PLIST"
echo "Installed and loaded $LABEL"
echo "Logs: $LOG"
