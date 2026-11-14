# Evergreen performance review and backlog for old or low-resource devices

## Context

- Repository: Evergreen Launcher, in this folder, branch `perf/android10`.
  - It is a fork of Lawnchair 15 (tag `v15.0.0-beta3.0`), itself based on AOSP Launcher3 with Quickstep.
  - Lawnchair's own code is in `lawnchair/src/app/lawnchair`.
  - The AOSP code is in `src/`, `quickstep/src`, `systemUI/` and `wmshell/`.
  - The icon libraries are in `platform_frameworks_libs_systemui/` (for example, `iconloaderlib`).
- Target device: old tablet with Android 10 (API 29).
  - Low-end CPU, 2-3 GB of RAM, eMMC storage.
  - Large screen, so many icons are visible at once.
  - The secondary target is any device with API 26-30 or with `ActivityManager.isLowRamDevice()`.
- API 29 constraints to keep in mind:
  - There is no `RenderEffect` and no window blur (`BlurUtils`/`DepthController` require R or higher).
  - ART's compilation model depends on a profile being installed, because the APK does not come from Play.
  - Quickstep is enabled with `QUICKSTEP_MIN_SDK = 29`.
- Starting point: `PERF_ANDROID10.md` contains a previous audit (about 30 findings with file and line).
  - Use it as a seed, but **verify each finding against the current code** before moving it to the backlog.
  - Discard or correct the ones that do not hold up.

## Goal

Do an exhaustive, **read-only (do not edit code)** review and produce a prioritized, actionable backlog of performance improvements for this device profile.

The backlog has two destinations:
- to become GitHub issues;
- to be implemented in small PRs, each one measurable on its own.

## How to work

### Phase 1. Parallel review with subagents

In a single message, launch one `Explore` subagent per area in the table, with "very thorough" thoroughness. Each subagent's prompt must include:
- the context above;
- its area and the guiding questions;
- the evidence rule;
- the finding format.

No subagent edits files.

| Area | Guiding questions |
|------|----------------|
| A. Cold start and process | What runs in `MainProcessInitializer`, `LawnchairApp`, `LauncherAppState`, `LawnchairLauncher.onCreate`/`onResume`, `LoaderTask` and in the providers. What is eager work that could be lazy. Whether the baseline profile and ProfileInstaller actually reach ART. |
| B. Main thread and storage | Uses of `firstBlocking`/`runBlocking`/`setBlocking` and of SharedPreferences, DataStore, Room and files on the main thread. How often each one is called: startup, per frame, per touch or per icon. Synchronous binder calls (PackageManager, AppWidgetManager, ShortcutManager…). |
| C. Icons and icon packs | Validity and invalidation of the icon cache, `appfilter` parsing, themed icons, software shadows and blur, bitmap sizes, threads involved, clock icons and receivers that force updates. |
| D. Drawer, desktop and scrolling | RecyclerView configuration (pool, prefetch, `setHasFixedSize`), folder and category recycling, overdraw on tablet, cost of `onDraw`/`onLayout` in `BubbleTextView`/`CellLayout`/`Workspace`, per-frame memory allocations, cost of dragging and reordering. |
| E. Search | Threads, debounce and cancellation, cost of fuzzy matching, providers (apps, contacts, files, settings, web, calculator) and whether any of them blocks app results, IPC and MediaStore queries per keystroke. |
| F. Animations, transitions and Quickstep on API 29 | Software layers (`setLayerType`), properties that trigger layout during animations, app close animations, recents and QuickSwitch on 29, `DepthController`, springs, animated widgets. |
| G. Memory and low RAM | Behavior in `onTrimMemory`/`onLowMemory`, cache sizes (icons, widgets, previews, fonts), view retention and leaks (listeners that are not unregistered), cost of recreating after a low-memory kill, use of `isLowRamDevice`. |
| H. Background work and battery | Dynamic receivers and their frequency (TIME_TICK, package changes…), WorkManager and alarms, smartspace, weather and feed, network requests (`lawnchair.app`, GitHub, web suggestions), wakeups. |
| I. Build and packaging | R8 and minify in release, proguard rules, `profileinstaller`, `baselineProfiles` per variant, `debuggable`/`profileable`, resources and ABIs, `coreLibraryDesugaring`, use of Compose outside settings. |

