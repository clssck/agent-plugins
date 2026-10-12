const API = "https://api.github.com";

function token(): string {
	const value = process.env.GITHUB_TOKEN;
	if (!value) throw new Error("GITHUB_TOKEN is required: GitHub's GraphQL API has no anonymous access");
	return value;
}

/** Execute one GitHub GraphQL request. Callers should batch independent lookups with aliases. */
export async function githubGraphql<T>(query: string): Promise<T> {
	const response = await fetch(API + "/graphql", {
		method: "POST",
		headers: {
			Accept: "application/vnd.github+json",
			Authorization: "Bearer " + token(),
			"User-Agent": "clssck-agent-plugins",
			"X-GitHub-Api-Version": "2022-11-28",
		},
		body: JSON.stringify({ query }),
	});
	const body = (await response.json()) as { data?: T; errors?: Array<{ message: string }> };
	if (!response.ok || body.errors?.length || !body.data) {
		throw new Error(
			"GitHub GraphQL " + response.status + ": " +
			(body.errors?.map(error => error.message).join("; ") ?? "missing data"),
		);
	}
	return body.data;
}

/** Build a GraphQL repository selector from an owner/name slug. */
export function githubRepositoryField(repository: string): string {
	const parts = repository.split("/");
	if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error("Invalid GitHub repository: " + repository);
	return "repository(owner: " + JSON.stringify(parts[0]) + ", name: " + JSON.stringify(parts[1]) + ")";
}
