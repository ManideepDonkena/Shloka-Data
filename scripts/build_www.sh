#!/usr/bin/env bash
# Copy only what the app needs into android-app/www (the web assets Capacitor bundles into the APK).
set -euo pipefail
cd "$(dirname "$0")/.."
W=android-app/www
rm -rf "$W" && mkdir -p "$W"
# Bundles the web shell, verses, purports and lecture mappings. Audio remains on-demand and cached.
cp poc/learn.html poc/feedback.js poc/student.js poc/privacy.html poc/tts_data.json poc/purports.json "$W"/
cp -r poc/lectures "$W"/
echo "www: $(du -sh "$W" | cut -f1) (shell, verses, purports & lectures)"
cat > "$W/index.html" <<'H'
<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Shloka Learn</title>
<script>location.replace('learn.html?src=tts')</script>
H
