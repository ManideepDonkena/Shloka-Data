# Apple App Store kit

Everything Apple App Store Connect asks for, formatted and ready to paste.

## 1. App Store Metadata
| Field | Value | Notes |
|---|---|---|
| **App Name** | `Shloka Learn` | 30 characters max |
| **Subtitle** | `Learn Bhagavad-gītā by Heart` | 30 characters max |
| **Bundle ID** | `org.shloka.learn` | Defined in `capacitor.config.json` |
| **SKU** | `shloka-learn-ios` | Unique internal identifier |
| **Primary Category** | `Education` | |
| **Secondary Category** | `Reference` | |
| **Copyright** | `2026 Shloka Learn` | |
| **Privacy Policy URL** | `https://shloka-learn.onrender.com/privacy.html` | Required |
| **Account Deletion URL** | `https://shloka-learn.onrender.com/privacy.html#deleting-your-data` | Required under Guideline 5.1.1(v) |

---

## 2. Description & Keywords

**Keywords (100 characters max, comma-separated):**
```
bhagavad gita,gita,sanskrit,shloka,chanting,sloka,vedic,scripture,meditation,memorization,krishna
```

**Promotional Text (170 characters max):**
Learn Bhagavad-gītā verses the traditional way: listen, repeat, and understand word by word with pronunciation feedback.

**Full Description:**
```
Learn the Bhagavad-gītā the traditional way: listen, repeat, and understand every word.

• All 700 verses of the Gītā (657 verse entries), chanted clearly in classical Sanskrit meter
• Practise by verse, half, quarter (pāda) or single word, with a pause for you to chant back, repeats and build-up
• Every word shows its meaning underneath; turn on "say its meaning" to hear each word explained before you practise
• Sandhi split: see how the chanted words break into their dictionary forms
• Translation and purport for every verse, with a "listen" button
• Mic feedback: chant in your turn and see which words came through clearly and your pace
• Classes on the verse: watch commentaries and word-by-word explanations
• Speed control without changing pitch, "hold the end" for long vowels, text size, dark mode
• Mark verses, track what you have learned, keep a streak and earn stars for clear chanting
• Optional account with a username and password to keep your progress on any device; no e-mail required
• Completely offline for all verses, meanings, and purports
• No ads. No tracking.
```

---

## 3. App Privacy Nutrition Label
| Category | Collected? | Linked to User? | Used for Tracking? | Purpose |
|---|---|---|---|---|
| **Audio Data** | Yes (ephemeral) | **No** | **No** | App Functionality (Mic feedback for chanting practice; recordings are never saved). |
| **User ID / Name** | Optional | **Yes** | **No** | Account Management (only if the user chooses to create an account). |
| **User Content** | Optional | **Yes** | **No** | App Functionality (saved marks, learned verses, practice scores synced across devices). |
| **Diagnostics / Tracking** | **No** | **No** | **No** | None |

---

## 4. App Review Information
- **Sign-in required**: Optional. The app works fully without an account (Guest mode).
  - *Demo account for review:* Username: `reviewer`, Password: `password123` (or leave unchecked as guest mode is full access).
- **Contact Info**: `donkena1234@gmail.com`
- **Review Notes:**
  ```
  Shloka Learn is an educational app for learning the Sanskrit verses of the Bhagavad-gītā.
  
  The microphone is used solely for the interactive "Your turn" chanting feedback feature.
  Audio recorded during practice is processed ephemerally to evaluate rhythm/alignment and is immediately discarded. Recordings are never stored, transmitted for marketing, or retained on servers.
  
  In-app account deletion is accessible under Settings → Student → Delete my account.
  ```

---

## 5. Assets
| Asset | Path | Specs |
|---|---|---|
| **App Store Icon** | `branding/out/app_store_icon_1024.png` | 1024 × 1024 PNG, no transparency |
| **Xcode AppIcon** | `ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png` | 1024 × 1024 PNG |
| **iPhone Screenshots** | App Store Connect requires 6.7" (1290 × 2796) and/or 6.5" (1242 × 2688) | Capture from iOS Simulator or real iPhone |

---

## 6. How to Build & Submit to App Store

### Option A: Using a Mac with Xcode (Recommended)
1. In `android-app/`:
   ```bash
   npm run sync
   npx cap open ios
   ```
2. In Xcode:
   - Click on the `App` project in the left sidebar.
   - In **Signing & Capabilities**, select your **Apple Developer Team**.
   - Set version to `0.3.2` and build to `5` (or match latest).
   - In the target device dropdown, select **Any iOS Device (arm64)**.
   - Go to menu **Product → Archive**.
   - When the Organizer window opens, click **Distribute App** → **App Store Connect** → **Upload**.
3. In [App Store Connect](https://appstoreconnect.apple.com):
   - Create a new app with Bundle ID `org.shloka.learn`.
   - The uploaded build will appear under **TestFlight** in ~10 minutes.
   - Fill in the metadata from above and submit for review.

### Option B: Automated via GitHub Actions (Without a physical Mac)
Because this repository is hosted on GitHub, you can use GitHub's free `macos-latest` runners to build and upload the iOS app directly to TestFlight using Fastlane or an App Store Connect API Key (`.p8`).
