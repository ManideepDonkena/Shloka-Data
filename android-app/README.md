# Android app (Capacitor)

A thin native shell around `poc/learn.html` that **bundles the verses, purports and all 657 chant MP3s** (≈54 MB APK), so practice works offline.
Student sign-in, marks sync and scores use the Render server (`https://shloka-learn.onrender.com`) when online; offline they stay on the device.

Build (needs JDK 21 and the Android SDK with platform 34 + build-tools 34):
```
cd android-app && npm ci
npm run apk        # copies the web files, syncs, runs gradle assembleDebug
# -> android/app/build/outputs/apk/debug/app-debug.apk
```
No local SDK? Run the **Build Android APK** workflow (Actions tab) and download the artifact.

This is a **debug-signed** APK: fine for sideloading to testers (enable "install unknown apps"). For the Play Store you need your own release keystore (never commit it) and a signed AAB (`./gradlew bundleRelease`); the app icon is still Capacitor's default.
The server allows the app's origin (`https://localhost`) for the API through CORS.
