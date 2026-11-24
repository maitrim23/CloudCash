import json, sys, collections
j = json.load(open(sys.argv[1], encoding="utf-8"))
print({k: (v if isinstance(v,str) else type(v).__name__) for k,v in j.items()})
prods = j["products"]
fam = collections.Counter(p["productFamily"] if "productFamily" in p else "?" for p in prods.values())
print(fam.most_common(15))
kind = sys.argv[2]
shown=0
for sku,p in prods.items():
    a=p.get("attributes",{})
    if p.get("productFamily")==kind and shown<2:
        print(json.dumps(p)[:600]); 
        od=j["terms"]["OnDemand"].get(sku)
        print(json.dumps(od)[:900]); shown+=1
