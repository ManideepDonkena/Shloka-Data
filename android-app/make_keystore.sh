#!/usr/bin/env bash
# Create the Play Store upload key (once). Keep the .jks file AND the passwords safe and backed up:
# without them you can never publish an update. Never commit them. (Play App Signing keeps Google's own key.)
set -euo pipefail
cd "$(dirname "$0")/android"
KS="${1:-$HOME/shloka-upload.jks}"
read -rsp "Choose a keystore password (6+ chars): " P; echo
keytool -genkeypair -v -keystore "$KS" -alias upload -keyalg RSA -keysize 2048 -validity 10000 -storepass "$P" -keypass "$P"
printf 'storeFile=%s\nstorePassword=%s\nkeyAlias=upload\nkeyPassword=%s\n' "$KS" "$P" "$P" > keystore.properties
chmod 600 keystore.properties
echo "Done. Key: $KS   Settings: android-app/android/keystore.properties (ignored by git). Back up both."
