# acc-recomm
Advancing Regulatory Compliance Beyond Checking through Object-Driven Adaptation Recommendations.

## setup uv 
1. Create a virtual environment with Python 3.11
```bash
uv venv yourvenvname --python "py -3.11"
```

2. Activate the environment
```bash
yourvenvname\Scripts\activate.bat
```

3. Link uv to this environment
```bash
set UV_PROJECT_ENVIRONMENT=yourvenvname
```

4. Verify Python version inside the environment
```bash
uv run python --version
```

5. Install all project dependencies
```bash
uv sync
```

6. Run your main script
```bash
uv run python main.py
```

