#!/usr/bin/env python3
"""
Deployment and Rollback script for Open WebUI v0.13.4 Native Realtime Voice Remediation.

Features:
- Verifies exact SHA-256 fingerprints for known upstream (v0.13.4) and patched BnHPywC-.js bundles.
- Refuses to modify unexpected or unknown upstream bundles.
- Stages updates to a temporary file inside the target container and swaps atomically via mv.
- Verifies resulting SHA-256 checksums after patch and rollback.
- Preserves original backups and fails nonzero if rollback lacks a valid original backup.
"""

import argparse
import hashlib
import os
import shlex
import subprocess
import sys
import uuid

DEFAULT_CONTAINER_NAME = "open-webui"
BUNDLE_PATH_IN_CONTAINER = "/app/build/_app/immutable/chunks/BnHPywC-.js"
BACKUP_PATH_IN_CONTAINER = "/app/build/_app/immutable/chunks/BnHPywC-.js.orig"

EXPECTED_ORIG_SHA256 = "d2359a68d087ee9a7ab52895653e4f27f40b64f90f0ede8a0eb5c77729dbf33c"
EXPECTED_PATCHED_SHA256 = "d5e4d07cfd5d13b4dfe0aa0d0dcb261ef2296d0ca6484f8ffcc7ac89187f67ab"

LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
PATCHED_LOCAL = os.path.join(LOCAL_DIR, "BnHPywC-.js")
ORIG_LOCAL = os.path.join(LOCAL_DIR, "BnHPywC-.js.orig")


class PatchError(RuntimeError):
    """Raised when bundle verification, staging, patching, or rollback fails."""


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


def check_status(container: str = DEFAULT_CONTAINER_NAME) -> str:
    print(f"Checking deployment status in container '{container}'...")
    current_sha = container_sha256(container, BUNDLE_PATH_IN_CONTAINER)
    has_backup = container_file_exists(container, BACKUP_PATH_IN_CONTAINER)
    backup_sha = container_sha256(container, BACKUP_PATH_IN_CONTAINER) if has_backup else None

    if current_sha == EXPECTED_PATCHED_SHA256:
        print(f"  [STATUS] PATCHED (sha256={current_sha}, backup_present={has_backup}, backup_sha={backup_sha})")
        return "patched"
    if current_sha == EXPECTED_ORIG_SHA256:
        print(f"  [STATUS] UNPATCHED / ORIGINAL (sha256={current_sha}, backup_present={has_backup})")
        return "unpatched"
    print(f"  [STATUS] UNEXPECTED BUNDLE (sha256={current_sha}, expected orig={EXPECTED_ORIG_SHA256} or patched={EXPECTED_PATCHED_SHA256})")
    return "unexpected"


def apply_patch(container: str = DEFAULT_CONTAINER_NAME, patched_local: str = PATCHED_LOCAL, orig_local: str = ORIG_LOCAL) -> None:
    print(f"Deploying patched bundle to '{container}:{BUNDLE_PATH_IN_CONTAINER}'...")
    current_sha = container_sha256(container, BUNDLE_PATH_IN_CONTAINER)

    if current_sha == EXPECTED_PATCHED_SHA256:
        # Idempotent: ensure backup is present if missing and host original is valid
        if not container_file_exists(container, BACKUP_PATH_IN_CONTAINER) and os.path.isfile(orig_local):
            atomic_deploy_to_container(container, orig_local, BACKUP_PATH_IN_CONTAINER, EXPECTED_ORIG_SHA256)
        print(f"  [OK] Bundle is already patched (sha256={current_sha}). No changes needed.")
        return

    if current_sha != EXPECTED_ORIG_SHA256:
        raise PatchError(
            f"Refusing to patch unexpected bundle in '{container}:{BUNDLE_PATH_IN_CONTAINER}' "
            f"(sha256={current_sha}; expected original {EXPECTED_ORIG_SHA256})."
        )

    # 1. Preserve original backup atomically if not already backed up; verify if present
    if container_file_exists(container, BACKUP_PATH_IN_CONTAINER):
        backup_sha = container_sha256(container, BACKUP_PATH_IN_CONTAINER)
        if backup_sha != EXPECTED_ORIG_SHA256:
            raise PatchError(
                f"Existing backup '{container}:{BACKUP_PATH_IN_CONTAINER}' has unexpected sha256={backup_sha} "
                f"(expected {EXPECTED_ORIG_SHA256}). Refusing to overwrite."
            )
    else:
        atomic_copy_in_container(container, BUNDLE_PATH_IN_CONTAINER, BACKUP_PATH_IN_CONTAINER, EXPECTED_ORIG_SHA256)

    # 2. Atomically deploy and verify patched bundle
    atomic_deploy_to_container(container, patched_local, BUNDLE_PATH_IN_CONTAINER, EXPECTED_PATCHED_SHA256)
    final_sha = container_sha256(container, BUNDLE_PATH_IN_CONTAINER)
    if final_sha != EXPECTED_PATCHED_SHA256:
        raise PatchError(f"Post-patch verification failed: expected {EXPECTED_PATCHED_SHA256}, got {final_sha}")
    print(f"  [SUCCESS] Patched bundle deployed and verified (sha256={final_sha}).")


def rollback(container: str = DEFAULT_CONTAINER_NAME, orig_local: str = ORIG_LOCAL) -> None:
    print(f"Rolling back bundle in '{container}:{BUNDLE_PATH_IN_CONTAINER}'...")
    current_sha = container_sha256(container, BUNDLE_PATH_IN_CONTAINER)
    if current_sha not in (EXPECTED_PATCHED_SHA256, EXPECTED_ORIG_SHA256):
        raise PatchError(
            f"Refusing rollback on unexpected bundle in '{container}:{BUNDLE_PATH_IN_CONTAINER}' (sha256={current_sha})."
        )

    if container_file_exists(container, BACKUP_PATH_IN_CONTAINER):
        atomic_copy_in_container(container, BACKUP_PATH_IN_CONTAINER, BUNDLE_PATH_IN_CONTAINER, EXPECTED_ORIG_SHA256)
        source_desc = f"container backup {BACKUP_PATH_IN_CONTAINER}"
    elif os.path.isfile(orig_local):
        atomic_deploy_to_container(container, orig_local, BUNDLE_PATH_IN_CONTAINER, EXPECTED_ORIG_SHA256)
        source_desc = f"host backup {orig_local}"
    else:
        raise PatchError(
            f"Cannot rollback '{container}': neither container backup '{BACKUP_PATH_IN_CONTAINER}' "
            f"nor host backup '{orig_local}' is present."
        )

    final_sha = container_sha256(container, BUNDLE_PATH_IN_CONTAINER)
    if final_sha != EXPECTED_ORIG_SHA256:
        raise PatchError(f"Post-rollback verification failed: expected {EXPECTED_ORIG_SHA256}, got {final_sha}")
    print(f"  [SUCCESS] Rolled back from {source_desc} and verified (sha256={final_sha}).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Open WebUI v0.13.4 Realtime Voice remediation patch.")
    parser.add_argument("--container", default=DEFAULT_CONTAINER_NAME, help="Target Open WebUI container name")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--patch", action="store_true", help="Apply remediation patch (default)")
    group.add_argument("--rollback", action="store_true", help="Roll back to original bundle")
    group.add_argument("--status", action="store_true", help="Check current bundle status")
    args = parser.parse_args(argv)

    try:
        if args.rollback:
            rollback(container=args.container)
        elif args.status:
            state = check_status(container=args.container)
            if state == "unexpected":
                return 2
        else:
            apply_patch(container=args.container)
    except PatchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
