from __future__ import annotations

import json
import logging
import os
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Literal, cast, Annotated, TypedDict, Sequence, Callable

from dotenv import load_dotenv
from langchain_neo4j.chains.graph_qa.cypher import GraphCypherQAChain
from langchain.prompts import PromptTemplate
from langchain_neo4j import Neo4jGraph
from langchain_openai import ChatOpenAI
from neo4j.exceptions import CypherSyntaxError
from pydantic import BaseModel, Field, SecretStr, field_validator
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages

from langgraph.graph.state import CompiledStateGraph

from .neo4j import connect_neo4j



LOGGER = logging.getLogger(__name__)

SuggestionStyle = Literal["standard", "creative"]


class AgentState(TypedDict):
    """State for the agent graph."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    issue: Dict[str, Any]
    iterations: int


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


class AdaptationSuggestionGeneratorGraph:
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
        neo4j_graph = connect_neo4j(self._neo4j_config)
        
        # Create the cypher tool
        cypher_chain = self._build_cypher_tool(neo4j_graph, llm)
        cypher_tool_func = self._create_cypher_tool(cypher_chain)
        
        # Build the LangGraph agent
        agent_graph = self._build_agent_graph(llm, [cypher_tool_func])
        
        issue_start_index = self._config["issue_start_index"]
        issue_processing_count = self._config["issue_processing_count"]
        results = []

        # Create separate LLM for structured output (always GPT since of its structured output capabilities)
        output_api_key = api_key
        output_llm = self._create_output_llm(output_api_key)
        
        # Process each issue 
        for issue in issues[issue_start_index:issue_start_index + issue_processing_count]:
            if len(issue["ifc_guids"]) > 10:
                self._logger.info("Skipping issue with IFC GUIDs", extra={"issue": issue})
                continue
            
            self._logger.info("Processing issue", extra={"issue": issue})

            # Invoke the graph with the issue as input
            initial_state: AgentState = {
                "messages": [HumanMessage(content=self._format_issue_input(issue))],
                "issue": issue,
                "iterations": 0
            }
            
            final_state = agent_graph.invoke(initial_state)
            
            # Extract the final answer from the last AI message
            final_answer = self._extract_final_answer(final_state["messages"])
            
            # Use structured output to format the response, ensuring it matches AdaptationPlan (OpenAI models only)
            structured_output_llm = output_llm.with_structured_output(AdaptationPlan)
            plan = cast(AdaptationPlan, structured_output_llm.invoke(self._structured_prompt(issue, final_answer)))
            
            results.append({
                "issue": issue,
                "suggestions": [s.model_dump() for s in plan.suggestions]
            })

        output_path = self._get_next_output_path(self._config["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        self._logger.info("Wrote adaptation plans", extra={"path": str(output_path)})
        return results

    def _create_llm(self, api_key: str) -> ChatOpenAI:
        """Create the main LLM for the agent to do LangGraph Query."""
        return ChatOpenAI(  # type: ignore[arg-type]
            model=self._config["llm_model"],
            temperature=self._config["temperature"],
            api_key=SecretStr(api_key),
            base_url=os.getenv("OPENROUTER_BASE_URL"),
        )
    
    def _create_output_llm(self, api_key: str) -> ChatOpenAI:
        """Create LLM specifically for structured output (always OpenAI)."""

        return ChatOpenAI(  # type: ignore[arg-type]
            model=self._config["structured_output_model"],
            temperature=self._config["temperature"],
            api_key=SecretStr(api_key),
            base_url=os.getenv("OPENROUTER_BASE_URL"),
        )

    def _create_cypher_tool(self, cypher_chain: GraphCypherQAChain):
        """Create a tool function for the cypher chain."""
        @tool
        def graph_cypher_qa(query: str) -> str:
            """Answer building graph questions using Cypher queries.
            
            Use this tool to query the Neo4j graph database about building elements,
            spaces, doors, walls, corridors, stairs, and their relationships.
            
            Args:
                query: A natural language question about the building graph
                
            Returns:
                Results from the graph database query
            """
            try:
                result = cypher_chain.invoke({"query": query})
                return json.dumps(result, ensure_ascii=False, default=str)
            except CypherSyntaxError as exc:
                self._logger.warning("Cypher syntax error", exc_info=exc)
                return json.dumps({"error": str(exc), "results": []})
        
        return graph_cypher_qa


    # SF: Dynamically retrieve the schema and all nodes from the graph db as input to the LLM prompt for generating cypher statements.
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

    def _build_agent_graph(self, llm: ChatOpenAI, tools: List[Callable[[str], str]]) -> CompiledStateGraph[AgentState]:
        """Build a LangGraph-based agent graph."""
        
        # Bind tools to the LLM
        llm_with_tools = llm.bind_tools(tools)
        
        # Define the agent node
        def agent_node(state: AgentState) -> AgentState:
            """Node that calls the LLM to decide next action."""
            system_message = self._create_system_prompt()
            messages = [HumanMessage(content=system_message)] + list(state["messages"])
            
            response = llm_with_tools.invoke(messages)
            
            return {
                "messages": [response],
                "issue": state["issue"],
                "iterations": state["iterations"] + 1
            }
        
        # Define the routing function
        def should_continue(state: AgentState) -> str:
            """Decide whether to continue or end."""
            messages = state["messages"]
            last_message = messages[-1]
            
            # Check if max iterations reached
            if state["iterations"] >= self._config["max_iterations"]:
                return "end"
            
            # If the LLM makes a tool call, continue to tools
            if isinstance(last_message, AIMessage) and hasattr(last_message, "tool_calls") and last_message.tool_calls:
                return "continue"
            
            # Otherwise, end
            return "end"
        
        # Create the graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("agent", agent_node)
        workflow.add_node("tools", ToolNode(tools))
        
        # Set entry point
        workflow.set_entry_point("agent")
        
        # Add conditional edges
        workflow.add_conditional_edges(
            "agent",
            should_continue,
            {
                "continue": "tools",
                "end": END
            }
        )
        
        # Add edge from tools back to agent
        workflow.add_edge("tools", "agent")
        
        # Compile the graph
        return workflow.compile()
    
    def _create_system_prompt(self) -> str:
        """Create the system prompt for the agent."""
        return textwrap.dedent("""
            You are an expert building design assistant helping to resolve building code compliance issues.
            You have access to a Neo4j graph database containing detailed building information.
            
            Important guidelines:
            1. Use the graph_cypher_qa tool to fetch concrete node objects (Spaces, Doors, Walls, Corridors, Stairs, etc.)
            2. Preserve the raw JSON for every retrieved node - do not summarize or rename fields
            3. Query multiple times if needed to gather all relevant information
            4. Assemble enough evidence to propose both standard and creative remediation strategies
            5. When you have gathered sufficient information, provide a comprehensive summary including all the raw node data you retrieved
        """).strip()
    
    def _extract_final_answer(self, messages: Sequence[BaseMessage]) -> str:
        """Extract the final answer from the message history."""
        # Find the last AI message that doesn't have tool calls
        for message in reversed(messages):
            if isinstance(message, AIMessage) and not (hasattr(message, "tool_calls") and message.tool_calls):
                content = message.content
                return content if isinstance(content, str) else str(content)
        
        # Fallback: return the last AI message content
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                content = message.content
                return content if isinstance(content, str) else str(content)
        
        return ""
    
    def _format_issue_input(self, issue: Dict[str, Any]) -> str:
        """Format the issue as input for the agent."""
        issue_json = json.dumps(issue, ensure_ascii=False, indent=2)
        total_suggestions = self._config["total_suggestions"]
        
        return textwrap.dedent(f"""
            I have the following building code compliance issue:
            
            {issue_json}
            
            Task: Analyze this issue and retrieve all relevant building elements from the graph database.
            I need to generate {total_suggestions} adaptation suggestions (both standard and creative approaches).
            
            Please use the graph-cypher-qa tool to:
            1. Find the specific elements mentioned in the issue (by ID, location, or properties)
            2. Retrieve their full details and properties
            3. Find related/connected elements that might be relevant for solutions
            4. Gather enough context to understand the spatial relationships
            
            Return all the raw data you retrieved so I can generate detailed adaptation suggestions.
        """).strip()


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

    def _get_next_output_path(self, base_path: Path) -> Path:
        """Get the next available output path by incrementing a counter."""
        if not base_path.exists():
            return base_path
        
        stem = base_path.stem
        suffix = base_path.suffix
        parent = base_path.parent
        
        counter = 1
        while True:
            new_path = parent / f"{stem}_{counter}{suffix}"
            if not new_path.exists():
                return new_path
            counter += 1