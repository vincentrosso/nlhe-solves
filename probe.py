"""Build one GTOpen preflop game, solve it, dump the tree. python3 probe.py games/x.json out_dir [iters] [max_nodes]"""
import json, sys, time, urllib.request, urllib.error, collections, os

BASE = os.environ.get("GTOPEN", "http://127.0.0.1:3737")
T0 = time.time()


def log(*a):
    print(time.strftime("[%H:%M:%S]"), f"+{time.time() - T0:6.0f}s", *a, flush=True)


def call(path, body=None, timeout=600):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"content-type": "application/json"}, method="GET" if body is None else "POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{path} -> {e.code}: {e.read()[:600].decode(errors='replace')}") from None


def main():
    cfg_path, out = sys.argv[1], sys.argv[2]
    iters = int(sys.argv[3]) if len(sys.argv) > 3 else 300
    max_nodes = int(sys.argv[4]) if len(sys.argv) > 4 else 4000
    os.makedirs(out, exist_ok=True)
    cfg = json.load(open(cfg_path))
    for name in ("version", "preflop/capabilities", "preflop/leafnets"):
        try:
            v = call("/api/" + name)
            json.dump(v, open(f"{out}/{name.replace('/', '_')}.json", "w"))
            log(name, json.dumps(v)[:400])
        except Exception as e:
            log(name, "FAILED", e)
    try:
        log("estimate", json.dumps(call("/api/preflop/estimate", cfg))[:600])
    except Exception as e:
        log("estimate FAILED", e)
    try:
        built = call("/api/preflop/spot", cfg)
    except Exception as e:
        log("build FAILED with", cfg.get("realization"), e, "-> retrying with realization=balanced")
        cfg.update(realization="balanced"); cfg.pop("leaf_net", None)
        built = call("/api/preflop/spot", cfg)
    log("built", json.dumps(built)[:600])
    json.dump({"config": cfg, "built": built}, open(f"{out}/built.json", "w"))
    log("solve start", iters, "iterations")
    log("solve ->", json.dumps(call("/api/preflop/solve", {"iterations": iters, "check_every": 25, "target_gap": 0.01}))[:300])
    last = None
    while True:
        time.sleep(10)
        st = call("/api/preflop/status")
        brief = {k: st.get(k) for k in ("state", "iteration", "gap_total", "gaps", "error")}
        log("status", json.dumps(brief)[:300])
        if st.get("state") in ("done", "stopped", "idle") and last == st.get("iteration"):
            break
        last = st.get("iteration")
        if time.time() - T0 > 3 * 3600:
            log("3h budget hit: stopping"); call("/api/preflop/stop", {})
    json.dump(st, open(f"{out}/status.json", "w"))
    # walk: breadth first, every action of every decision, raw node views one per line
    q, n, kinds = collections.deque([[]]), 0, collections.Counter()
    with open(f"{out}/nodes.jsonl", "w") as f:
        while q and n < max_nodes:
            path = q.popleft()
            try:
                r = call("/api/preflop/node", {"path": path})
            except Exception as e:
                log("node", path, "FAILED", e); kinds["failed"] += 1; continue
            node = r.get("result", r)
            if n == 0:
                log("first node keys", sorted(node), "| wrapper keys", sorted(r))
                log("first node (cut)", json.dumps({k: v for k, v in node.items() if k not in ("strategy", "reach", "reaches_all")})[:1500])
            node.pop("reaches_all", None)
            f.write(json.dumps({"path": path, "node": node}, separators=(",", ":")) + "\n")
            n += 1; kinds[node.get("kind")] += 1
            if node.get("actor") is not None:
                q.extend(path + [i] for i in range(len(node.get("actions") or [])))
            if n % 500 == 0:
                log("walked", n, "queue", len(q), dict(kinds))
    log("walk done:", n, "nodes written,", len(q), "left unvisited,", dict(kinds))
    try:
        log("save ->", json.dumps(call("/api/preflop/save", {"name": os.path.basename(cfg_path)[:-5]}))[:300])
    except Exception as e:
        log("save FAILED", e)


main()
