#!/usr/bin/env python3
"""Deterministic transitive content-hashed asset versioning for Open WebUI v0.13.5.

Solves immutable 1-year caching (`Cache-Control: public, max-age=31536000, immutable`)
for patched ES module chunks (`B1EqPYAs.js`, `CaoI0pp2.js`, etc.) by assigning every
affected module in the transitive importer closure up to `entry/app.*.js`, `nodes/*.js`,
`workers/*.js`, and `index.html` a deterministic `.p<8-hex>.js` filename and rewriting all
references atomically while preserving originals/rollback state.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Dict, Iterable, List, Set

MANIFEST_REL = ".patch-asset-manifest.json"
BACKUP_REL = ".patch-asset-orig"
VERSIONED_NAME_RE = re.compile(r"\.p[0-9a-f]{8}\.js$")
JS_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_.$-])([A-Za-z0-9_.-]+\.js)(?![A-Za-z0-9_.$-])")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _atomic_write_bytes(path: Path, data: bytes, mode: int = 0o644) -> None:
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def restore_previous_versioning(build_dir: Path) -> None:
    """Remove generated `.p<hash>.js` artifacts and restore backed-up HTML/JSON files."""
    manifest_path = build_dir / MANIFEST_REL
    backup_root = build_dir / BACKUP_REL

    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        for rel in manifest.get("generated_files", []):
            p = build_dir / rel
            if p.is_file():
                p.unlink()
        for rel in manifest.get("rewritten_static_files", []):
            bak = backup_root / rel
            dst = build_dir / rel
            if bak.is_file():
                _atomic_write_bytes(dst, bak.read_bytes())

    # Sweep any leftover .p<8hex>.js if manifest was partially written
    imm_dir = build_dir / "_app" / "immutable"
    if imm_dir.is_dir():
        for root, _, fns in os.walk(imm_dir):
            for fn in fns:
                if VERSIONED_NAME_RE.search(fn):
                    try:
                        os.unlink(os.path.join(root, fn))
                    except OSError:
                        pass

    if manifest_path.is_file():
        manifest_path.unlink()


def version_build_assets(
    build_dir: Path,
    seeds: Iterable[str] = ("B1EqPYAs.js", "CaoI0pp2.js"),
) -> Dict[str, str]:
    """Compute transitive content-hashed `.p<8hex>.js` copies and rewrite HTML/JS refs.

    Returns mapping `{orig_rel_path: versioned_rel_path}` under `build_dir`.
    """
    build_dir = build_dir.resolve()
    restore_previous_versioning(build_dir)

    imm_dir = build_dir / "_app" / "immutable"
    if not imm_dir.is_dir():
        raise RuntimeError(f"Immutable build directory not found: {imm_dir}")

    # Collect original JS files under _app/immutable (ignoring .orig and any .p<hash>.js)
    js_bytes: Dict[str, bytes] = {}
    js_texts: Dict[str, str] = {}
    base_to_rels: Dict[str, List[str]] = {}

    for root, _, fns in os.walk(imm_dir):
        for fn in sorted(fns):
            if not fn.endswith(".js") or fn.endswith(".orig") or VERSIONED_NAME_RE.search(fn):
                continue
            full = Path(root) / fn
            rel = full.relative_to(build_dir).as_posix()
            raw = full.read_bytes()
            js_bytes[rel] = raw
            js_texts[rel] = raw.decode("utf-8", errors="ignore")
            base_to_rels.setdefault(fn, []).append(rel)

    # Assert seed basenames exist and resolve uniquely
    seed_basenames = {os.path.basename(s) for s in seeds if s}
    seed_rels: Set[str] = set()
    for sb in sorted(seed_basenames):
        rels = base_to_rels.get(sb, [])
        if not rels:
            raise RuntimeError(f"Seed JS asset not found under {imm_dir}: {sb}")
        seed_rels.update(rels)

    # Build direct JS dependency adjacency (file rel -> referenced child rels)
    # Note: we only need exact token matches against known JS basenames under _app/immutable
    known_basenames = set(base_to_rels.keys())
    deps: Dict[str, Set[str]] = {rel: set() for rel in js_texts}
    rev_deps: Dict[str, Set[str]] = {rel: set() for rel in js_texts}

    for rel, txt in js_texts.items():
        for m in JS_TOKEN_RE.finditer(txt):
            tok = m.group(1)
            if tok in known_basenames:
                for target_rel in base_to_rels[tok]:
                    if target_rel != rel:
                        deps[rel].add(target_rel)
                        rev_deps[target_rel].add(rel)

    # All files reaching any seed transitively (reverse BFS)
    affected_rels: Set[str] = set(seed_rels)
    q = deque(sorted(seed_rels))
    while q:
        cur = q.popleft()
        for parent in rev_deps.get(cur, ()):
            if parent not in affected_rels:
                affected_rels.add(parent)
                q.append(parent)

    # Precompute raw content hashes for cycle-safe deterministic closure hashing
    raw_hashes: Dict[str, str] = {rel: _sha256_bytes(data) for rel, data in js_bytes.items()}

    def _closure(start_rel: str) -> Set[str]:
        visited = {start_rel}
        dq = deque([start_rel])
        while dq:
            node = dq.popleft()
            for nxt in deps.get(node, ()):
                if nxt not in visited:
                    visited.add(nxt)
                    dq.append(nxt)
        return visited

    # Assign deterministic .p<8hex>.js names using closure raw hash
    rel_rename: Dict[str, str] = {}
    basename_rename: Dict[str, str] = {}
    for rel in sorted(affected_rels):
        clos = sorted(_closure(rel))
        h = hashlib.sha256()
        for item in clos:
            h.update(item.encode("utf-8"))
            h.update(b":")
            h.update(raw_hashes[item].encode("ascii"))
            h.update(b"\n")
        short_hash = h.hexdigest()[:8]
        p_obj = Path(rel)
        new_base = f"{p_obj.stem}.p{short_hash}.js"
        new_rel = p_obj.with_name(new_base).as_posix()
        rel_rename[rel] = new_rel
        # All basenames under _app/immutable have unique Vite hash stems; map basename -> versioned basename
        basename_rename[p_obj.name] = new_base

    affected_basenames = set(basename_rename.keys())

    def _rewrite_text(txt: str) -> tuple[str, bool]:
        changed = False

        def _sub(match: re.Match[str]) -> str:
            nonlocal changed
            tok = match.group(1)
            rep = basename_rename.get(tok)
            if rep:
                changed = True
                return rep
            return tok

        # Quick prefilter
        out = JS_TOKEN_RE.sub(_sub, txt)
        return out, changed

    generated_files: List[str] = []
    for rel in sorted(affected_rels):
        new_rel = rel_rename[rel]
        new_text, _ = _rewrite_text(js_texts[rel])
        dst = build_dir / new_rel
        _atomic_write_bytes(dst, new_text.encode("utf-8"))
        generated_files.append(new_rel)

    # Rewrite static HTML/JSON entrypoints (e.g. index.html) after backing up originals
    backup_root = build_dir / BACKUP_REL
    rewritten_static_files: List[str] = []
    for root, _, fns in os.walk(build_dir):
        rel_dir = Path(root).relative_to(build_dir)
        if rel_dir.parts and rel_dir.parts[0] in (BACKUP_REL,):
            continue
        if len(rel_dir.parts) >= 2 and rel_dir.parts[0] == "_app" and rel_dir.parts[1] == "immutable":
            continue
        for fn in sorted(fns):
            if not fn.endswith((".html", ".json")):
                continue
            full = Path(root) / fn
            rel = full.relative_to(build_dir).as_posix()
            raw_txt = full.read_text(encoding="utf-8", errors="ignore")
            new_txt, changed = _rewrite_text(raw_txt)
            if changed:
                bak = backup_root / rel
                bak.parent.mkdir(parents=True, exist_ok=True)
                if not bak.is_file():
                    _atomic_write_bytes(bak, full.read_bytes())
                _atomic_write_bytes(full, new_txt.encode("utf-8"))
                rewritten_static_files.append(rel)

    manifest = {
        "seeds": sorted(seed_basenames),
        "generated_files": generated_files,
        "rewritten_static_files": rewritten_static_files,
        "rename_map": rel_rename,
    }
    _atomic_write_bytes(
        build_dir / MANIFEST_REL,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    )
    return rel_rename


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=Path("/app/build"))
    parser.add_argument("--seeds", nargs="+", default=["B1EqPYAs.js", "CaoI0pp2.js"])
    parser.add_argument("--rollback", action="store_true")
    args = parser.parse_args()

    if args.rollback:
        restore_previous_versioning(args.build_dir)
        print(f"Restored asset versioning under {args.build_dir}")
        return 0

    mapping = version_build_assets(args.build_dir, seeds=args.seeds)
    print(f"Versioned {len(mapping)} transitive assets under {args.build_dir} (seeds={args.seeds})")
    for sb in sorted(args.seeds):
        matches = [(k, v) for k, v in mapping.items() if os.path.basename(k) == sb or os.path.basename(k).startswith("app.")]
        for k, v in matches:
            print(f"  {k} -> {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
