---
description: Protect container volumes, images, and build cache from destructive Docker/Podman cleanup
condition:
  - '\b(?:docker|podman)\s+(?:system|image|container|network|builder|buildx|volume)\s+prune\b'
  - '\b(?:docker|podman)\s+volume\s+(?:rm|remove)\b'
  - '\b(?:(?:docker|podman)\s+compose|docker-compose|podman-compose)\b[^\n;&|]*\sdown\b[^\n;&|]*\s(?:-v|--volumes|--rmi)\b'
scope: "tool:bash"
interruptMode: always
---

Volumes hold databases and other persistent state; prune and `down -v` delete them irreversibly. Images and build cache are reusable and slow to rebuild. Remove a volume, or run `compose down -v`/`--rmi`, only when the user explicitly requested that exact target; otherwise ask first.

## Before removing

List exactly what would go and name each volume's owner project.

```bash
docker volume ls
docker system df -v
docker compose config --volumes
docker volume inspect --format '{{ index .Labels "com.docker.compose.project" }}' my-volume
```

## Volumes are user data

Volumes for long-lived services (Postgres, memory/vector stores, caches shared across projects) are user data, not disposable test fixtures.

## Not troubleshooting

NEVER run `system prune` (especially `-a`/`--volumes`) as troubleshooting; remove only the specific containers or images this session created.

```bash
# Bad
docker system prune -a --volumes
docker compose down -v

# Good — remove only what this session created
docker rm -f my-test-container
docker image rm my-test-image:dev
```

## Exceptions

Containers and volumes this session created for a throwaway test may be removed once their owner process exits.
