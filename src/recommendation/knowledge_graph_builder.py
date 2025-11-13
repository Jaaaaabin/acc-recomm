from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from .neo4j import connect_neo4j

LOGGER = logging.getLogger(__name__)

RELATION_LABELS: Dict[str, str] = {
    "e-adjacent_connectivity": "ADJACENT",
    "e-spatial_containment": "CONTAINED",
    "e-structural_support": "SUPPORTS",
    "e-accessible_connectivity": "ACCESSIBLE",
    "e-locational_alignment": "ALIGNED",
}


@dataclass(frozen=True)
class GraphData:
    nodes: Dict[str, Dict[str, Any]]
    relationships: Dict[str, List[Tuple[str, str]]]

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def relationship_count(self) -> int:
        return sum(len(edges) for edges in self.relationships.values())


class KnowledgeGraphBuilder:
    def __init__(
        self,
        neo4j_config: Dict[str, Any],
        graph_config: Dict[str, Any],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._neo4j_config = neo4j_config
        self._config = graph_config
        self._logger = logger or LOGGER

    @property
    def data_dir(self) -> Path:
        return self._config["data_dir"]

    def load_graph_data(self) -> GraphData:
        data_dir = self.data_dir
        if not data_dir.exists():
            raise FileNotFoundError(f"Graph data directory does not exist: {data_dir}")

        vertex_files = sorted(data_dir.glob("v-*.json"))
        edge_files = sorted(data_dir.glob("e-*.json"))
        if not vertex_files:
            raise FileNotFoundError(f"No vertex files found in {data_dir}")

        self._logger.info(
            "Loading graph data", extra={"vertices": len(vertex_files), "edges": len(edge_files)}
        )

        nodes: Dict[str, Dict[str, Any]] = {}
        for v_file in vertex_files:
            vertex_type = v_file.stem[2:]
            with v_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            for node_id, properties in payload.items():
                properties["node_type"] = vertex_type
                nodes[node_id] = properties

        relationships: Dict[str, List[Tuple[str, str]]] = {}
        for e_file in edge_files:
            rel_label = RELATION_LABELS.get(e_file.stem)
            if rel_label is None:
                self._logger.warning("Skipping unknown edge file type", extra={"file": e_file.name})
                continue
            with e_file.open("r", encoding="utf-8") as handle:
                edge_payload = json.load(handle)

            flat_edges: List[Tuple[str, str]] = []
            for edge_list in edge_payload.values():
                flat_edges.extend((pair[0], pair[1]) for pair in edge_list)

            relationships.setdefault(rel_label, []).extend(flat_edges)

        self._logger.info(
            "Aggregated graph data",
            extra={
                "nodes": len(nodes),
                "relationships": sum(len(edges) for edges in relationships.values()),
            },
        )
        return GraphData(nodes=nodes, relationships=relationships)

    def _clear_database(self, graph: Any) -> None:
        self._logger.debug("Clearing Neo4j database")
        graph.query("MATCH (n) DETACH DELETE n")

    def _chunked(self, iterable: Iterable[Any], chunk_size: int) -> Iterable[List[Any]]:
        batch: List[Any] = []
        for item in iterable:
            batch.append(item)
            if len(batch) == chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch

    def _create_nodes(self, graph: Any, nodes: Dict[str, Dict[str, Any]]) -> None:
        self._logger.info("Creating %d nodes", len(nodes))
        for batch in self._chunked(nodes.items(), self._config["batch_size"]):
            for node_id, properties in batch:
                node_type = properties.get("node_type", "Entity")
                label = node_type.capitalize()
                props = {k: v for k, v in properties.items() if k != "node_type"}
                props["id"] = node_id
                query = f"CREATE (n:{label}) SET n += $props"
                graph.query(query, params={"props": props})

    def _create_relationships(self, graph: Any, relationships: Dict[str, List[Tuple[str, str]]]) -> None:
        total_rel = sum(len(edges) for edges in relationships.values())
        self._logger.info("Creating %d relationships", total_rel)
        for rel_type, edges in relationships.items():
            query = (
                "MATCH (a {id: $from_id}) "
                "MATCH (b {id: $to_id}) "
                f"CREATE (a)-[:{rel_type}]->(b)"
            )
            for batch in self._chunked(edges, self._config["batch_size"]):
                for from_id, to_id in batch:
                    graph.query(query, params={"from_id": from_id, "to_id": to_id})

    def _graph_counts(self, graph: Any) -> Tuple[int, int]:
        nodes = graph.query("MATCH (n) RETURN count(n) as count")
        rels = graph.query("MATCH ()-[r]->() RETURN count(r) as count")
        node_count = nodes[0]["count"] if nodes else 0
        rel_count = rels[0]["count"] if rels else 0
        self._logger.debug("Existing graph counts", extra={"nodes": node_count, "relationships": rel_count})
        return node_count, rel_count

    def _graph_is_current(self, graph: Any, expected: GraphData) -> bool:
        node_count, relationship_count = self._graph_counts(graph)
        if node_count == 0 and relationship_count == 0:
            return False
        matches_nodes = node_count == expected.node_count
        matches_relationships = relationship_count == expected.relationship_count
        if not matches_nodes or not matches_relationships:
            self._logger.info(
                "Graph counts do not match expected data",
                extra={
                    "existing_nodes": node_count,
                    "expected_nodes": expected.node_count,
                    "existing_relationships": relationship_count,
                    "expected_relationships": expected.relationship_count,
                },
            )
        return matches_nodes and matches_relationships

    def build(self, *, force: bool | None = None) -> bool:
        graph_data = self.load_graph_data()
        graph = connect_neo4j(self._neo4j_config)

        should_force = self._config.get("force", False) if force is None else force
        needs_refresh = should_force or not self._graph_is_current(graph, graph_data)
        if not needs_refresh:
            self._logger.info("Existing Neo4j graph matches the dataset; skipping rebuild")
            return False

        self._logger.info("Refreshing Neo4j graph data")
        self._clear_database(graph)
        self._create_nodes(graph, graph_data.nodes)
        self._create_relationships(graph, graph_data.relationships)
        self._logger.info("Graph rebuild complete")
        return True

