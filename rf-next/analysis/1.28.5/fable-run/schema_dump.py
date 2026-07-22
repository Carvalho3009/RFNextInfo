import sqlite3, json, sys
DB = r"K:\MCP\projects\rf-next\analysis\1.28.5\rfnext-data.sqlite"
c = sqlite3.connect(DB)
tabs = [r[0] for r in c.execute("select name from sqlite_master where type='table' order by name")]
print("TABLE_COUNT", len(tabs))
for t in tabs:
    try:
        n = c.execute(f'select count(*) from "{t}"').fetchone()[0]
    except Exception as e:
        n = f"ERR:{e}"
    print(f"{t}\t{n}")
