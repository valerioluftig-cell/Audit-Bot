import sqlite3, os
db = r"C:\Users\valer\Downloads\audit_project\feedback.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print("=== coded_dirs ===")
for r in conn.execute("SELECT year, coded_dir FROM coded_runs ORDER BY run_at DESC"):
    exists = os.path.exists(r["coded_dir"]) if r["coded_dir"] else False
    print("  year=%s  exists=%s  dir=%s" % (r["year"], exists, r["coded_dir"]))

print()
print("=== 2013 comparison flags by parish ===")
for r in conn.execute("SELECT parish, COUNT(*) as n FROM uncertainties WHERE year=2013 AND source='comparison' GROUP BY parish ORDER BY n DESC"):
    print("  %-35s %d" % (r["parish"], r["n"]))

print()
print("=== 2014 comparison flags by parish ===")
for r in conn.execute("SELECT parish, COUNT(*) as n FROM uncertainties WHERE year=2014 AND source='comparison' GROUP BY parish ORDER BY n DESC"):
    print("  %-35s %d" % (r["parish"], r["n"]))

print()
# Which 2013 parishes had NO comparison flags at all
print("=== 2013 parishes in cache but NO comparison flags ===")
import pathlib, json
cache_2013 = pathlib.Path(r"C:\Users\valer\Downloads\audit_project\runs\e44ac3c9\output\cache")
cached = set(f.stem.rsplit("_",1)[0] for f in cache_2013.glob("*_2013.json"))
flagged = set(r["parish"] for r in conn.execute("SELECT DISTINCT parish FROM uncertainties WHERE year=2013 AND source='comparison'"))
print("  Cached parishes: %d" % len(cached))
print("  Parishes with comparison flags: %d" % len(flagged))
print("  Cached but no comp flag: %s" % sorted(cached - flagged))
