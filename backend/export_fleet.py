import sqlite3, glob, csv
found = []
for p in glob.glob("**/*.db", recursive=True) + glob.glob("**/*.sqlite*", recursive=True):
    if ".venv" in p or "node_modules" in p: continue
    try:
        con = sqlite3.connect(p)
        for (t,) in con.execute("select name from sqlite_master where type='table'"):
            cols = [r[1] for r in con.execute(f'pragma table_info("{t}")')]
            cpu = [c for c in cols if "cpu" in c.lower() and "pred" not in c.lower() and "forecast" not in c.lower()]
            mem = [c for c in cols if "mem" in c.lower() and "pred" not in c.lower() and "forecast" not in c.lower()]
            if cpu and mem:
                n = con.execute(f'select count(*) from "{t}"').fetchone()[0]
                found.append((n, p, t, cols, cpu[0], mem[0]))
    except Exception as e:
        print("skip", p, e)
if not found:
    print("No table with CPU and memory columns found. Files checked:", glob.glob("**/*.db", recursive=True))
else:
    found.sort(reverse=True)
    for n, p, t, cols, c, m in found: print(f"candidate: {p} table={t} rows={n} cpu={c} mem={m}")
    n, p, t, cols, c, m = found[0]
    idc = next((x for x in cols if x.lower() in ("resource_id", "id", "name")), None)
    sel = ", ".join(f'"{x}"' for x in ([idc] if idc else []) + [c, m])
    rows = sqlite3.connect(p).execute(f'select {sel} from "{t}"').fetchall()
    with open("fleet.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(([idc] if idc else []) + ["cpu", "memory"]); w.writerows(rows)
    print(f"Wrote fleet.csv with {len(rows)} rows from {p} / {t}")