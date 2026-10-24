#!/usr/bin/env python3
"""
gql-suggest — enumerate GraphQL schemas on servers with introspection disabled.

Many Apollo Server deployments disable introspection in production but leave
field suggestions enabled. Validation errors then leak field/type names within
edit distance ~2 of any probe string. This tool mines those suggestions
breadth-first: candidate words in, discovered schema out.

Safe by construction: only well-formed queries are sent; no mutations, no
introspection fields, no batching. The server does the leaking.

Usage:
  gql_suggest.py https://target/graphql --seed small
  gql_suggest.py https://target/graphql --wordlist words.txt --depth 2
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import ssl

SUGGESTION = re.compile(r'Did you mean (?:"[^"]+"(?:, | or )?)+"?')
QUOTED = re.compile(r'"([^"]+)"')
VALID_NEEDS_SUBSEL = re.compile(r'Field "(\w+)" .* must have a selection of subfields')
CANNOT_QUERY = "Cannot query field"

DEFAULT_SEEDS = """me user users currentUser account profile balance wallet bets games
deposit withdraw transactions stats config settings feed live chat admin auth login
session online history items inventory trades payments leaderboard vip promo referral
raffle giveaway bonus rewards points currencies currency steam id email name role
""".split()


class SuggestMiner:
    def __init__(self, url, headers=None, delay=0.12, timeout=15):
        self.url = url
        self.headers = {"Content-Type": "application/json", "User-Agent": "gql-suggest/1.0",
                        **(headers or {})}
        self.delay = delay
        self.timeout = timeout
        self.ctx = ssl.create_default_context()
        self.ctx.check_hostname = False
        self.ctx.verify_mode = ssl.CERT_NONE
        self.discovered = {}   # field -> set of parents ("ROOT" or "parent.field")
        self.queued = set()

    def _post(self, query):
        body = json.dumps({"query": query}).encode()
        req = urllib.request.Request(self.url, data=body, headers=self.headers)
        for _ in range(3):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                    return json.loads(r.read().decode())
            except urllib.error.HTTPError as e:
                try:
                    return json.loads(e.read().decode())
                except Exception:
                    return None
            except Exception:
                time.sleep(1.5)
        return None

    def probe(self, query):
        """returns (suggestions, valid_fields) for a probe query"""
        resp = self._post(query)
        if not resp:
            return [], []
        sugg, valid = [], []
        for err in resp.get("errors", []):
            msg = err.get("message", "")
            if "Did you mean" in msg:
                sugg += QUOTED.findall(SUGGESTION.search(msg).group(0))
            m = VALID_NEEDS_SUBSEL.search(msg)
            if m:
                valid.append(m.group(1))
            elif CANNOT_QUERY not in msg and "Expected" not in msg and msg:
                # other errors can still confirm a field exists
                m2 = re.search(r'Field "(\w+)"', msg)
                if m2:
                    valid.append(m2.group(1))
        return sugg, valid

    def mine(self, parent="ROOT", seeds=None, depth=2):
        """BFS: probe under `parent`, harvest suggestions, recurse into subfields"""
        if depth < 0:
            return
        sel = lambda f: f"{parent} {{ {f} }}" if parent != "ROOT" else f"{{ {f} }}"
        words = list(seeds or DEFAULT_SEEDS)
        # single letters harvest short field names cheaply
        words += [c for c in "abcdefghijklmnopqrstuvwxyz"]
        found = set()
        for w in words:
            if w in self.queued:
                continue
            self.queued.add(w)
            sugg, valid = self.probe(sel(w))
            for f in sugg + valid:
                if f not in self.discovered.get(parent, set()):
                    self.discovered.setdefault(parent, set()).add(f)
                    found.add(f)
                    print(f"  [{parent}] + {f}", flush=True)
            time.sleep(self.delay)
        if depth > 0:
            for f in found:
                child = f if parent == "ROOT" else f"{parent}.{f}"
                # candidate subfield probes = same seed list (edit-distance game)
                self.mine(parent=child, seeds=words, depth=depth - 1)

    def report(self):
        print("\n=== discovered schema map ===")
        for parent in sorted(self.discovered):
            print(f"{parent}:")
            for f in sorted(self.discovered[parent]):
                print(f"    {f}")


def main():
    ap = argparse.ArgumentParser(prog="gql_suggest")
    ap.add_argument("url")
    ap.add_argument("--wordlist", help="candidate words file")
    ap.add_argument("--depth", type=int, default=1, help="BFS depth below root fields")
    ap.add_argument("--delay", type=float, default=0.12)
    ap.add_argument("--header", action="append", default=[], help="extra header 'K: V'")
    args = ap.parse_args()
    headers = dict(h.split(":", 1) for h in args.header)
    seeds = None
    if args.wordlist:
        seeds = [w.strip() for w in open(args.wordlist) if w.strip()]
    m = SuggestMiner(args.url, headers=headers, delay=args.delay)
    m.mine(seeds=seeds, depth=args.depth)
    m.report()


if __name__ == "__main__":
    main()
