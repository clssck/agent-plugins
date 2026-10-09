---
description: Protect container volumes, images, and build cache from destructive Docker/Podman cleanup
condition:
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:docker|podman)(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:volume[ \t]+(?:rm|remove|prune)|(?:system|image|container|network|builder|buildx)[ \t]+prune)(?=\s|$|[;&|)])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:docker|podman)(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:volume[ \t]+(?:rm|remove|prune)|(?:system|image|container|network|builder|buildx)[ \t]+prune)(?=\s|$|[;&|)"]|\\n)'
- '^(?:\s*|(?:(?:[^#''"\\]|(?<=[^\s;&|()<>])#|#[^\r\n]*(?=[\r\n]|$)|\\[\s\S]|''[^'']*''|"(?:[^"\\]|\\[\s\S])*")*?)(?:&&|;|\|\|?|\r?\n|\()\s*)(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:(?:docker|podman)[ \t]+compose|docker-compose|podman-compose)(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+down(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:-v|--volumes|--rmi(?:[ \t=]+\S+)?)(?=\s|$|[;&|)])'
- '"command"\s*:\s*"(?:(?:\\"(?:[^"\\]|\\[^"])*?\\"|\''(?:[^\''"\\]|\\.)*\''|\\[^"]|[^"\\\''])*?(?:&&|;|\|\|?|\\n|\(|\$\()\s*)?(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"(?:[^"\\]|\\[\s\S])*"|''[^'']*''|[^\s;&|''"#]+)|(?:env|command|sudo|xargs(?:[ \t]+-[^\s;&|()''"#]+)*)(?:\s+--)?)\s+)*(?:(?:docker|podman)[ \t]+compose|docker-compose|podman-compose)(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+down(?:[ \t]+(?:"(?:[^"\\\n]|\\[^\n])*"|''[^''\n]*''|[^\s;&|()''"#]+))*?[ \t]+(?:-v|--volumes|--rmi(?:[ \t=]+\S+)?)(?=\s|$|[;&|)"]|\\n)'
scope: tool:bash
interruptMode: always
---

**Volumes hold databases and other persistent state; prune and `down -v` delete them irreversibly.** Images and build cache are reusable and slow to rebuild.

- Remove a volume, or run `compose down -v`/`--rmi`, only when the user explicitly requested that exact target; otherwise ask first.
- Before removal, list exactly what would go (`docker volume ls`, `docker system df -v`, `docker compose config --volumes`) and name each volume's owner project.
- Volumes for long-lived services (Postgres, memory/vector stores, caches shared across projects) are user data, not disposable test fixtures.
- NEVER run `system prune` (especially `-a`/`--volumes`) as troubleshooting; remove only the specific containers or images this session created.
- Containers and volumes this session created for a throwaway test may be removed once their owner process exits.
