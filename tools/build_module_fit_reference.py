"""One-off, pinned EDCD reference export. Runtime never accesses GitHub."""
import concurrent.futures
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "ED-Frame-reference-import"}), timeout=30) as response:
        return json.load(response)


def main():
    commit = fetch("https://api.github.com/repos/EDCD/coriolis-data/commits/master")["sha"]
    tree = fetch(f"https://api.github.com/repos/EDCD/coriolis-data/git/trees/{commit}?recursive=1")
    paths = [row["path"] for row in tree["tree"] if row["path"].endswith(".json") and row["path"].startswith(("ships/", "modules/"))]
    def read(path):
        return path, fetch(f"https://raw.githubusercontent.com/EDCD/coriolis-data/{commit}/{path}")
    result = {"source": "https://github.com/EDCD/coriolis-data", "commit": commit, "ships": {}, "modules": {}}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for path, payload in pool.map(read, paths):
            if path.startswith("ships/"):
                for symbol, ship in payload.items():
                    props = ship.get("properties", {})
                    result["ships"][symbol.casefold()] = {"hullMass": props.get("hullMass"), "name": props.get("name"), "slots": ship.get("slots", {})}
            else:
                for rows in payload.values():
                    for row in rows if isinstance(rows, list) else []:
                        if row.get("symbol"):
                            result["modules"][row["symbol"].casefold()] = {key: row[key] for key in ("mass", "maxmass", "power", "pgen", "cost", "rating", "class", "grp") if key in row}
                            result["modules"][row["symbol"].casefold()].setdefault("power", 0)
    rules_commit = fetch("https://api.github.com/repos/taleden/EDSY/commits/master")["sha"]
    with urlopen(f"https://raw.githubusercontent.com/taleden/EDSY/{rules_commit}/eddb.js", timeout=30) as response:
        rules = response.read().decode("utf-8")
    result["rulesSource"] = "https://github.com/taleden/EDSY"
    result["rulesCommit"] = rules_commit
    ship_ids = {int(number): symbol.casefold() for number, symbol in re.findall(r"\n\s*(\d+)\s*:\s*\{\s*fdid:[^\n]+?fdname:'([^']+)'", rules)}
    for match in re.finditer(r"\n\s*\d+\s*:\s*\{\s*fdid:[^\n]+?fdname:'([^']+)'([^{}]+)", rules):
        mass = re.search(r"\bmass:\s*([\d.]+)", match.group(2))
        if mass:
            result["ships"].setdefault(match.group(1).casefold(), {})["hullMass"] = float(mass.group(1))
    limits_block = re.search(r"\n\s*limit\s*:\s*\{([^}]+)\}", rules).group(1)
    result["limits"] = {key: int(value) for key, value in re.findall(r"'([^']+)'\s*:\s*(\d+)", limits_block)}
    for line in rules.splitlines():
        armour = re.search(r"fdname:'([^']+_Armour_[^']+)'", line, re.IGNORECASE)
        if armour:
            entry = result["modules"].setdefault(armour.group(1).casefold(), {})
            entry["power"] = 0
            for field in ("mass", "cost"):
                value = re.search(r"\b" + field + r":\s*([\d.]+)\s*[,}]", line)
                if value:
                    entry[field] = float(value.group(1))
        if not re.match(r"\s*\d+\s*:\s*\{.*mtype:", line):
            continue
        name = re.search(r"fdname:'([^']+)'", line)
        if not name:
            continue
        row = result["modules"].setdefault(name.group(1).casefold(), {})
        reserved = re.search(r"reserved:\{([^}]+)\}", line)
        if reserved:
            ids = [int(value) for value in re.findall(r"(\d+):1", reserved.group(1))]
            if not all(value in ship_ids for value in ids):
                raise ValueError("Unresolved reserved ship IDs")
            row["allowedShips"] = [ship_ids[value] for value in ids]
        for field in ("limit", "unlimit"):
            match = re.search(field + r":'([^']+)'", line)
            if match:
                row[field] = match.group(1)
        row["noUndersize"] = bool(re.search(r"noundersize:\s*1", line))
    target = Path(__file__).resolve().parents[1] / "ed_data" / "module_fit_reference.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Pinned {commit}: {len(result['ships'])} ships, {len(result['modules'])} modules")


if __name__ == "__main__":
    main()
