# acc-recomm
Advancing Regulatory Compliance Beyond Checking through Object-Driven Adaptation Recommendations.

## setup uv 
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

4. Run your main script
```bash
uv run python main.py
```

## switch to network path.
1. Register the network disk
```bash
net use H: \\nas.ads.mwn.de\ge58quh
```