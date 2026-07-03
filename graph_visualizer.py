import matplotlib.pyplot as plt
import networkx as nx


def visualize_graph(adjacency_graph):
    """Visualizes an adjacency graph using networkx and matplotlib."""

    graph = nx.DiGraph()  # Use DiGraph for directed graph

    for node, edges in adjacency_graph.items():
        for edge in edges:
            graph.add_edge(node, edge["other_id"], weight=edge["similarity"])

    pos = nx.spring_layout(graph)  # Node positioning for visualization

    # Get edge weights and normalize them
    weights = [edge["weight"] for u, v, edge in graph.edges(data=True)]
    normalized_weights = [(w - min(weights)) / (max(weights) - min(weights)) for w in weights]

    # Create a color map
    cmap = plt.cm.viridis

    # Map normalized weights to colors
    edge_colors = [cmap(w) for w in normalized_weights]

    nx.draw(graph, pos, with_labels=True, node_size=1500, node_color="skyblue", font_size=10, edge_color=edge_colors)
    edge_labels = nx.get_edge_attributes(graph, "weight")
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, font_size=8)

    plt.title("Adjacency Graph")
    plt.show()


if __name__ == "__main__":
    adjacency_graph = {
        "G3250": [
            {"other_id": "E2029", "similarity": 0.8886164931432184},
            {"other_id": "G4687", "similarity": 0.7799796722164661},
            {"other_id": "G2491", "similarity": 0.7358682896118928},
        ],
        "E2029": [
            {"other_id": "G3250", "similarity": 0.589185898055919},
            {"other_id": "G4687", "similarity": 0.5547903202019775},
            {"other_id": "G2491", "similarity": 0.4763465778429552},
        ],
        "G4687": [
            {"other_id": "G3250", "similarity": 0.8534847661087587},
            {"other_id": "E2029", "similarity": 0.382888810662511},
            {"other_id": "G2491", "similarity": 0.9591597530883424},
        ],
        "G2491": [
            {"other_id": "G3250", "similarity": 0.11935305775711214},
            {"other_id": "E2029", "similarity": 0.3629634156202275},
            {"other_id": "G4687", "similarity": 0.810511185411589},
        ],
    }
    visualize_graph(adjacency_graph)
