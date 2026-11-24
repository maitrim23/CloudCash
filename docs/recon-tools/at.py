import sys
t = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for pos in map(int, sys.argv[2:]):
    print(f"\n=== @{pos} ===\n" + t[pos-1500:pos+1800])
