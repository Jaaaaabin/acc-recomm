"""
One-time environment setup script.
Run with: uv run python scripts/setup_environment.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from src.common.paths import PathManager
from src.common.logger import get_logger

logger = get_logger(__name__, 'setup.log')

def check_platform():
    """Check and display platform information."""
    pm = PathManager()
    logger.info(f"Platform detected: {pm.platform}")
    logger.info(f"Project root: {pm.project_root}")
    logger.info(f"Python version: {sys.version}")
    
    if pm.is_windows():
        logger.info("Windows-specific setup...")
        try:
            import clr
            logger.info("pythonnet available for Revit API access")
        except ImportError:
            logger.warning("pythonnet not available (install with: uv pip install pythonnet)")
    
    elif pm.is_mac():
        logger.info("macOS-specific setup...")
        logger.warning("Note: Revit API not available on macOS")
    
    else:
        logger.info("Linux-specific setup...")


def verify_dependencies():
    """Verify core dependencies are installed."""
    logger.info("Verifying dependencies...")
    
    required = [
        'numpy', 
        'pandas', 
        'networkx', 
        'yaml',
        'transformers', 
        'torch'
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package)
            logger.info(f"{package}")
        except ImportError:
            missing.append(package)
            logger.error(f"{package}")
    
    if missing:
        logger.error(f"Missing packages: {', '.join(missing)}")
        logger.error("Run: uv sync")
        return False
    
    logger.info("All core dependencies verified")
    return True


def download_models():
    """Download required NLP models."""
    logger.info("Downloading NLP models...")
    
    try:
        import spacy
        logger.info("Downloading spacy model...")
        spacy.cli.download("en_core_web_sm")
        logger.info("Spacy model downloaded")
    except Exception as e:
        logger.error(f"Failed to download spacy model: {e}")
    
    logger.info("Model setup complete")



def main():
    """Run full setup process."""
    print("=" * 70)
    print("Regulatory Compliance Framework - Environment Setup")
    print("=" * 70)
    print()
    
    check_platform()
    
    if not verify_dependencies():
        sys.exit(1)
    
    # download_models()
    
    # print()
    # print("=" * 70)
    # print("Setup complete!")
    # print("=" * 70)
    # print()
    # print("Next steps:")
    # print("1. Edit .env file with your API keys")
    # print("2. Run a test: uv run python scripts/run_module_1.py --help")
    # print()


if __name__ == "__main__":
    main()