# Evergreen: the smoothest, best-looking experience on an Android 10 tablet

## Context

You are working on **Evergreen Launcher**, a fork of Lawnchair 15 (AOSP Launcher3 + Quickstep).

**Repository**
- Repo: `github.com/jtorregrosa/evergreen-launcher`. The local checkout is the current directory.
  - Default branch: `evergreen`. Integration branch: `perf/android10`.
  - Work in feature branches, open PRs against `perf/android10`, and merge `perf/android10` into
    `evergreen` when a batch is done.
- The `platform_frameworks_libs_systemui` submodule points to the fork
  `jtorregrosa/platform_frameworks_libs_systemui`, branch `evergreen/15`. Push submodule commits
  there before pushing a gitlink that references them.
- Build with JDK 17+ (Zulu 21 works): `./gradlew assembleLawnWithQuickstepGithubRelease`. The
  applicationId is `io.github.jtorregrosa.evergreen`.
- **Language:** all code, comments, docs, commits and PRs are in **English**. Talk to the user in
  **Spanish**.

**Target device**
- Lenovo Tab M10 FHD Plus (TB-X606F): Helio P22T (8× Cortex-A53), PowerVR GE8320, 4 GB RAM,
  1200×1920 at 240 dpi (≈800×1280 dp, the sw720dp tablet layout), Android 10 (API 29), 3-button navigation.
- Recents are provided by the OEM launcher, so in Evergreen `isRecentsEnabled` is false and app
  open/close animations use the non-recents fallback path.
- **API 29 limits:** no `RenderEffect`, no window/background blur (`DepthController` and blur are
  no-ops), and no `GestureNavContract` on 3-button navigation.

**Read these first**
- `docs/perf/BACKLOG.md`: the verified backlog, plus an "Implementation status" section that lists
  what each PR already did and what is still open.
- `docs/perf/RESULTS.md`: methodology and every number so far.
  - Cold start: ~1.70 s with no AOT, ~1.33 s with full AOT.
  - Drawer jank: 8.5%. Search typing jank: 15.2%. Page swipes: ~0%.
- `tools/perf/README.md`: the on-device measurement scripts. Use them, extend them, and keep their
  output comparable.
**Already decided, don't redo**
- Removing `-dontoptimize` (full R8 optimization) was measured and rejected: ~3% slower cold start
  with full AOT.
- A "Reduce visual effects" switch (single-pass label shadows, no extra blurred shadow pass on
  adaptive icons) was measured and rejected: no gain in jank or cold start, and it looked the same.
  Don't retry cheaper shadows as a smoothness fix. Look for the real long frames instead.

## Goal

Make Evergreen feel as **fluid** as possible on this tablet and look **polished and beautiful**,
without losing what has already been gained. Fluid means:
- every frame of every everyday interaction lands within 16.6 ms, or as close as this GPU allows;
- input responds immediately;
- there is no visible hitch when returning home from an app.

Beautiful means: coherent spacing, typography, icon sizing, colors and motion that suit a large
tablet. Use effects that are cheap on this hardware, not effects that need blur or Android 12+.

## Device protocol (important)

- Use only the device with `ADB_SERIAL=HA12S9CD`. Another phone is attached; never touch it.
- The user's default launcher is their own Lawnchair (`app.lawnchair/.LawnchairLauncher`). Keep it as
  the default HOME. Installing Evergreen can reset HOME on Android 10, so restore it with
  `cmd package set-home-activity app.lawnchair/.LawnchairLauncher` after every install.
- The screen has a secure lock. If `dumpsys window` shows `isStatusBarKeyguard=true`, ask the user to
  unlock it. Never try to unlock it yourself.
  - `svc power stayon usb` only while measuring. `svc power stayon false` when you are done.
- Don't change other system settings (dark mode, animation scale, fonts, display size) without
  asking first. If something needs `setprop` (for example `persist.traced.enable 1` for Perfetto on
  Android 10), ask the user before running it.
- Another session may use the device. If anything looks off (another app in focus, a different
  APK version), stop and ask.
- Before finishing, check that the default HOME is Lawnchair and that `stayon` is off.

## How to work

1. **Baseline.** Build the current `evergreen` release, install it, then run `measure.sh` (verify and
   speed, 8 runs each) and `interact.sh` (3 rounds). Record the numbers.
2. **Extend the measurement** to the interactions still missing, and keep each one as a script:
   - returning home from an app (the non-recents close path);
   - opening an app from home and from the drawer;
   - opening/closing a folder;
   - the long-press menu;
   - scrolling a long drawer;
   - the widget picker;
   - At a Glance and the dock search bar updating.

   Where a gfxinfo summary is not enough, capture Perfetto traces (ask about `persist.traced.enable`
   first) and find the actual long frames: main thread vs RenderThread vs GPU, layout passes,
   inflation, bitmap uploads, overdraw. Check overdraw visually with `debug.hwui.overdraw` (it is
   a setprop, so ask first).
3. **Rank the jank sources** by how often the user hits them multiplied by how bad they are. Use
   subagents for parallel code investigation, one per interaction. Give each one the context above
   and ask for `path:line` evidence. Then verify their claims yourself, on the device where
   possible, before acting on them. Several earlier findings turned out wrong when checked on the
   device.
4. **Visual design pass.** Before changing anything visible:
   - take screenshots of home, drawer, folder, search, long-press menu and settings on the tablet;
   - propose concrete improvements with before/after mockups or screenshots, for example: grid and
     icon sizes for an 800 dp-wide screen, label typography and contrast over the wallpaper, dock
     and search bar proportions, drawer sheet margins, corner radii, colors derived from the
     wallpaper, and motion curves and durations that feel crisp at 60 fps on this GPU;
   - get the user's approval on the direction. Prefer changing **defaults for tablets / modest
     devices** over adding new options, and keep the user's explicit settings untouched.
5. **Implement in small PRs.** Each PR should:
   - do one coherent change;
   - include measured before/after numbers (interleaved rounds against the base build);
   - include before/after screenshots for anything visible;
   - pass `smoke.sh` with no crashes;
   - update `docs/perf/RESULTS.md` and the backlog status.

   Merge when the numbers and the screenshots are good. Don't merge regressions. Record rejected
   experiments in RESULTS.md the same way the R8 one was recorded.
6. **Finish** with a summary for the user, in Spanish: what changed (with numbers and
   screenshots), what was tried and rejected, and what is still open.

## Ground rules

- Measure, don't guess. A change ships only if the device shows it helps, or it fixes a real bug.
- Keep AOSP diffs small and commented (`// Evergreen: …`), so upstream Lawnchair 15 fixes can
  still be merged.
- Never use `--force` on pushes. Don't delete branches you didn't create. Don't touch the user's
  own Lawnchair data or settings.
