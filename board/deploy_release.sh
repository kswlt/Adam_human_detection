#!/bin/sh
# Run on the board after the container build and unit tests have passed.
set -eu
APP=/userdata/xtapp
STAGE="$APP/release-20260831"
BACKUP="$APP/backup-before-jpeg-config-recovery-20260831"
if [ -e "$BACKUP" ]; then
    if [ "${1:-}" != "--reuse-backup" ]; then
        echo "Backup exists; use --reuse-backup only when continuing this deployment." >&2
        exit 1
    fi
else
mkdir "$BACKUP"
for name in xt_camera xt_radar xt_camera.cpp xt_radar.cpp config.json lidar_intrinsics.json; do
    if [ -f "$APP/$name" ]; then cp -p "$APP/$name" "$BACKUP/$name"; fi
done
cp -p /mnt/system/factory-data/Lixel.yaml "$BACKUP/Lixel.yaml"
cp -p /etc/init.d/S99xtcamera /etc/init.d/S99xtradar "$BACKUP/"
fi
docker cp xtbuilder:/tmp/xtbuild/board/xt_camera "$STAGE/xt_camera.new"
docker cp xtbuilder:/tmp/xtbuild/board/xt_radar "$STAGE/xt_radar.new"
chmod 755 "$STAGE/xt_camera.new" "$STAGE/xt_radar.new"
sha256sum "$STAGE/xt_camera.new" "$STAGE/xt_radar.new"
# Exact process names avoid the legacy camera script's pkill -f matching this shell.
killall xt_camera xt_radar 2>/dev/null || true
sleep 2
mv "$STAGE/xt_camera.new" "$APP/xt_camera"
mv "$STAGE/xt_radar.new" "$APP/xt_radar"
cp "$STAGE/board/src/"* "$APP/"
rm -f /var/run/xt_radar.pid /var/run/xt_camera.pid
/etc/init.d/S99xtradar start
/etc/init.d/S99xtcamera start
sleep 5
echo 'DEPLOYED; factory file must remain unchanged:'
sha256sum /mnt/system/factory-data/Lixel.yaml "$BACKUP/Lixel.yaml"
pidof xt_camera xt_radar
tail -15 "$APP/camera.log"
tail -20 "$APP/xt_radar.log"
