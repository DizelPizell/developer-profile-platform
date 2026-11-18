"""Checks the github-worker service and the media volume in the resolved Compose file
(ADR-018, step 6.6; ADR-0022, step 4.2b),
and with --production the file merged with docker-compose.prod.yml (ADR-0021, 9.3).

Run from the repository root, with a .env beside docker-compose.yml:

    python .github/scripts/check_compose.py
    python .github/scripts/check_compose.py --production

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


PRODUCTION_FILES = ("-f", "docker-compose.yml", "-f", "docker-compose.prod.yml")
# The only service reachable from outside, and the ones that must get no secrets.
PUBLIC_SERVICE = "nginx"
NO_ENV_FILE = ("frontend", "nginx", "certbot")
# The screenshot volume (ADR-0022): written by the backend, read by Nginx.
MEDIA_VOLUME = "media"
MEDIA_TARGET = "/srv/media"


def media_mount(service: dict) -> dict | None:
    """The service's mount of the media volume, as `docker compose config` prints it."""
    for volume in service.get("volumes") or []:
        if volume.get("type") == "volume" and volume.get("source") == MEDIA_VOLUME:
            return volume
    return None


def resolved_config(files: tuple[str, ...] = ()) -> dict | None:
    result = subprocess.run(
        ["docker", "compose", *files, "config", "--format", "json"],
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
    backend_media = media_mount(backend) or {}
    return [
        (
            "h",
            f"backend mounts {MEDIA_VOLUME} at {MEDIA_TARGET} for writing",
            backend_media.get("target") == MEDIA_TARGET and not backend_media.get("read_only"),
        ),
        ("i", f"github-worker does not mount {MEDIA_VOLUME}", media_mount(worker) is None),
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


def production_checks(config: dict) -> list[tuple[str, str, bool]]:
    services = config["services"]
    published = sorted(name for name, service in services.items() if service.get("ports"))
    nginx_media = media_mount(services.get(PUBLIC_SERVICE) or {}) or {}
    return [
        (
            "p4",
            f"{PUBLIC_SERVICE} mounts {MEDIA_VOLUME} at {MEDIA_TARGET} read-only",
            nginx_media.get("target") == MEDIA_TARGET and nginx_media.get("read_only") is True,
        ),
        ("p1", f"only {PUBLIC_SERVICE} publishes ports", published == [PUBLIC_SERVICE]),
        (
            "p2",
            f"{', '.join(NO_ENV_FILE)} have no env_file",
            all(name in services and not services[name].get("env_file") for name in NO_ENV_FILE),
        ),
        (
            "p3",
            "every service rotates its logs (max-size)",
            all(
                ((service.get("logging") or {}).get("options") or {}).get("max-size")
                for service in services.values()
            ),
        ),
    ]


def main() -> int:
    production = "--production" in sys.argv[1:]
    config = resolved_config(PRODUCTION_FILES if production else ())
    if config is None:
        print("FAIL docker compose config failed; run `docker compose config -q` to see why")
        return 1
    if WORKER not in config["services"]:
        print(f"FAIL there is no {WORKER} service")
        return 1
    results = checks(config) + (production_checks(config) if production else [])
    for label, expected, holds in results:
        print(f"{'ok  ' if holds else 'FAIL'} ({label}) {expected}")
    return 0 if all(holds for _, _, holds in results) else 1


if __name__ == "__main__":
    sys.exit(main())
