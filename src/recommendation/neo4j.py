from __future__ import annotations

import logging
from typing import Any, Dict

from langchain_neo4j import Neo4jGraph
from neo4j import GraphDatabase
from neo4j.exceptions import Neo4jError

LOGGER = logging.getLogger(__name__)


def _ensure_database_exists(config: Dict[str, Any]) -> None:
    driver = GraphDatabase.driver(config["uri"], auth=(config["username"], config["password"]))
    try:
        with driver.session(database="system") as session:
            LOGGER.debug("Checking for existing Neo4j database", extra={"database": config["database"]})
            records = list(session.run("SHOW DATABASES"))  # pyright: ignore[reportArgumentType]
            existing_names = {record["name"] for record in records}
            if config["database"] in existing_names:
                current_status = next(
                    (record["currentStatus"] for record in records if record["name"] == config["database"]),
                    "offline",
                )
                if current_status.lower() != "online":
                    LOGGER.info("Waiting for Neo4j database '%s' to become available", config["database"])
                    session.run(f"ALTER DATABASE `{config['database']}` WAIT 300")  # pyright: ignore[reportArgumentType]
                return

            LOGGER.info("Creating Neo4j database '%s'", config["database"])
            session.run(f"CREATE DATABASE `{config['database']}` IF NOT EXISTS WAIT 300")  # pyright: ignore[reportArgumentType]
    except Neo4jError as exc:
        LOGGER.error("Failed to ensure Neo4j database exists: %s", exc)
        raise
    finally:
        driver.close()


def connect_neo4j(config: Dict[str, Any]) -> Neo4jGraph:
    _ensure_database_exists(config)
    LOGGER.debug(
        "Connecting to Neo4j",
        extra={"uri": config["uri"], "database": config["database"]},
    )
    return Neo4jGraph(
        url=config["uri"],
        username=config["username"],
        password=config["password"],
        database=config["database"],
    )

