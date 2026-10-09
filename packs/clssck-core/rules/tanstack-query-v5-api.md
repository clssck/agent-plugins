---
description: TanStack Query v4 call forms and the fetchQuery/prefetchQuery/ensureQueryData methods deprecated in v5.102
condition:
- \buse(?:Query|Mutation|InfiniteQuery|IsFetching|IsMutating)\(\s*\[|\buseMutation\(\s*(?:async\s*)?(?:\([^)]*\)|\w+)\s*=>|\bcacheTime\s*:|\bkeepPreviousData\s*:\s*true|\buseErrorBoundary\s*:|\bisPreviousData\b|['"]react-query['"]|\.(?:fetchQuery|prefetchQuery|ensureQueryData|fetchInfiniteQuery|prefetchInfiniteQuery|ensureInfiniteQueryData)\s*\(
scope:
- tool:edit(**/*.{ts,tsx,js,jsx,vue,svelte})
- tool:write(**/*.{ts,tsx,js,jsx,vue,svelte})
interruptMode: never
---

**Use the current TanStack Query v5 API; check `@tanstack/*-query` in `package.json`.**

| Old | Current |
|---|---|
| `useQuery(['key'], fn)`, `useMutation(fn)` | object form: `useQuery({ queryKey, queryFn })`, `useMutation({ mutationFn })` |
| `cacheTime`, `useErrorBoundary`, `keepPreviousData: true`, `isPreviousData` | `gcTime`, `throwOnError`, `placeholderData: keepPreviousData` with `isPlaceholderData` |
| `'react-query'` import | `'@tanstack/react-query'` |
| `queryClient.fetchQuery(opts)` | `queryClient.query(opts)` |
| `queryClient.prefetchQuery(opts)` | `queryClient.query(opts).catch(noop)` |
| `queryClient.ensureQueryData(opts)` | `queryClient.query({ ...opts, staleTime: 'static' })` |
| `fetchInfiniteQuery` / `prefetchInfiniteQuery` / `ensureInfiniteQueryData` | `queryClient.infiniteQuery(...)` with the same patterns |

The `fetch`/`prefetch`/`ensure` methods are deprecated since 5.102 (August 2026) and will be removed in the next major version. On an older 5.x, keep them.

Source: https://tanstack.com/query/latest/docs/framework/react/reference/classes/QueryClient
