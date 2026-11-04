"""Checks the github-worker service in the resolved Compose file (ADR-018, step 6.6).

Run from the repository root, with a .env beside docker-compose.yml:

    python .github/scripts/check_compose.py

It prints only the checks: the output of `docker compose config` holds the values
of .env, so neither that output nor its errors are shown. Standard library only.
"""

import json
import re
import subprocess
import sys

WORKER = "github-worker"
CONTAINER_NAME = "developer-platform-github-worker"
MIN_GRACE_SECONDS = 90
DEPENDS_ON = {
    "postgres": "service_healthy",
    "migrate": "service_completed_successfully",
    "backend": "service_started",
}
DURATION = re.compile(r"(?:\d+(?:\.\d+)?(?:ms|h|m|s))+")
DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")
UNIT_SECONDS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}


def duration_seconds(value: object) -> float | None:
    """A duration as Compose prints it, such as 1m30s, or None if it is not one."""
    if not isinstance(value, str) or not DURATION.fullmatch(value):
        return None
    parts = DURATION_PART.findall(value)
    return sum(float(amount) * UNIT_SECONDS[unit] for amount, unit in parts)


def resolved_config() -> dict | None:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        capture_output=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def checks(config: dict) -> list[tuple[str, str, bool]]:
    """(label, what is expected, whether it holds) for each check."""
    services = config["services"]
    worker = services[WORKER]
    backend = services["backend"]
    # A service with build and no image gets the image name <project>-<service>.
    backend_image = backend.get("image") or f"{config['name']}-backend"
    images = {worker.get("image"), services["migrate"].get("image"), backend_image}
    grace = duration_seconds(worker.get("stop_grace_period"))
    depends_on = worker.get("depends_on") or {}
    return [
        ("a", "github-worker, backend and migrate use one image", len(images) == 1),
        ("b", "restart is unless-stopped", worker.get("restart") == "unless-stopped"),
        (
            "c",
            f"stop_grace_period is at least {MIN_GRACE_SECONDS} seconds",
            grace is not None and grace >= MIN_GRACE_SECONDS,
        ),
        (
            "d",
            f"container_name is {CONTAINER_NAME}",
            worker.get("container_name") == CONTAINER_NAME,
        ),
        ("e", "github-worker publishes no ports", not worker.get("ports")),
        ("f", "github-worker has no build", "build" not in worker),
        (
            "g",
            "depends_on holds postgres, migrate and backend with their conditions",
            all(
                (depends_on.get(service) or {}).get("condition") == condition
                for service, condition in DEPENDS_ON.items()
            ),
        ),
    ]


def main() -> int:
    config = resolved_config()
    if config is None:
        print("FAIL docker compose config failed; run `docker compose config -q` to see why")
        return 1
    if WORKER not in config["services"]:
        print(f"FAIL there is no {WORKER} service")
        return 1
    results = checks(config)
    for label, expected, holds in results:
        print(f"{'ok  ' if holds else 'FAIL'} ({label}) {expected}")
    return 0 if all(holds for _, _, holds in results) else 1


if __name__ == "__main__":
    sys.exit(main())
