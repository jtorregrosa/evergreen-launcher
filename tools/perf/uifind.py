#!/usr/bin/env python3
"""Find a view in a `uiautomator dump` XML (read from stdin) and print its center as "x y".

Usage: uifind.py <text-or-content-desc> [occurrence]

Matches the `text` or `content-desc` attribute exactly, then as a case-insensitive prefix.
`occurrence` (1-based, default 1) picks among several matches, in document order.
Exits with status 1 when nothing matches, so callers can fall back or abort.
"""
import re
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    wanted = sys.argv[1]
    occurrence = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    xml = sys.stdin.read()
    nodes = []
    for node in re.findall(r"<node [^>]*>", xml):
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', node))
        bounds = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", attrs.get("bounds", ""))
        if not bounds:
            continue
        x1, y1, x2, y2 = map(int, bounds.groups())
        if x2 <= x1 or y2 <= y1:
            continue
        nodes.append((attrs.get("text", ""), attrs.get("content-desc", ""),
                      (x1 + x2) // 2, (y1 + y2) // 2))

    exact = [n for n in nodes if wanted in (n[0], n[1])]
    loose = [n for n in nodes
             if n[0].lower().startswith(wanted.lower()) or n[1].lower().startswith(wanted.lower())]
    matches = exact or loose
    if len(matches) < occurrence:
        sys.exit(1)
    print(matches[occurrence - 1][2], matches[occurrence - 1][3])


if __name__ == "__main__":
    main()
