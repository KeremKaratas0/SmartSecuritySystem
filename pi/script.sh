#!/bin/bash

DEVICE_MAC=put_mac_here
OBEX_CHANNEL=put_obex_here
WATCH_DIR="/home/admin/Pictures"
LOG_FILE="/home/admin/Logs"
command -v inotifywait >/dev/null 2>&1 || { echo >&2 "inotifywait not found. Run: sudo apt install inotify-tools"; exit 1; }
command -v obexftp >/dev/null 2>&1 || { echo >&2 "obexftp not found. Run: sudo apt install obexftp"; exit 1; }
echo "[$(date)] Connecting to $DEVICE_MAC" | tee -a "$LOG_FILE"
echo -e "connect $DEVICE_MAC\nquit" | bluetoothctl >/dev/null 2>&1
sleep 2  # Give it a moment to connect
echo "Watching folder: $WATCH_DIR"
inotifywait -m "$WATCH_DIR" -e create -e moved_to --format %w%f |
while read NEW_FILE
do
    if [[ "$NEW_FILE" =~ \.(jpg|jpeg|png|mp4|avi|mov)$ ]]; then
        echo "[$(date)] New file detected: $NEW_FILE" | tee -a "$LOG_FILE"

        # Connect device before sending


        if obexftp --nopath --uuid none --bluetooth "$DEVICE_MAC" --channel "$OBEX_CHANNEL" --put "$NEW_FILE"; then
            echo "[$(date)] Sent successfully: $NEW_FILE" | tee -a "$LOG_FILE"
            rm "$NEW_FILE"
            echo "[$(date)] Deleted: $NEW_FILE" | tee -a "$LOG_FILE"
        else
            echo "[$(date)] Failed to send: $NEW_FILE" | tee -a "$LOG_FILE"
        fi
    fi
done