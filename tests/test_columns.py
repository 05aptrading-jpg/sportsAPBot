import requests, re

h = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Test 1: batting table columns
print("=== BATTING TABLE ===")
url = "https://www.baseball-reference.com/leagues/majors/2025-standard-batting.shtml"
r = requests.get(url, headers=h, timeout=20)
html = r.text
m = re.search(r'<table[^>]+id="teams_standard_batting"[^>]*>(.*?)</table>', html, re.DOTALL|re.IGNORECASE)
if m:
    table = m.group(1)
    cells = re.findall(r'data-stat="([^"]+)"', table)
    unique = list(dict.fromkeys(cells))
    print("All columns:", unique)
    pf = [c for c in unique if "park" in c.lower() or "bpf" in c.lower() or "factor" in c.lower()]
    print("Park factor columns:", pf)
else:
    print("Table not found")

# Test 2: value-pitching table
print("\n=== VALUE PITCHING TABLE ===")
url2 = "https://www.baseball-reference.com/leagues/majors/2025-value-pitching.shtml"
r2 = requests.get(url2, headers=h, timeout=20)
html2 = r2.text
m2 = re.search(r'<table[^>]+id="teams_value_pitching"[^>]*>(.*?)</table>', html2, re.DOTALL|re.IGNORECASE)
if m2:
    table2 = m2.group(1)
    cells2 = re.findall(r'data-stat="([^"]+)"', table2)
    unique2 = list(dict.fromkeys(cells2))
    print("All columns:", unique2)
    war = [c for c in unique2 if "war" in c.lower() or "WAR" in c]
    print("WAR columns:", war)
    # Get one sample row
    rows = re.findall(r'<tr[^>]*class="[^"]*(?:full_table)[^"]*"[^>]*>(.*?)</tr>', table2, re.DOTALL|re.IGNORECASE)
    if rows:
        row_cells = re.findall(r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]*)(?:</[^>]+>)*</(?:td|th)>', rows[0], re.IGNORECASE)
        print("Sample row:", dict(row_cells))
else:
    print("Table not found - trying in comments")
    # B-Ref hides some tables in HTML comments
    comments = re.findall(r'<!--(.*?)-->', html2, re.DOTALL)
    for c in comments:
        if 'teams_value_pitching' in c:
            m3 = re.search(r'<table[^>]+id="teams_value_pitching"[^>]*>(.*?)</table>', c, re.DOTALL|re.IGNORECASE)
            if m3:
                table3 = m3.group(1)
                cells3 = re.findall(r'data-stat="([^"]+)"', table3)
                unique3 = list(dict.fromkeys(cells3))
                print("Columns (from comment):", unique3)
                war3 = [c2 for c2 in unique3 if "war" in c2.lower() or "WAR" in c2]
                print("WAR columns:", war3)
                rows3 = re.findall(r'<tr[^>]*class="[^"]*(?:full_table)[^"]*"[^>]*>(.*?)</tr>', table3, re.DOTALL|re.IGNORECASE)
                if rows3:
                    row_cells3 = re.findall(r'<(?:td|th)[^>]+data-stat="([^"]+)"[^>]*>(?:<[^>]+>)*([^<]*)(?:</[^>]+>)*</(?:td|th)>', rows3[0], re.IGNORECASE)
                    print("Sample row:", dict(row_cells3))
            break

# Test 3: standard pitching table
print("\n=== STANDARD PITCHING TABLE ===")
url3 = "https://www.baseball-reference.com/leagues/majors/2025-standard-pitching.shtml"
r3 = requests.get(url3, headers=h, timeout=20)
html3 = r3.text
m4 = re.search(r'<table[^>]+id="teams_standard_pitching"[^>]*>(.*?)</table>', html3, re.DOTALL|re.IGNORECASE)
if m4:
    table4 = m4.group(1)
    cells4 = re.findall(r'data-stat="([^"]+)"', table4)
    unique4 = list(dict.fromkeys(cells4))
    print("All columns:", unique4)
    war4 = [c for c in unique4 if "war" in c.lower() or "WAR" in c]
    print("WAR columns:", war4)
