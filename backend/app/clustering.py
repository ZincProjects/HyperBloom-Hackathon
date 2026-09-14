"""Union-find over incident_links: connected components = attacker clusters / campaigns."""


class UnionFind:
    def __init__(self, items=()):
        self.parent = {i: i for i in items}

    def find(self, x):
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            # Keep the smallest incident id as the root so cluster ids are stable.
            lo, hi = sorted((ra, rb))
            self.parent[hi] = lo


def build_clusters(incident_ids, links) -> dict[int, list[int]]:
    """Return {cluster_id: sorted member incident ids}; cluster_id is the lowest member id."""
    uf = UnionFind(incident_ids)
    for link in links:
        uf.union(link.incident_a_id, link.incident_b_id)
    clusters: dict[int, list[int]] = {}
    for iid in list(uf.parent):
        clusters.setdefault(uf.find(iid), []).append(iid)
    return {root: sorted(members) for root, members in clusters.items()}


def cluster_index(clusters: dict[int, list[int]]) -> dict[int, int]:
    return {member: root for root, members in clusters.items() for member in members}
