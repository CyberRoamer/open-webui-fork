#!/usr/bin/env python3
"""
Deployment, status verification, and rollback utility for Open WebUI v0.13.5 patches:
- B1EqPYAs.js : Mobile realtime AudioWorklet resampling and user-gesture audio unlock
- ask_user.py : Flexible ask_user options validation (0 or more options + text input)
- builtin.py  : Builtin ask_user tool validation and schema docstring
"""

import argparse
from dataclasses import dataclass
import hashlib
import os
import shlex
import subprocess
import sys
import uuid

DEFAULT_CONTAINER_NAME = "open-webui"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATCHES_DIR = (
    LOCAL_DIR
    if os.path.isfile(os.path.join(LOCAL_DIR, "B1EqPYAs.js"))
    else os.path.abspath(os.path.join(LOCAL_DIR, "..", "open-webui-patches", "v0.13.5"))
)


@dataclass(frozen=True)
class PatchTarget:
    name: str
    container_path: str
    backup_path: str
    filename: str
    orig_filename: str
    expected_orig_sha256: str
    expected_patched_sha256: str


TARGETS: tuple[PatchTarget, ...] = (
    PatchTarget(
        name="B1EqPYAs.js",
        container_path="/app/build/_app/immutable/chunks/B1EqPYAs.js",
        backup_path="/app/build/_app/immutable/chunks/B1EqPYAs.js.orig",
        filename="B1EqPYAs.js",
        orig_filename="B1EqPYAs.js.orig",
        expected_orig_sha256="29d6b2a2e76eff38c3bd7602c006459ed8d19c405eeaa06b28da52b81347e31c",
        expected_patched_sha256="a39794ef60a0d0c0571ff17499b458338f933ba8fc6c2e7761cba5bcafe72d90",
    ),
    PatchTarget(
        name="CaoI0pp2.js",
        container_path="/app/build/_app/immutable/chunks/CaoI0pp2.js",
        backup_path="/app/build/_app/immutable/chunks/CaoI0pp2.js.orig",
        filename="CaoI0pp2.js",
        orig_filename="CaoI0pp2.js.orig",
        expected_orig_sha256="7611058e08d300631a1d481bea550389eba07a5ac873611e814139f86f5bdd94",
        expected_patched_sha256="4ba267e48e304c3d5f4c720f665f397952863ea6ea5d4d762b137af3840e939e",
    ),
    PatchTarget(
        name="ask_user.py",
        container_path="/app/backend/open_webui/utils/ask_user.py",
        backup_path="/app/backend/open_webui/utils/ask_user.py.orig",
        filename="ask_user.py",
        orig_filename="ask_user.py.orig",
        expected_orig_sha256="8538e5effbda42c310573e6a5be718b8ea655ddb90c5360b25bf1386a74e5c5d",
        expected_patched_sha256="984e19f255f7cadc6839147acee4502d58fd80f4c75ef7c90c61cb4fae89b16b",
    ),
    PatchTarget(
        name="builtin.py",
        container_path="/app/backend/open_webui/tools/builtin.py",
        backup_path="/app/backend/open_webui/tools/builtin.py.orig",
        filename="builtin.py",
        orig_filename="builtin.py.orig",
        expected_orig_sha256="1bd4ce2bd8a8aaf180a5a0783a616519968de62eaea1c87b54536c51e560d59c",
        expected_patched_sha256="7e0134597c37b08deb79845d84435c94b6fef3c0c342b58237934ddef18045b0",
    ),
    PatchTarget(
        name="middleware.py",
        container_path="/app/backend/open_webui/utils/middleware.py",
        backup_path="/app/backend/open_webui/utils/middleware.py.orig",
        filename="middleware.py",
        orig_filename="middleware.py.orig",
        expected_orig_sha256="919b4dc69c6356d65ed1198467710f00933de3b08825f5c5b96a5f3d5f066f7d",
        expected_patched_sha256="7fac507d50b85c8296318876cd914402954eaa200c8678e64e244852c32ebccd",
    ),
    PatchTarget(
        name="headers.py",
        container_path="/app/backend/open_webui/utils/headers.py",
        backup_path="/app/backend/open_webui/utils/headers.py.orig",
        filename="headers.py",
        orig_filename="headers.py.orig",
        expected_orig_sha256="2601a71db5eadd258d5dc89b40023d4c470063357bdeafe939cbcda45a32a432",
        expected_patched_sha256="7a158f28d1b8f6b9efd6510686f95d4bc0d9a1d8b782dfb0e7f664d0b85bbc51",
    ),
    PatchTarget(
        name="audio_init.py",
        container_path="/app/backend/open_webui/routers/audio/__init__.py",
        backup_path="/app/backend/open_webui/routers/audio/__init__.py.orig",
        filename="audio_init.py",
        orig_filename="audio_init.py.orig",
        expected_orig_sha256="f22233f795444da1773f07043e478b77f915bde5633580a9f231b4eed864dd40",
        expected_patched_sha256="9265128cdb8f15ec5c9c0327a67bd9f7de2ac78ff3f65129199c6aa8c3567f17",
    ),
    PatchTarget(
        name="audio_realtime.py",
        container_path="/app/backend/open_webui/routers/audio/realtime.py",
        backup_path="/app/backend/open_webui/routers/audio/realtime.py.orig",
        filename="audio_realtime.py",
        orig_filename="audio_realtime.py.orig",
        expected_orig_sha256="0226a1501401e08804c3501474de847e454d12f98ae938eb83cfc678e1b4a830",
        expected_patched_sha256="442197a929490256ff5ad1fe74652950214550b500f083dc298414a83d578d09",
    ),
)


