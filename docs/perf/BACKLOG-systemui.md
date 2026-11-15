# Evergreen: performance backlog for the `platform_frameworks_libs_systemui` submodule

- **Base:** `evergreen` at `1599be8a8f`, submodule `evergreen/15` at `3ed257c`.
- **Scope:**
  - `iconloaderlib` (about 7.7k lines: icon cache, icon rendering, `IconProvider` and Lawnchair's additions in `app/lawnchair/icons`);
  - `animationlib` (interpolators);
  - `searchuilib` (two constant files).

  App code (`src/`, `quickstep/src`, `lawnchair/src`) is cited where it decides how often submodule code runs.
- **Method:** the same as `docs/prompts/perf-backlog-old-devices.md`, adapted to the submodule:
  1. 5 read-only reviews by area.
  2. 3 adversarial verifiers for the high- and medium-impact findings.
  3. Checks on the tablet.
- **Status of each finding:**
  - **CONFIRMED**: the code was read and, where possible, the behaviour seen on the device.
  - **HYPOTHESIS**: needs a measurement.
  - The refuted ones are in section 6.
- **Device:** the same Lenovo TB-X606F as `BACKLOG.md` (Android 10, Helio P22T, 4 GB). It has Google Clock (`com.google.android.deskclock`), Google Calendar and Lawnicons 2.18 installed.

Defaults that decide who is affected (from `lawnchair/src/app/lawnchair/preferences/PreferenceManager.kt`):

| Setting | Default |
|---|---|
| Themed icons (`themed_icons`) | off |
| Icon pack (`pref_iconPackPackage`) | none |
| "Wrap legacy icons" (`prefs_wrapAdaptive`) | off |
| Bulk icon loading for all apps (`pref_allapps_bulk_icon_loading`) | off |
| Contacts, files and settings search | off |
| Notification counts | off |

## 1. Summary

The submodule's runtime code is cheap on the default path: a normal icon is one `drawBitmap`, interpolators do not allocate per frame and `searchuilib` is constants. The heaviest problems are elsewhere:

1. **The release APK's baseline profile has no launcher or submodule classes (SUI-1).** The 12.8 KB `baseline.prof` comes only from library AARs. The app's own profile lives in a source set (`src/lawnWithQuickstepRelease/`) that no variant uses since the `channel` flavor dimension was added, and it dates from December 2023. EVG-4 runs ProfileInstaller, but what it installs does not cover `Launcher`, `Workspace`, the loader or the icon code. This is the biggest item in either backlog.
2. **Changing many settings wipes the whole icon DB and re-renders every icon (SUI-2).** This happens for app renames, folder rows, hotseat columns, label and grid options. The EVG-3h fix only removed the *second* reload.
3. **On a DB miss, workspace icons are rendered twice (SUI-3),** because the bulk-load fallback never stores its result in the memory cache.
4. **Themed icons cost 3 draws per frame instead of 1 and waste a bitmap per view (SUI-6 and SUI-7).** Freshly rendered icons also blend a blank full-size "badge" bitmap.
5. **The animated Google Clock icon (present on this tablet) clips a path and redraws its layer stack every frame (SUI-9),** and is re-inflated on every cold start.

Recommended order:
- SUI-1 first. It changes every cold-start number, so measure the rest after it.
- Then the quick wins SUI-2 and SUI-3.
- Then the themed-icon items, since you plan to use themed icons and icon packs.
- Then SUI-9.

## 2. Epics

| Epic | Scope |
|---|---|
| SUI-E1 | Build and profiles |
| SUI-E2 | Icon cache and DB |
| SUI-E3 | Themed, clock and placeholder drawing |
| SUI-E4 | Rendering and per-bind costs |
| SUI-E5 | Receivers, memory and animationlib |

## 3. Items

Priority = impact / (risk × effort). I/R/E = impact / risk / effort.

### SUI-E1: Build and profiles

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| SUI-1 | **P0** | The shipped APK's baseline profile contains no app or submodule classes | `build.gradle:273` sets 3 flavor dimensions, so `src/lawnWithQuickstepRelease/` matches no variant. `src/lawnWithQuickstepGithubRelease/generated/baselineProfiles/` is empty. The merged `build/intermediates/merged_art_profile/lawnWithQuickstepGithubRelease/.../baseline-prof.txt` (9277 lines) has 0 lines for `com/android/launcher3/Launcher;`, `com/android/launcher3/icons` or `app/lawnchair`. The committed profile is from `31cb3ba4be` (2023-12-06) and still lists the removed `com/android/launcher3/anim/Interpolators`. | Short term: move or copy the profile to `src/lawnWithQuickstepGithubRelease/generated/baselineProfiles/` (or set `baselineProfile { mergeIntoMain = true }`), dropping stale classes. Then regenerate it with the `baseline-profile` module. That module targets a Pixel 6 API 33 managed device; collecting on the API 29 tablet would need root. Extend the generator to cover the drawer, scrolling, search and folders (EVG-4). | H/L/M | **CONFIRMED**. Stopgap done in #29: cold start 1542 → 1242 ms after a speed-profile compile. Regeneration still pending |
| SUI-1b | P3 | Unused submodule code is shipped and kept unobfuscated | `InterpolatorsAndroidX` (0 callers) and `src_full_lib` (`IconFactory`, `SimpleIconCache`, 0 callers; `iconloaderlib/build.gradle:10`) are kept by `proguard.pro:38` `-keep class com.android.** { *; }`. `mapping.txt` shows them unrenamed. | Drop `src_full_lib` from `iconloaderlib/build.gradle`, as Android.bp's `iconloader_base` does. Let R8 remove `InterpolatorsAndroidX` when EVG-5b narrows the keep rule. | L/L/S | CONFIRMED |

**Acceptance for SUI-1:**
- The merged intermediate contains `Lcom/android/launcher3/Launcher;`, `Lcom/android/launcher3/icons/` and `Lcom/android/app/animation/Interpolators;`.
- `assets/dexopt/baseline.prof` grows well beyond 12.8 KB.
- After install plus ProfileInstaller, `dumpsys package dexopt` shows `speed-profile`.
- Interleaved `am start -W` TotalTime is lower in the "fresh install, before background dexopt" state.

### SUI-E2: Icon cache and DB

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| SUI-2 | **P1** | Every `reloadIcons`/`reloadGrid` preference wipes the icon DB and memory cache | `PreferenceManager.kt:37-38`, `ReloadHelper.kt:33-34` → `InvariantDeviceProfile.java:572-587` → `reloadIcons()` or (via LauncherAppState's IDP listener) `refreshAndReloadLauncher()` → `BaseIconCache.java:191-199` (`mIconDb.clear(); ... mCache.clear()`). Affects `customAppName`, `folderRows`, `hotseatColumns`, `drawerListOrder`, `folderApps` and every PreferenceManager2 `reloadGrid` pref. The EVG-3h change (`InvariantDeviceProfile.java:582-586`) only skips the second reload. | Remember `iconBitmapSize`/`fillResIconDpi` in `LauncherAppState`. Call `updateIconParams` only when they, the icon state (pack, shape, theme) or the locale changed; otherwise `mModel.forceReload()`. | H/L/S | **CONFIRMED**, fixed in #32 (rename: 64 → 3 renders) |
| SUI-3 | **P1** | The bulk-load fallback renders missing icons without caching them, so they are rendered again | `IconCache.java:535-566` renders into a new `CacheEntry` that never goes into `mCache`. All apps then misses and renders again through `AllAppsList.java:155` → `cacheLocked` (`BaseIconCache.java:434-458`). Workspace and hotseat apps without a DB row are rendered 2 times (3 with bulk all-apps loading on). Folder items get a full render too. | When the fallback produces a high-res bitmap, put it in `mCache` through a protected helper in `BaseIconCache`. The update handler then only persists it. | H (on a miss) / L / S | **CONFIRMED**, fixed in #32 (pack switch: 61 → 47 renders) |
| SUI-4 | P2 | The update handler fetches every installed package and scans the whole table 4 times per start | `IconCacheUpdateHandler.java:93-98` `getInstalledPackages(MATCH_UNINSTALLED_PACKAGES)` (every package on the device, not just the 35 launchable ones). `:148-153` scans the user's table in each of the 4 `updateIcons` calls (`LoaderTask.java:302, 309, 327, 364`). `IconCache.close()` (`:178`) also builds a handler. | One handler per loader run. Scan the table once and dispatch rows to the four caching logics. Fast path with `PackageManager.getChangedPackages(seq)` when nothing changed. | M/M/M | CONFIRMED. Time: HYPOTHESIS |
| SUI-5 | P2 | Themed icons read from the DB make a binder call and a name lookup per icon | `ThemedIconDrawable.java:207-214`: `getResourcesForApplication(pkg)` plus `getIdentifier(resName, ...)` for every `TYPE_THEMED_V2` blob, reached from `BitmapInfo.java:262-263` via `BaseIconCache.java:685`. | Memoize `Resources` per package and `(pkg, resName) → resId` in `BaseIconCache`. Clear them in `updateIconParamsBg` and on a pack change. | M (themed) / L / S | CONFIRMED (only with themed icons) |
| SUI-5b | P3 | BLOB columns come before label, color, flags and system_state | `BaseIconCache.java:773-786` schema order. `COLUMNS_LOW_RES` (`:747-751`) and the update-handler scan (`IconCacheUpdateHandler.java:149-151`) read columns after the blobs, so SQLite walks each PNG's overflow chain. | Put the BLOB columns last and bump `RELEASE_VERSION` (one-time wipe). Do it together with SUI-4. | M/L/S | CONFIRMED. Gain: HYPOTHESIS |
| SUI-5c | P3 | `allAppsIconBitmapSize` vs `iconBitmapSize` mismatch in the DB version | `IconCache.java:123` opens with `max(iconBitmapSize, allAppsIconBitmapSize)`; `LauncherAppState.java:239-240` reopens with `iconBitmapSize`. A different version drops the table (`SQLiteCacheHelper.java:106-118`). | Pass the same `max(...)` in both places. | H if it triggers / L / S | HYPOTHESIS: harmless with the default profiles (66/66, 57/57). Check `PRAGMA user_version` before and after a reload and a restart |
| SUI-5d | P3 | All-apps icons are looked up with one SQL query per app | `PreferenceManager.kt:102` bulk loading defaults to false; `BaseIconCache.java:641-646` runs a primary-key query per component (about 35). | Enable bulk loading by default **after** SUI-3. | L/L/S | CONFIRMED (a few ms) |
| SUI-5e | P3 | Widget labels are one SQL query per provider at every start | `WidgetItem.java:50, 82` → `IconCache.getTitleNoCache` (`IconCache.java:357-361`), not memory-cached. | One `IN (...)` query in `WidgetsModel.update`, or a label-only map. | L-M/L/M | CONFIRMED |
| SUI-5f | P3 | Deep shortcut icons rendered in popups are never persisted | `PopupPopulator.java:124` → `IconCache.java:287-290`. `addToMemCache=false` (`ShortcutCachingLogic.java:97`) and `cacheLocked` writes no DB row on a miss. | Persist on a miss. | L/M/M | CONFIRMED (re-renders only when a shortcut changes) |

### SUI-E3: Themed, clock and placeholder drawing

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| SUI-6 | **P1** | Themed icons allocate an unused ARGB bitmap and draw a blank full-size badge | `ThemedIconDrawable.java:84, 93` → `CustomAdaptiveIconDrawable.java:331-334` allocates `mLayersBitmap`, but only `getIconMask()` is used (`:103`). `:300, :331` pass `myUserHandle()` to `getUserBadgeBitmap`; for the main user `BaseIconFactory.java:160-167` keeps a blank `mIconBitmapSize` ARGB bitmap, drawn every frame at `:106-107`. This applies to icons rendered in the current process; DB-decoded ones get no badge (`:220-224`). | Allocate `mLayersBitmap` lazily in `draw()` (this also fixes SUI-12). Return null from `getUserBadgeBitmap` when the badged drawable is the input. | M (themed) / L / S | **CONFIRMED**, fixed in #34 |
| SUI-7 | P1 | Each themed icon is drawn as a path, a vector and a bitmap every frame, with a mutated vector per view | `ThemedIconDrawable.java:99-108` (save, scale, `drawPath`, `mMonochromeIcon.draw`, badge). `:82` and `:249` give `getDrawable(resId).mutate()` per instance, so the workspace, drawer and folder copies of one app are rasterized separately. | Rasterize background plus mono once per (ThemedBitmapInfo, colors, size) into a HARDWARE bitmap cached on the info, then draw it like `FastBitmapDrawable` (1 `drawBitmap`). Invalidate the cache on a theme or colour change. | M-H (themed) / M / M | CONFIRMED (op list). Frame cost: HYPOTHESIS |
| SUI-8 | P2 | The themed icon map keeps every pack entry in an ArrayMap for the whole process | `LawnchairIconProvider.kt:392-418` parses each `<icon>` of the pack's `grayscale_icon_map` (Lawnicons: 12,935 entries, from the #27 logs) into an `ArrayMap` (O(n²) inserts). That is about 2.5-3 MB, while only about 35 apps are installed. | Keep only installed packages while parsing (or use a HashMap). Drop the map on `TRIM_MEMORY_UI_HIDDEN`; DB-loaded icons do not need it. | M (themed) / L / S-M | CONFIRMED. Memory: HYPOTHESIS (heap dump) |
| SUI-9 | P2 | The animated clock clips a path and redraws its layers every frame, and is re-inflated every start | `ClockDrawableWrapper.java:584-597` (`drawBitmap(mBG)`, `clipPath(mFullDrawable.getIconMask())`, rotated layer draws). `:517` `canPersist()` returns false, so `forPackage` (`:155-160`) does binder plus inflate at each start. `:577` `mFullDrawable.setBounds` allocates an unused layer bitmap. It applies here: `com.google.android.deskclock` matches `config.xml:40`. | In `run()`, when `applyTime` returns true, compose BG + clip + FG once a minute into a cached bitmap, and have `drawInternal` draw that bitmap. Keep only the mask path. | M/L/M | CONFIRMED (code). Cost, and whether Google Clock ships `LEVEL_PER_TICK_ICON_ROUND` here: HYPOTHESIS |
| SUI-9b | P3 | Clock tick aligned to uptime, one tick per instance | `ClockDrawableWrapper.java:644-646` `scheduleSelf(this, upTime - (upTime % step) + step)`. Clocks on other workspace pages stay visible (`BubbleTextView.java:592-596`). | Align to the wall-clock minute (the hands can lag by up to 59 s today) and share one tick across all instances. | L/L/S | CONFIRMED |
| SUI-10 | P3 | Placeholder-to-icon cross-fade allocates a ColorFilter per frame per icon | `PlaceHolderIconDrawable.java:58-75` (375 ms animator, `new PorterDuffColorFilter` per update) and `:43` (`getShapePath` parses the mask per instance). | Reuse one filter and change its colour through paint alpha. Cache the shape Path statically. Skip the animation below API 30. | L-M/L/S | CONFIRMED. Much rarer since R4c (`prewarmFolders`); remaining cases: folders opened in the first ~1.5 s, widget picker headers |

### SUI-E4: Rendering and per-bind costs

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| SUI-11 | P2 | Freshly rendered icons stay as software ARGB bitmaps in memory | `BaseIconFactory.java:483-486` (MODE_WITH_SHADOW, the default; `setBitmapGenerationMode` has no callers). `BaseIconCache.java:339, 356, 482` store it as is, while DB-loaded icons are HARDWARE (`BitmapInfo.java:252-254`). | After persisting, swap in `bitmap.copy(Config.HARDWARE, false)` in the memory cache when `USE_HARDWARE_BITMAP`. | L-M/L/S | CONFIRMED. Memory and first-draw upload: HYPOTHESIS (`dumpsys meminfo` before and after a pack switch) |
| SUI-12 | P2 | `CustomAdaptiveIconDrawable` allocates a full-size layers bitmap on every bounds change, even for mask-only uses | `CustomAdaptiveIconDrawable.java:331-334`. Hit by `BaseIconFactory.java:375` (1×1, then full size per legacy icon), `:452`, `:509`, `IconNormalizer.java:138`, `DragView.java:278` and SUI-6. | Allocate (or reuse) `mLayersBitmap` lazily in `draw()`. | L/L/S | CONFIRMED, fixed in #34 (with SUI-6) |
| SUI-13 | P3 | `getSharedPreferences` on every icon pref read | `IconPreferences.kt:12` `val Context.prefs get() = applicationContext.getSharedPreferences(...)`. Called per render (`BaseIconFactory.java:363`), per themed bind (`ThemedIconDrawable.java:354`) and from `LawnchairIconProvider.kt`. | Cache the SharedPreferences instance (`lazy`). | L/L/S | CONFIRMED |
| SUI-14 | P3 | `obtainStyledAttributes` and colour-token lookups on every bind | `BitmapInfo.java:176` and `ThemedIconDrawable.java:169` (`GraphicsUtils.getFloat(disabledIconAlpha)`). `ThemedIconDrawable.java:166` `getThemedColors` (pref read plus 2 `resolveColor`). | Cache `disabledIconAlpha` per theme; cache the themed `int[]` and invalidate on a theme or uiMode change. | L/L/S | CONFIRMED |
| SUI-15 | P3 | Per-render theme lookup allocates even with theming off | `IconProvider.java:222, 228` (`new ComponentName`), `:172` (`dynamicCalendars.stream().anyMatch(...)`), `:192` (`getIdentifier("themed_icon_calendar_" + day)`), `:333` (`obtainTypedArray` without `recycle()`). | Short-circuit when `!isThemeEnabled()`. Use a `HashSet` of calendar packages; cache the calendar resId per day; recycle the TypedArray. | L/L/S | CONFIRMED |
| SUI-16 | P3 | "Wrap legacy icons" runs a full Palette per icon and normalizes twice | `IconPreferences.kt:23` `Palette.Builder(drawableToBitmap(icon)).generate()`; `BaseIconFactory.java:377, 392` (two `getScale`). | Use `ColorExtractor.findDominantColorByHue`; drop the second `getScale`. | L (opt-in) / L / S | CONFIRMED |
| SUI-17 | P3 | Search results from opt-in providers rebuild their icon on every keystroke | `SearchResultIcon.kt:165` (`postAtFrontOfQueue`), `:241-256`; `BaseIconFactory.java:423-428` (`badgeBitmap` → `recreateIcon` blur). The EVG-10d cache only covers `TYPE_RESOURCE`, not contact photos, initials or file thumbnails. | Extend the LruCache key to bitmap icons (target id + URI). Draw the badge composite in software without `recreateIcon`. | L (opt-in) / L / S | CONFIRMED (only with contacts or files search on) |
| SUI-18 | P3 | Small allocations per draw in dots and badges | `DotRenderer.java:146` (`getClipBounds()`), `:178, :219` (Palette contrast per draw with counts on). `UserBadgeDrawable.java:108` (`Color.valueOf` per draw). `FastBitmapDrawable.java:355-371` (new `ColorMatrixColorFilter` per `updateFilter`). | Reuse a Rect, precompute the counter colour, use int colour math, keep static disabled filters. | L/L/S | CONFIRMED |

### SUI-E5: Receivers, memory and animationlib

| ID | P | Title | Evidence | Proposal | I/R/E | Status |
|---|---|---|---|---|---|---|
| SUI-19 | P2 | Folder animations re-inflate XML interpolators on every open and close | `FolderAnimationManager.java:117-122`: 3 `AnimationUtils.loadInterpolator` calls, constructed on open (`Folder.java:765`) and close (`:919`). `Folder.java:805` loads `fast_out_slow_in` in each open's `onAnimationEnd`. Same pattern: `QuickstepTransitionManager.java:313-315`, `WidgetsFullSheet.java:648`. | Use the `Interpolators` singletons (`STANDARD`, `STANDARD_ACCELERATE`, `LEGACY`, `EMPHASIZED`, `LEGACY_DECELERATE`, same curves). Make `large_folder_preview_item_open` a static `PathInterpolator(0, 1, 0.5, 1)`. | L-M/L/S | CONFIRMED, fixed in #34 (no measurable frame change) |
| SUI-20 | P3 | `Interpolators` builds 27 PathInterpolators eagerly, 5 of them duplicates | `animationlib/.../Interpolators.java`: `STANDARD = AGGRESSIVE_EASE`, `LEGACY = CONTROL_STATE`, `LEGACY_ACCELERATE = ACCELERATED_EASE = ALPHA_IN`, `LEGACY_DECELERATE = DECELERATED_EASE`. | Alias the duplicates. After SUI-1 the `<clinit>` is AOT-compiled anyway. | L/L/S | CONFIRMED |
| SUI-21 | P3 | Time/date receivers registered twice; pack clock and calendar fan-out | `IconProvider.java:401-411`, from `LauncherAppState.java:165` and from `RecentsModel.java:89, 133` (created unconditionally by `QuickstepLauncher.java:266` even with recents off; its callback only clears the task icon cache). `LawnchairIconProvider.kt` `CalendarAndClockChangeReceiver` posts one task per pack clock/calendar per user and `loadBlocking()`s the pack. | Do not register `RecentsModel`'s listener when recents are disabled. Deduplicate pack components to installed packages; skip calendar refreshes when `getDay()` did not change. | L/L/S | CONFIRMED. Frequency is low (daily DATE_CHANGED, TIME_SET) |

### Correctness bugs found on the way (not performance)

| ID | Bug | Evidence | Fix |
|---|---|---|---|
| SUI-B1 | A work-profile icon can get the main user's blank badge, or the reverse | `BaseIconFactory.java:161` caches `mUserBadgeBitmap` per pooled factory, regardless of `user` | Fixed in #34: the cache is keyed by user |
| SUI-B2 | Themed icons ignore fade alpha | `FastBitmapDrawable.setAlpha` (`:184-187`) sets it on `mPaint`, which `ThemedIconDrawable.java:102` `mPaint.setColor(colorBg)` overwrites; the mono drawable never gets it | Apply the alpha after `setColor` and to the mono drawable |
| SUI-B3 | `LauncherIcons.mMonoIconEnabled` hides `BaseIconFactory.mMonoIconEnabled` | `LauncherIcons.java:63` vs `BaseIconFactory.java:102`; `BaseIconFactory.java:262` and `ClockDrawableWrapper.java:375` always read false | Remove the shadowing field. It has no effect on API 29 (`ATLEAST_T` paths) |

| SUI-B4 | Icon-rendering settings (wrap legacy icons, transparent background, background shadow, background lightness, tint icon pack backgrounds) did not reach cached icons | They only recreated the activity, which re-rendered icons only while upstream wiped the cache on every `onCreate` (removed by EVG-1) | Reload icons from those preferences (fixed in #32) |

### Measurement items

| ID | What | How |
|---|---|---|
| SUI-M1 | Icon DB journal mode, and whether full rebuilds are fsync-bound (each icon is its own auto-commit insert, `SQLiteCacheHelper.java:55-61`) | On device, `PRAGMA journal_mode` via `dumpsys dbinfo io.github.jtorregrosa.evergreen`. Time a full re-render with and without one transaction per 20 inserts |
| SUI-M2 | Whether one HARDWARE bitmap per icon limits batching on the PowerVR driver (the code does not support the claim) | A/B `USE_HARDWARE_BITMAP = false` below API 30; `ab.sh` drawer scroll, plus Perfetto RenderThread `flush commands` |
| SUI-M3 | Real frame cost of themed icons (SUI-6, SUI-7) and of the animated clock (SUI-9) | `ab.sh` drawer and home with themed icons on/off, and with the clock page vs a page without it |
| SUI-M4 | Real startup cost of SUI-4 | Perfetto with `Trace.beginSection` around `getInstalledPackages` and each `updateIcons` |

## 4. Quick wins (first PRs)

1. **SUI-1 (stopgap):** wire the existing profile into the GitHub release variant, minus stale classes, and check the merged intermediate. Regeneration is a second PR.
2. **SUI-2:** reload icons only when icon parameters or icon state changed.
3. **SUI-3:** put bulk-fallback renders in the memory cache.
4. **SUI-6:** lazy `mLayersBitmap` (covers SUI-12) and no blank badge for the main user (with SUI-B1).
5. **SUI-19:** reuse the `Interpolators` singletons in folder and transition code.

## 5. Baseline measurement plan

Use the existing scripts in the scratchpad pattern (`ab.sh`, `scenario.sh`, `framestats.py`), interleaved, on the GitHub release APK:

- **SUI-1:**
  - `cmd package compile --reset io.github.jtorregrosa.evergreen`, install, wait 5 s for ProfileInstaller, then `dumpsys package dexopt | grep -A3 evergreen`.
  - 3×3 interleaved `am start -W` TotalTime against the current APK.
  - Repeat after `cmd package bg-dexopt-job`.
- **SUI-2 and SUI-3:** add a temporary log counter in `LawnchairIconProvider.getIconWithOverrides` (as in #27). Count renders after:
  - renaming one app;
  - changing folder rows;
  - a cold start with the DB deleted (Evergreen test data only).
- **SUI-6 to SUI-9:** with themed icons on:
  - `ab.sh` drawer and home swipe scenarios;
  - `dumpsys meminfo` (Graphics, Native);
  - a heap dump for SUI-8.
- Record TotalTime, janky %, p90/p99 and the render count in `docs/perf/RESULTS.md`.

## 6. Discarded or corrected

| Finding | Reason |
|---|---|
| Adaptive icons are shadowed twice (D-4) | Already measured as EVG-1d / EVG-21: removing the second pass gave no measurable gain |
| `sMaskId` race makes the startup icon state mismatch (A-10) | The #27 logs show the state string starting with the mask (`M50 0A50 ...`) from the first cold start, on every run |
| `ACTION_OVERLAY_CHANGED` can never change the state (part of D-8) | `sMaskId` changes with the icon shape (`PreferenceManager2.kt:788`). The receiver is mostly redundant, not dead |
| Search action icons are rebuilt per keystroke by default (B-1) | Default rows (apps, StartPage suggestions, web) use `TYPE_RESOURCE` icons covered by the EVG-10d cache. Only opt-in providers remain (SUI-17) |
| `src_full_lib` is removed by R8 (D note) | `mapping.txt` shows `IconFactory` and `SimpleIconCache` kept (SUI-1b) |
| Build config of animationlib and searchuilib costs runtime (E-5) | Single resolved `core-ktx`, no packaged tests, constants inlined; no action |

Corrections to `BACKLOG.md`:
- **EVG-4:** the profile is *not* packaged. The 12.8 KB `baseline.prof` comes only from libraries. See SUI-1.
- **EVG-3h:** the merged change only removed the double reload. Icons are still wiped on every grid or preference change. See SUI-2.

## 7. Risks and things not to touch

- `iconloaderlib` is AOSP code that Lawnchair already diverges from. Keep changes small, mark them `Evergreen:`, and keep the DB schema version logic intact. SUI-5b needs a `RELEASE_VERSION` bump, which wipes the icon DB once.
- SUI-7 and SUI-9 change how themed and clock icons are produced. Compare screenshots before and after (light/dark, work profile, drag).
- SUI-1: a stale or wrong profile is harmless at runtime (ART ignores missing classes), but regenerating needs a managed API 33 emulator or a rooted device.
- Do not change shadow or visual defaults without a measured gain (see EVG-1d).
