import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from common.paths import PathManager
from common.logger import get_logger

from lpg.RvtBatchRunner import RvtBatchRunner

# Import the refactored modules
# from bcf_handler import (
#     BcfExtractor, 
#     BcfAnalyzer, 
#     ComplianceIssue,
#     IfcInfoProvider,
#     extract_checking_issues
# )
from check.SolibriManager import SolibriManager
from check.ModelProcessor import ModelProcessor, process_model, process_all_models

logger = get_logger(__name__, 'run_sol_acc.log')

def example_batch_processing():
    """Process multiple IFC models sequentially."""
    
    project_root = os.getcwd()
    
    # Initialize Solibri manager
    solibri_manager = SolibriManager(project_root)
    
    # Process all models (or specify a list)
    successful_models = process_all_models(
        project_root=project_root,
        solibri_manager=solibri_manager,
        model_filenames=None,  # None = process all models in directory
        skip_if_exists=True,   # Skip models with existing results
    )
    
    print(f"\n✓ Successfully processed {len(successful_models)} models")
# =============================================================================
# MAIN EXECUTION
# =============================================================================
if __name__ == "__main__":

    example_batch_processing()

    # Choose which example to run
    # Uncomment the example you want to test:
    
    # example_single_model()
    # example_batch_processing()
    # example_with_processor()
    # example_bcf_analysis()
    # example_custom_pipeline()
    # example_update_settings()
    # example_bcf_operations()
    