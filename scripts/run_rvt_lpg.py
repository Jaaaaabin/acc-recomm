import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from common.paths import PathManager
from common.logger import get_logger

from lpg.RvtBatchRunner import RvtBatchRunner

logger = get_logger(__name__, 'run_rvt_lpg.log')

def run_rvt_batch(config_dir=None, rvt_models_dir=None):
    """Run the Revit Batch Processor with specified configuration and models directory."""

    try:
        runner = RvtBatchRunner(config_dir=config_dir, rvt_models_dir=rvt_models_dir)
        logger.info("Revit Batch Processor setup completed successfully.")
    except Exception as e:
        logger.error(f"Error setting up Revit Batch Processor: {e}")
        return

    try:
        runner.run()
        logger.info("Revit Batch Processor ran successfully.")
    except Exception as e:
        logger.error(f"Error running Revit Batch Processor: {e}")

# =============================================================================
# MAIN EXECUTION
# =============================================================================
if __name__ == "__main__":

    pm = PathManager()
    if not pm.is_windows():
        logger.error("Revit Batch Processor can only be run on Windows.")
        sys.exit(1)
    run_rvt_batch()