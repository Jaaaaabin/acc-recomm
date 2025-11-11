import sys
from pathlib import Path

# --- Path setup --------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
from common.logger import get_logger

# --- Pipeline dependencies ---------------------------------------------------
from check.BcfHandler import analyze_bcf_projects
from check.SolibriManager import SolibriManager
from check.ModelProcessor import process_all_models

logger = get_logger(__name__, 'run_sol_acc.log')

def batch_processing_solibri(model_filenames=None):
    """Run Solibri batch checks for the provided IFC models (or all available)."""

    # --- Initialize Solibri manager -----------------------------------------
    solibri_manager = SolibriManager() # type: ignore

    # --- Execute Solibri pipeline -------------------------------------------
    successful_models = process_all_models(
        solibri_manager=solibri_manager,
        model_filenames=model_filenames,  # None = process all models in the defined directory
        skip_if_exists=True,   # Skip checking ifc models with existing results
    )

    print(f"\n✓ Successfully processed  models:{successful_models}.")

    return successful_models

def main():
    
    """Execute Solibri batch run followed by BCF analysis."""

    # --- Run Solibri checks --------------------------------------------------
    checked_model_filenames = batch_processing_solibri()

    # --- Analyze resulting BCF packages -------------------------------------
    # checked_model_filenames = ['case-autcon']
    analyze_bcf_projects(model_names=checked_model_filenames)


# =============================================================================
# MAIN EXECUTION
# =============================================================================
if __name__ == "__main__":

    main()

