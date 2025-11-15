from __future__ import annotations

import logging
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from recommendation.adaptation_suggestion_generator import AdaptationSuggestionGenerator
from recommendation.adaptation_suggestion_generator_graph import AdaptationSuggestionGeneratorGraph
from recommendation.configuration import (
    get_graph_config,
    get_neo4j_config,
    get_suggestions_config,
    load_config,
)
from recommendation.knowledge_graph_builder import KnowledgeGraphBuilder


def main() -> None:
    """Build the graph (if needed) and generate adaptation suggestions."""
    config = load_config()
    
    neo4j_config = get_neo4j_config(config)
    graph_config = get_graph_config(config)
    suggestions_config = get_suggestions_config(config)

    logging.basicConfig(level=logging.DEBUG if suggestions_config["verbose"] else logging.INFO)

    KnowledgeGraphBuilder(neo4j_config, graph_config).build(
        force=graph_config["force"],
    )

    generator = AdaptationSuggestionGeneratorGraph(neo4j_config, suggestions_config)
    # generator = AdaptationSuggestionGenerator(neo4j_config, suggestions_config)
    results = generator.generate()
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
