#!/usr/bin/env python3
"""Summarize `dumpsys gfxinfo <pkg> framestats` dumps.

Usage: framestats.py [-v] <label> <scenario> <dump> [<dump> ...]

Prints one line in the same format as interact.sh, so summ.py can read it:
    label,scenario,frames=N,janky=J (P%),p50=Xms,p90=Xms,p95=Xms,p99=Xms,max=Xms
followed by a stage breakdown of the slow frames (longer than one 60 Hz frame):
    label,scenario,slow=K,avg_ms:<stage>=..,...,dominant:<stage>=count,...

`frames` and `janky` are gfxinfo's own totals, summed over the dumps. Percentiles and stages come
from the per-frame rows (the last 120 frames of each window), so reset gfxinfo before each
repetition and keep repetitions short.

Stages, in frame order:
    wait    IntendedVsync -> HandleInputStart   main thread busy before the frame started
    input   HandleInputStart -> AnimationStart
    anim    AnimationStart -> PerformTraversalsStart
    layout  PerformTraversalsStart -> DrawStart  measure and layout
    draw    DrawStart -> SyncQueued              recording display lists (View.draw)
    syncq   SyncQueued -> SyncStart              RenderThread still busy with the previous frame
    sync    SyncStart -> IssueDrawCommandsStart  includes bitmap uploads
    gpu     IssueDrawCommandsStart -> SwapBuffers  RenderThread issuing GL commands
    swap    SwapBuffers -> FrameCompleted        buffer queue / GPU back-pressure
"""
import re
import sys

FRAME_NS = 1e9 / 60
STAGES = [
    ("wait", "IntendedVsync", "HandleInputStart"),
    ("input", "HandleInputStart", "AnimationStart"),
    ("anim", "AnimationStart", "PerformTraversalsStart"),
    ("layout", "PerformTraversalsStart", "DrawStart"),
    ("draw", "DrawStart", "SyncQueued"),
    ("syncq", "SyncQueued", "SyncStart"),
    ("sync", "SyncStart", "IssueDrawCommandsStart"),
    ("gpu", "IssueDrawCommandsStart", "SwapBuffers"),
    ("swap", "SwapBuffers", "FrameCompleted"),
]
SKIPPED_FRAME = 0x8


def parse(path):
    """Returns (total_frames, janky_frames, [frame dict]) for one dump."""
    total = janky = 0
    frames = []
    header = None
    window = "?"
    in_profile = False
    for raw in open(path, encoding="utf-8", errors="replace"):
        line = raw.strip()
        m = re.match(r"Total frames rendered: (\d+)", line)
        if m:
            total = int(m.group(1))
            continue
        m = re.match(r"Janky frames: (\d+)", line)
        if m:
            janky = int(m.group(1))
            continue
        if "ViewRootImpl@" in line or line.startswith("Window:"):
            window = line.split("/")[-2] if line.count("/") >= 2 else line
            continue
        if line == "---PROFILEDATA---":
            in_profile = not in_profile
            header = None
            continue
        if not in_profile or not line:
            continue
        cells = [c for c in line.split(",") if c != ""]
        if header is None:
            header = cells
            continue
        if len(cells) < len(header):
            continue
        try:
            row = dict(zip(header, (int(c) for c in cells)))
        except ValueError:
            continue
        if row.get("Flags", 0) & SKIPPED_FRAME or not row.get("FrameCompleted"):
            continue
        row["window"] = window
        row["total"] = row["FrameCompleted"] - row["IntendedVsync"]
        frames.append(row)
    return total, janky, frames


def pct(sorted_values, p):
    if not sorted_values:
        return 0
    return sorted_values[min(len(sorted_values) - 1, int(len(sorted_values) * p / 100))]


def main():
    args = sys.argv[1:]
    verbose = False
    if args and args[0] == "-v":
        verbose = True
        args = args[1:]
    if len(args) < 3:
        sys.exit(__doc__)
    label, scenario, paths = args[0], args[1], args[2:]

    total = janky = 0
    frames = []
    for path in paths:
        t, j, f = parse(path)
        total += t
        janky += j
        frames += f

    durations = sorted(f["total"] for f in frames)
    ms = lambda ns: ns / 1e6
    share = 100.0 * janky / total if total else 0.0
    print("%s,%s,frames=%d,janky=%d (%.2f%%),p50=%dms,p90=%dms,p95=%dms,p99=%dms,max=%dms" % (
        label, scenario, total, janky, share,
        round(ms(pct(durations, 50))), round(ms(pct(durations, 90))),
        round(ms(pct(durations, 95))), round(ms(pct(durations, 99))),
        round(ms(durations[-1])) if durations else 0))

    slow = [f for f in frames if f["total"] > FRAME_NS]
    if not slow:
        print("%s,%s,slow=0" % (label, scenario))
        return
    avg = []
    dominant = {}
    for name, start, end in STAGES:
        avg.append("%s=%.1f" % (name, sum(ms(f[end] - f[start]) for f in slow) / len(slow)))
    for f in slow:
        worst = max(STAGES, key=lambda s: f[s[2]] - f[s[1]])[0]
        dominant[worst] = dominant.get(worst, 0) + 1
    print("%s,%s,slow=%d,avg_ms:%s,dominant:%s" % (
        label, scenario, len(slow), ",".join(avg),
        ",".join("%s=%d" % kv for kv in sorted(dominant.items(), key=lambda kv: -kv[1]))))

    if verbose:
        for f in sorted(slow, key=lambda f: -f["total"])[:8]:
            parts = " ".join("%s=%.1f" % (n, ms(f[e] - f[s])) for n, s, e in STAGES)
            print("#   %5.1f ms  %s  [%s]" % (ms(f["total"]), parts, f["window"]))


if __name__ == "__main__":
    main()
