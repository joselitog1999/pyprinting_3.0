import re, collections, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
p = r"C:\Users\josel\AppData\Local\Temp\claude\c--Users-josel-Documents-Obsidian-Vault-printing3\afba3773-d2e9-4849-aed3-3e531a30c567\scratchpad\auditoria\L8_cristalografia_2.md"
rows = [l for l in open(p, encoding="utf-8") if l.startswith("| L8-")]
order = ["CITA ERRÓNEA", "CONTRADICHO", "SIN FUENTE", "REQUIERE BANCO", "UNSTATED_ASSUMPTION", "ALTERNATIVE_MODEL", "CONFIRMADO"]
vc, sc = collections.Counter(), collections.Counter()
hi = []
per_doc = collections.Counter()
for r in rows:
    cells = [c.strip() for c in re.split(r"(?<!\\)\|", r)[1:-1]]
    rid, loc, claim, ver, sev = cells[0], cells[1], cells[2], cells[3], cells[4]
    # primary verdict = earliest occurring label in the cell
    pos = {lab: ver.find(lab) for lab in order if lab in ver}
    prim = min(pos, key=pos.get) if pos else "?"
    vc[prim] += 1
    s = sev if sev in ("CRÍTICA", "ALTA", "MEDIA", "BAJA") else "—"
    sc[s] += 1
    per_doc[rid.split("-")[1]] += 1
    if s in ("CRÍTICA", "ALTA"):
        hi.append((s, rid, loc, prim))
print("total rows", len(rows))
print("verdict", dict(vc))
print("severity", dict(sc))
print("per doc", dict(per_doc))
for h in sorted(hi, key=lambda x: (x[0] != "CRÍTICA", x[1])):
    print(h)