class PatchError(RuntimeError):
    """Raised when target verification, staging, patching, or rollback fails."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(args: list[str]) -> str:
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0:
        detail = res.stderr.strip() or res.stdout.strip() or f"exit code {res.returncode}"
        raise PatchError(f"Command failed ({' '.join(args)}): {detail}")
    return res.stdout.strip()


def container_file_exists(container: str, path: str) -> bool:
    res = subprocess.run(
        ["docker", "exec", container, "sh", "-c", f"test -f {shlex.quote(path)}"],
        capture_output=True,
        text=True,
    )
    return res.returncode == 0


def container_sha256(container: str, path: str) -> str:
    if not container_file_exists(container, path):
        raise PatchError(f"File not found in container '{container}': {path}")
    out = run_cmd(["docker", "exec", container, "sha256sum", path])
    return out.split()[0].strip().lower()


def atomic_deploy_to_container(container: str, local_src: str, target_path: str, expected_sha256: str) -> None:
    if not os.path.isfile(local_src):
        raise PatchError(f"Local source file missing: {local_src}")
    actual_local_sha = sha256_file(local_src)
    if actual_local_sha != expected_sha256:
        raise PatchError(
            f"Local file checksum mismatch for {local_src}: expected {expected_sha256}, got {actual_local_sha}"
        )

    tmp_path = f"{target_path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    q_tmp = shlex.quote(tmp_path)
    q_target = shlex.quote(target_path)
    try:
        run_cmd(["docker", "cp", local_src, f"{container}:{tmp_path}"])
        staged_sha = container_sha256(container, tmp_path)
        if staged_sha != expected_sha256:
            raise PatchError(
                f"Staged file checksum mismatch in '{container}:{tmp_path}': expected {expected_sha256}, got {staged_sha}"
            )
        run_cmd(["docker", "exec", container, "sh", "-c", f"chmod 0644 {q_tmp} && mv -f {q_tmp} {q_target}"])
    except Exception:
        subprocess.run(
            ["docker", "exec", container, "rm", "-f", tmp_path],
            capture_output=True,
            text=True,
        )
        raise


def atomic_copy_in_container(container: str, src_path: str, dst_path: str, expected_sha256: str) -> None:
    src_sha = container_sha256(container, src_path)
    if src_sha != expected_sha256:
        raise PatchError(
            f"Container source checksum mismatch for '{container}:{src_path}': expected {expected_sha256}, got {src_sha}"
        )

    tmp_path = f"{dst_path}.tmp.{os.getpid()}.{uuid.uuid4().hex[:8]}"
    q_src = shlex.quote(src_path)
    q_tmp = shlex.quote(tmp_path)
    q_dst = shlex.quote(dst_path)
    try:
        run_cmd(["docker", "exec", container, "sh", "-c", f"cp -p {q_src} {q_tmp}"])
        staged_sha = container_sha256(container, tmp_path)
        if staged_sha != expected_sha256:
            raise PatchError(
                f"Staged copy checksum mismatch in '{container}:{tmp_path}': expected {expected_sha256}, got {staged_sha}"
            )
        run_cmd(["docker", "exec", container, "sh", "-c", f"mv -f {q_tmp} {q_dst}"])
    except Exception:
        subprocess.run(
            ["docker", "exec", container, "rm", "-f", tmp_path],
            capture_output=True,
            text=True,
        )
        raise


def check_target_status(container: str, target: PatchTarget) -> str:
    current_sha = container_sha256(container, target.container_path)
    has_backup = container_file_exists(container, target.backup_path)
    backup_sha = container_sha256(container, target.backup_path) if has_backup else None

    if current_sha == target.expected_patched_sha256:
        print(f"  [PATCHED] {target.name} (sha256={current_sha}, backup_present={has_backup}, backup_sha={backup_sha})")
        return "patched"
    if current_sha == target.expected_orig_sha256:
        print(f"  [UNPATCHED] {target.name} (sha256={current_sha}, backup_present={has_backup})")
        return "unpatched"
    print(
        f"  [UNEXPECTED] {target.name} (sha256={current_sha}, expected orig={target.expected_orig_sha256} or patched={target.expected_patched_sha256})"
    )
    return "unexpected"


def check_status(container: str = DEFAULT_CONTAINER_NAME) -> str:
    print(f"Checking Open WebUI v0.13.5 patch status in container '{container}'...")
    statuses = [check_target_status(container, target) for target in TARGETS]
    if all(s == "patched" for s in statuses):
        return "patched"
    if any(s == "unexpected" for s in statuses):
        return "unexpected"
    return "unpatched"


def apply_target_patch(container: str, target: PatchTarget, patches_dir: str) -> None:
    patched_local = os.path.join(patches_dir, target.filename)
    orig_local = os.path.join(patches_dir, target.orig_filename)
    current_sha = container_sha256(container, target.container_path)

    if current_sha == target.expected_patched_sha256:
        if not container_file_exists(container, target.backup_path) and os.path.isfile(orig_local):
            atomic_deploy_to_container(container, orig_local, target.backup_path, target.expected_orig_sha256)
        print(f"  [OK] {target.name} is already patched (sha256={current_sha}).")
        return

    if current_sha != target.expected_orig_sha256:
        raise PatchError(
            f"Refusing to patch unexpected {target.name} in '{container}:{target.container_path}' "
            f"(sha256={current_sha}; expected original {target.expected_orig_sha256})."
        )

    if container_file_exists(container, target.backup_path):
        backup_sha = container_sha256(container, target.backup_path)
        if backup_sha != target.expected_orig_sha256:
            raise PatchError(
                f"Existing backup '{container}:{target.backup_path}' has unexpected sha256={backup_sha} "
                f"(expected {target.expected_orig_sha256}). Refusing to overwrite."
            )
    else:
        atomic_copy_in_container(container, target.container_path, target.backup_path, target.expected_orig_sha256)

    atomic_deploy_to_container(container, patched_local, target.container_path, target.expected_patched_sha256)
    final_sha = container_sha256(container, target.container_path)
    if final_sha != target.expected_patched_sha256:
        raise PatchError(
            f"Post-patch verification failed for {target.name}: expected {target.expected_patched_sha256}, got {final_sha}"
        )
    print(f"  [SUCCESS] {target.name} deployed and verified (sha256={final_sha}).")


def apply_patch(container: str = DEFAULT_CONTAINER_NAME, patches_dir: str = DEFAULT_PATCHES_DIR) -> None:
    print(f"Applying Open WebUI v0.13.5 patches to '{container}'...")
    for target in TARGETS:
        apply_target_patch(container, target, patches_dir)
    versioner_local = os.path.join(patches_dir, "asset_versioner.py")
    if os.path.isfile(versioner_local):
        tmp_v = f"/tmp/asset_versioner_{os.getpid()}.py"
        try:
            run_cmd(["docker", "cp", versioner_local, f"{container}:{tmp_v}"])
            out = run_cmd([
                "docker", "exec", container, "python3", tmp_v,
                "--build-dir", "/app/build", "--seeds", "B1EqPYAs.js", "CaoI0pp2.js",
            ])
            if out:
                print(out)
        finally:
            subprocess.run(["docker", "exec", container, "rm", "-f", tmp_v], capture_output=True, text=True)


def rollback_target(container: str, target: PatchTarget, patches_dir: str) -> None:
    orig_local = os.path.join(patches_dir, target.orig_filename)
    current_sha = container_sha256(container, target.container_path)
    if current_sha not in (target.expected_patched_sha256, target.expected_orig_sha256):
        raise PatchError(
            f"Refusing rollback on unexpected {target.name} in '{container}:{target.container_path}' (sha256={current_sha})."
        )

    if container_file_exists(container, target.backup_path):
        atomic_copy_in_container(container, target.backup_path, target.container_path, target.expected_orig_sha256)
        source_desc = f"container backup {target.backup_path}"
    elif os.path.isfile(orig_local):
        atomic_deploy_to_container(container, orig_local, target.container_path, target.expected_orig_sha256)
        source_desc = f"host backup {orig_local}"
    else:
        raise PatchError(
            f"Cannot rollback '{container}' {target.name}: neither container backup '{target.backup_path}' "
            f"nor host backup '{orig_local}' is present."
        )

    final_sha = container_sha256(container, target.container_path)
    if final_sha != target.expected_orig_sha256:
        raise PatchError(
            f"Post-rollback verification failed for {target.name}: expected {target.expected_orig_sha256}, got {final_sha}"
        )
    print(f"  [SUCCESS] Rolled back {target.name} from {source_desc} (sha256={final_sha}).")


def rollback(container: str = DEFAULT_CONTAINER_NAME, patches_dir: str = DEFAULT_PATCHES_DIR) -> None:
    print(f"Rolling back Open WebUI v0.13.5 patches in '{container}'...")
    versioner_local = os.path.join(patches_dir, "asset_versioner.py")
    if os.path.isfile(versioner_local):
        tmp_v = f"/tmp/asset_versioner_rb_{os.getpid()}.py"
        try:
            run_cmd(["docker", "cp", versioner_local, f"{container}:{tmp_v}"])
            run_cmd(["docker", "exec", container, "python3", tmp_v, "--build-dir", "/app/build", "--rollback"])
        finally:
            subprocess.run(["docker", "exec", container, "rm", "-f", tmp_v], capture_output=True, text=True)
    for target in TARGETS:
        rollback_target(container, target, patches_dir)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Manage Open WebUI v0.13.5 realtime and ask_user patches.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER_NAME, help="Docker container name (default: open-webui)")
    parser.add_argument("--patches-dir", default=DEFAULT_PATCHES_DIR, help="Directory holding v0.13.5 patch files")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--patch", action="store_true", help="Apply verified patches")
    group.add_argument("--rollback", action="store_true", help="Roll back to original upstream files")
    group.add_argument("--status", action="store_true", help="Inspect current patch state")
    args = parser.parse_args(argv)

    try:
        if args.rollback:
            rollback(args.container, args.patches_dir)
            return 0
        if args.status:
            status = check_status(args.container)
            return 0 if status == "patched" else (2 if status == "unexpected" else 1)
        apply_patch(args.container, args.patches_dir)
        return 0
    except PatchError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
