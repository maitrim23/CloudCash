import re, sys
path, pat, before, after, limit = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
t = open(path, encoding="utf-8", errors="replace").read()
ms = list(re.finditer(pat, t))
print(f"[{len(ms)} matches for /{pat}/]")
for i, m in enumerate(ms[:limit]):
    a, b = max(0, m.start() - before), min(len(t), m.end() + after)
    print(f"\n--- #{i} @ {m.start()} ---")
    print(t[a:b])
