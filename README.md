# **acc-recomm**
Advancing Regulatory Compliance Beyond Checking through LLM-Driven Reasoning for Adaptation Recommendation.

## **Setup**
### Setup uv 
1. Create a virtual environment with Python 3.11
```bash
uv venv yourvenvname --python "py -3.11"
```

2. Verify Python version inside the environment
```bash
uv run python --version
```

3. Install all project dependencies
```bash
uv sync
```

### Setup Batch Process for Autodesk Revit
1. **tbd** 
2. **tbd**

### Setup Autorun Process for Solibri
1. **tbd** 
2. **tbd**

### Setup Neo4j and Environment

1. **Install Neo4j Desktop**
   - Download from: https://neo4j.com/download/
   - Create a new database, set a password, REMEMBER it (your_neo4j_password)
   - Install the **APOC plugin** from the Plugins tab
   - Start the database

2. **Create `.env` file** in project root:
```properties
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
LLM_MODEL=XXXXXX
XXXXX_API_KEY=your_api_key
```

## Pipeline Execution
1. **Revit pipeline**
```bash
uv run python scripts/run_rvt_lpg.py
```

2. **Solirbi pipeline**
```bash
uv run python scripts/run_sol_acc.py
```

3. **Garph + LLM pipeline**
```bash
uv run python scripts/run_llm_pipeline.py
```

## Additional Notes

1. **Switch to Network Path (Register first)**
    
```bash
# necessary for Wins system when running with admin rights.
net use H: \\nas.ads.mwn.de\ge58quh
```

2. **Git Configuration for Local Changes**

```bash
# Ignore local changes to uv.lock (might happen after 'uv sync')
git update-index --skip-worktree uv.lock 

# To undo (if needed)
git update-index --no-skip-worktree uv.lock
```