**Evidence rule.** Each finding must cite `path:line` and a short excerpt that the subagent has actually read. If the conclusion depends on runtime behavior that cannot be seen in the code, mark it as `HYPOTHESIS` and say which measurement would confirm it. No generic findings like "use coroutines".

**Finding format for each subagent** (return at most about 1200 words):
```
- id: <AREA>-<n>
  title: <one line>
  evidence: <path:line> — <excerpt or precise description>
  frequency: startup | per frame | per touch | per keystroke | per icon | periodic | rare
  why it hurts on API 29 / low RAM: <concrete mechanism>
  proposal: <concrete change>
  impact: high | medium | low   risk: high | medium | low   effort: S | M | L
  status: CONFIRMED | HYPOTHESIS
```

### Phase 2. Adversarial verification

When the subagents come back:

1. **Deduplicate.** Merge findings repeated across areas, especially those from B, which show up in almost all of them.
2. **Verify.** For each high- or medium-impact finding, launch one verifier subagent per group of about 5 findings. Its job is to try to **refute** them by reading the code:
   - does the path actually run?
   - is the frequency what is claimed?
   - is there already a cache or a guard that prevents it?

   Its verdict must be `CONFIRMED`, `REFUTED` or `HYPOTHESIS`, with its own citation.
3. **Discard** the refuted ones and note why in a separate section.
4. **Check the default values.** For each finding, look at the default value of the setting involved (for example, in `lawnchair/res/values/config.xml`). A problem that affects all users is not the same as one that only affects whoever enables an option.

### Phase 3. Backlog

Write `docs/perf/BACKLOG.md` (and optionally `docs/perf/backlog.csv` to import as issues) in English, with this structure.

1. **Summary.** About 10 lines with the 5 heaviest problems and the recommended order of attack.
2. **Epics.**
   - EVG-E1: Cold start.
   - EVG-E2: Main thread and storage.
   - EVG-E3: Icons.
   - EVG-E4: Drawer and desktop smoothness.
   - EVG-E5: Search.
   - EVG-E6: Animations.
   - EVG-E7: Memory and low RAM.
   - EVG-E8: Background and battery.
   - EVG-E9: Build and profiles.
   - EVG-E10: "Modest device" mode. It is a set of default values applied when `isLowRamDevice` is true or the SDK is lower than 31, configurable from the settings.
3. **Items.** One table per epic, sorted by priority = impact / (risk × effort). Each item has:
   - `ID` (EVG-123), title, epic, priority P0-P3, impact, risk, effort S/M/L;
   - evidence (`path:line`) and status (CONFIRMED/HYPOTHESIS);
   - a concrete **technical proposal**;
   - a **measurable acceptance criterion**, for example "`am start -W` TotalTime −20 % cold in `verify` state" or "0 `firstBlocking` calls in `updateHeaderScroll`";
   - **how to measure it** (exact command);
   - dependencies between items and whether it changes anything visible or any default value (and, if so, whether it goes behind "modest device" mode).
4. **Quick wins.** P0/P1 items with effort S and low risk, meant for the first PR.
5. **Baseline measurement plan.** What needs to be measured on the tablet before touching anything:
   - `am start -W` in the `verify` and `speed-profile` compilation states;
   - Perfetto on Android 10 (`setprop persist.traced.enable 1`) with the specific categories and scenarios;
   - `dumpsys gfxinfo` with automated swipes;
   - overdraw;
   - `meminfo` and `am_proc_died`.

   Always with a release APK that has `profileable`, never with a debug one. State which metrics to record in a reference table.
6. **Discarded.** The refuted findings and the reason.
7. **Risks and things that must not be touched.** For example, divergences from AOSP that would make it harder to pull in fixes from the 15 branch, and visible appearance changes.

## Rules

- Do not edit code or make commits. The only file you may write is the backlog, in `docs/perf/`.
- Always distinguish CONFIRMED from HYPOTHESIS, and do not inflate impact without evidence.
- Prioritize small, isolated and reversible changes. Each item must fit in one PR.
- If something can only be decided by measuring, turn it into a measurement item (EVG-Mx) instead of assuming the result.
- When you finish, give me in the chat:
  - the summary;
  - the first 5 quick wins;
  - how many findings were confirmed, how many were refuted and how many remained as hypotheses.
