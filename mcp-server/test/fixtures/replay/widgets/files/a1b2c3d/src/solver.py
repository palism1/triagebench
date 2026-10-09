def resolve(pkg, graph):
    return [resolve(dep, graph) for dep in graph[pkg]]
