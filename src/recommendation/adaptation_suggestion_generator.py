from __future__ import annotations

import json
import logging
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, cast

from dotenv import load_dotenv
from langchain.agents import AgentExecutor, AgentType, Tool, initialize_agent
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain
from langchain.prompts import PromptTemplate
from langchain_neo4j import Neo4jGraph
from langchain_openai import ChatOpenAI
from neo4j.exceptions import CypherSyntaxError
from pydantic import BaseModel, Field, SecretStr, field_validator

from .neo4j import connect_neo4j

LOGGER = logging.getLogger(__name__)

SuggestionStyle = Literal["standard", "creative"]


class Suggestion(BaseModel):
    style: SuggestionStyle = Field(
        default="standard",
        description="Tone of the action (standard vs creative).",
    )
    objects_json: str = Field(
        default="[]",
        description="JSON array string of the primary graph objects involved.",
    )
    context_json: str = Field(
        default="[]",
        description="Optional JSON array string of supporting context objects.",
    )
    ids: List[str] = Field(
        default_factory=list,
        description="Graph node ids extracted from the referenced objects.",
    )
    action: str = Field(description="Concise action proposal.")
    reasoning: str = Field(description="Brief justification referencing retrieved nodes.")

    @property
    def objects(self) -> List[Dict[str, Any]]:
        return json.loads(self.objects_json or "[]")

    @property
    def context(self) -> List[Dict[str, Any]]:
        return json.loads(self.context_json or "[]")

    @field_validator("objects_json")
    @classmethod
    def validate_objects_json(cls, value: str) -> str:
        json.loads(value or "[]")
        return value

    @field_validator("context_json")
    @classmethod
    def validate_context_json(cls, value: str) -> str:
        json.loads(value or "[]")
        return value


class AdaptationPlan(BaseModel):
    suggestions: List[Suggestion] = Field(
        default_factory=list,
        description="Ordered adaptation suggestions.",
    )


