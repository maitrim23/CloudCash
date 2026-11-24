import json, sys
p = sys.argv[1]
j = json.load(open(p, encoding="utf-8"))
def show(o, depth=0, maxd=3, key="root"):
    pad = "  " * depth
    if isinstance(o, dict):
        print(f"{pad}{key}: dict[{len(o)}] keys={list(o)[:8]}")
        if depth < maxd:
            for k in list(o)[:3]:
                show(o[k], depth + 1, maxd, k)
    elif isinstance(o, list):
        print(f"{pad}{key}: list[{len(o)}]")
        if o and depth < maxd:
            show(o[0], depth + 1, maxd, key + "[0]")
    else:
        print(f"{pad}{key}: {type(o).__name__} = {str(o)[:80]}")
show(j)
