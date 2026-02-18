import os
import subprocess
import sys

MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def get_staged_files():
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main():
    bad = []
    for path in get_staged_files():
        if not os.path.exists(path) or not os.path.isfile(path):
            continue
        size = os.path.getsize(path)
        if size > MAX_BYTES:
            bad.append((path, size))

    if bad:
        print("Large staged files detected (limit: 10 MB):")
        for p, s in bad:
            print(f"  {p} ({s / (1024 * 1024):.2f} MB)")
        print("Move artifacts out of git and store pointers under artifacts/pointers/.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