class AdaptationSuggestionGenerator:
    def __init__(
        self,
        neo4j_config: Dict[str, Any],
        suggestions_config: Dict[str, Any],
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._neo4j_config = neo4j_config
        self._config = suggestions_config
        self._logger = logger or LOGGER

    def generate(self) -> List[Dict[str, Any]]:
        issues = self._load_issues(self._config["issues_path"])

        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if api_key is None:
            raise RuntimeError("Missing OPENROUTER_API_KEY or OPENAI_API_KEY environment variable.")

        llm = self._create_llm(api_key)
        graph = connect_neo4j(self._neo4j_config)
        cypher_tool = self._build_cypher_tool(graph, llm)
        tool = Tool(
            name="graph-cypher-qa",
            func=lambda query: self._run_cypher_tool(cypher_tool, query),
            description="Answer building graph questions using Cypher.",
        )

        agent = self._build_agent(tool, llm)
        
        issue_start_index = self._config["issue_start_index"]
        issue_processing_count = self._config["issue_processing_count"]
        results = []
        for issue in issues[issue_start_index:issue_start_index + issue_processing_count]:
            agent_output = agent.run(self._agent_prompt(issue))
            structured_llm = llm.with_structured_output(AdaptationPlan)
            plan = cast(AdaptationPlan, structured_llm.invoke(self._structured_prompt(issue, agent_output)))
            results.append({
                "issue": issue,
                "suggestions": [s.model_dump() for s in plan.suggestions]
            })

        output_path = self._config["output_path"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        self._logger.info("Wrote adaptation plans", extra={"path": str(output_path)})
        return results

    def _create_llm(self, api_key: str) -> ChatOpenAI:
        return ChatOpenAI(  # type: ignore[arg-type]
            model=self._config["llm_model"],
            temperature=self._config["temperature"],
            api_key=SecretStr(api_key),
            base_url=os.getenv("OPENROUTER_BASE_URL"),
        )

    def _build_agent(self, tool: Tool, llm: ChatOpenAI) -> AgentExecutor:
        return initialize_agent(
            tools=[tool],
            llm=llm,
            agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=self._config["verbose"],
            max_iterations=self._config["max_iterations"],
            early_stopping_method="generate",
            handle_parsing_errors=True,
        )

    def _build_cypher_tool(self, graph: Neo4jGraph, llm: ChatOpenAI) -> GraphCypherQAChain:
        schema_query = """
        CALL apoc.meta.schema() YIELD value
        UNWIND keys(value) AS name
        WITH name, value[name] AS data
        WHERE data.type IN ['node', 'relationship']
        RETURN name, data.type AS type, keys(data.properties) AS properties
        ORDER BY type, name
        """
        schema_result = graph.query(schema_query)

        all_nodes_query = """
        MATCH (n)
        WHERE size(labels(n)) > 0
        WITH labels(n)[0] AS label, collect(n) AS nodes
        RETURN label, nodes[0] AS sampleNode
        """
        all_nodes_result = graph.query(all_nodes_query)

        prompt_template = """Task:Generate Cypher statement to query a graph database.
Instructions:
Use only the provided relationship types and properties in the schema. Do not use any other relationship types or properties that are not provided.
Schema:
{schema}
Note: Do not include any explanations or apologies in your responses.
Do not respond to any questions that might ask anything else than for you to construct a Cypher statement.
Do not include any text except the generated Cypher statement.
Be specific with your Cypher statements. You can make it less restrictive in a second step if no results are found.

For example, if one wants to retrieve examples for all the nodes, one could use the following Cypher statement:
- Example query: {all_nodes_query}
- Example result: {all_nodes}

The question is:
{question}"""

        prompt = PromptTemplate.from_template(prompt_template).partial(
            schema=json.dumps(schema_result, ensure_ascii=False),
            all_nodes_query=all_nodes_query.strip(),
            all_nodes=json.dumps(all_nodes_result, ensure_ascii=False),
        )

        chain = GraphCypherQAChain.from_llm(
            llm=llm,
            graph=graph,
            allow_dangerous_requests=True,
            verbose=self._config["verbose"],
            return_intermediate_steps=True,
            cypher_prompt=prompt,
        )

        return chain

    def _run_cypher_tool(self, chain: GraphCypherQAChain, query: str) -> Dict[str, Any]:
        try:
            return chain.invoke({"query": query})
        except CypherSyntaxError as exc:
            self._logger.warning("Cypher syntax error", exc_info=exc)
            return {"error": str(exc), "results": []}

    def _agent_prompt(self, issue: Dict[str, Any]) -> str:
        issue_json = json.dumps(issue, ensure_ascii=False)
        total_suggestions = self._config["total_suggestions"]
        return textwrap.dedent(
            f"""
            I've got the following issue:
            <issue>{issue_json}</issue>

            Objectives:
            1. Use the `graph-cypher-qa` tool to fetch the concrete node objects involved (Spaces, Doors, Walls, Corridors, Stairs, etc.).
            2. Preserve the raw JSON for every retrieved node; do not summarise or rename fields.
            3. Assemble enough evidence to propose both standard and creative remediation strategies.

            Response rules:
            - Provide exactly {total_suggestions} candidate adaptations.
            - Each suggestion must reference the specific node ids retrieved via the tool.
            - Return the final JSON between <final_answer>...</final_answer>.
            """
        ).strip()

    def _structured_prompt(self, issue: Dict[str, Any], agent_answer: str) -> str:
        total = self._config["total_suggestions"]
        standard = self._config["standard_suggestions"]
        creative = self._config["creative_suggestions"]
        
        rules = [
            f"Produce exactly {total} suggestions.",
            "For each suggestion, set 'objects_json' to a JSON array string containing the exact nodes to modify.",
            "Use 'context_json' to capture additional supporting nodes when needed.",
            "Populate 'ids' with every 'id' appearing in either JSON array.",
            "Keep 'action' concise and 'reasoning' tied to the retrieved geometry.",
        ]
        if standard and creative:
            rules.append(
                f"Mark the first {standard} suggestions with style 'standard' "
                f"and the remaining {creative} suggestions with style 'creative'."
            )
        elif standard:
            rules.append("Mark every suggestion with style 'standard'.")
        else:
            rules.append("Mark every suggestion with style 'creative'.")

        instructions = " ".join(rules)
        return textwrap.dedent(
            f"""
            Issue: {json.dumps(issue, ensure_ascii=False)}
            AgentAnswer: {agent_answer}
            {instructions}
            """
        ).strip()

    def _load_issues(self, path: Path) -> List[Dict[str, Any]]:
        return json.loads(path.read_text(encoding="utf-8"))

    def _select_issue(self, issues: List[Dict[str, Any]], index: int) -> Dict[str, Any]:
        return issues[index]

