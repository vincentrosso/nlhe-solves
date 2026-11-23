"""Build one GTOpen postflop spot, solve it, dump what a node looks like. python3 probe_post.py spots/x.json out_dir [iters] [max_nodes]"""
import json, sys, time, urllib.request, urllib.error, collections, os, resource

BASE = os.environ.get("GTOPEN", "http://127.0.0.1:3737")
API = os.environ.get("GTO_API", "/api")          # /api = heads-up, /api/mw = three players
T0 = time.time()


def log(*a):
    print(time.strftime("[%H:%M:%S]"), f"+{time.time() - T0:6.0f}s", *a, flush=True)


def call(path, body=None, timeout=1800):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} -> {e.code}: {e.read()[:800].decode(errors='replace')}") from None


def cut(v, n=1800):
    return json.dumps(v)[:n]


def main():
    spot_path, out = sys.argv[1], sys.argv[2]
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    max_nodes = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    os.makedirs(out, exist_ok=True)
    spot = json.load(open(spot_path))
    built = call(API + "/spot", spot)
    log("built", cut(built, 1200))
    json.dump(built, open(f"{out}/built.json", "w"))
    log("solve ->", cut(call(API + "/solve", {"max_iterations": iters, "target_exploit_pct": 0.5, "check_every": 20}), 300))
    last, same = None, 0
    while True:
        time.sleep(15)
        st = call(API + "/status")
        brief = {k: v for k, v in st.items() if not isinstance(v, (list, dict)) or len(json.dumps(v)) < 200}
        log("status", cut(brief, 500))
        key = json.dumps(brief, sort_keys=True)
        same = same + 1 if key == last else 0
        last = key
        state = str(st.get("state") or st.get("status") or "")
        if state in ("done", "stopped", "idle", "solved", "finished") or same >= 8:
            break
        if time.time() - T0 > 4 * 3600:
            log("4h budget hit: stopping"); call(API + "/stop", {})
    json.dump(st, open(f"{out}/status.json", "w"))
    q, n, kinds, carded = collections.deque([[]]), 0, collections.Counter(), 0
    with open(f"{out}/nodes.jsonl", "w") as f:
        while q and n < max_nodes:
            path = q.popleft()
            try:
                node = call(API + "/node", {"path": path})
            except Exception as e:
                log("node", path, "FAILED", e); kinds["failed"] += 1; continue
            if n < 3 or (path and path[-1]["type"] == "card" and carded < 3):
                slim = {k: v for k, v in node.items() if k != "players"}
                log("node", cut(path, 200), "keys", sorted(node), "|", cut(slim, 1500))
                for p in node.get("players") or []:
                    hs = p.get("hands") or []
                    log("  player keys", sorted(k for k in p if k != "hands"), "hands", len(hs), "first two:", cut(hs[:2], 900))
                carded += bool(path and path[-1]["type"] == "card")
            f.write(json.dumps({"path": path, "node": node}, separators=(",", ":")) + "\n")
            n += 1
            kind = node.get("kind") or node.get("node_type") or ("action" if node.get("actions") else "other")
            kinds[kind] += 1
            acts = node.get("actions") or []
            if kind == "chance" or (not acts and node.get("available_cards")):
                cards = node.get("available_cards") or []
                names = [c if isinstance(c, str) else c.get("card") for c in cards]
                names = names[::max(1, len(names) // 2)][:2]             # two sample cards per chance node
                if n == 0 or kinds[kind] <= 2:
                    log("chance node", cut(path, 200), "cards", cut(cards, 300))
                if sum(st["type"] == "card" for st in path) < 2:
                    q.extend(path + [{"type": "card", "card": c}] for c in names if c)
            elif acts:
                q.extend(path + [{"type": "action", "index": i}] for i in range(len(acts)))
    log("walk done:", n, "nodes,", len(q), "unvisited,", dict(kinds), "| file MB", round(os.path.getsize(f"{out}/nodes.jsonl") / 1e6, 1))
    try:
        log("save ->", cut(call(API + "/save", {"name": os.path.basename(spot_path)[:-5]}), 300))
    except Exception as e:
        log("save FAILED", e)


main()
