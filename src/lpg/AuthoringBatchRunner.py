"""
AuthoringCall.py
----------------
Foundation module for Revit model authoring workflow.
Contains core classes for model duplication and batch processing.
"""

from pathlib import Path
import shutil
import subprocess
import json
import sys
from pathlib import Path

# Add src directory to Python path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from common.paths import get_path

class AuthoringBatchRunner:

    def __init__(self, config_dir=None, rvt_models_dir=None):
        """
        Initializes the batch runner.

        Parameters:
            settings_file (str or Path): Path to the .json settings file.
            exe_path (str or Path): Path to BatchRvt.exe. Defaults to standard LOCALAPPDATA path.
        """

        default_exe_path = Path.home() / "AppData/Local/RevitBatchProcessor/BatchRvt.exe"
        self.exe_path = default_exe_path

        config_dir = Path(config_dir) if config_dir else None

        if not self.exe_path.exists():
            raise FileNotFoundError("BatchRvt.exe not found at {}".format(self.exe_path))

        self._update_configuration(config_rvt_batch_dir=config_dir, rvt_models_dir=rvt_models_dir)
    
    def _update_configuration(self, config_rvt_batch_dir=None, rvt_models_dir=None):
        """
        Updates the configuration files for Revit batch processing.
        
        Parameters:
            config_rvt_batch_dir (Path): Directory containing batch configuration files
            rvt_models_dir (Path): Directory containing .rvt model files
        """
        if config_rvt_batch_dir is None:
            config_rvt_batch_dir = get_path('config', 'rvt')
        
        config_rvt_batch_dir = Path(config_rvt_batch_dir) # type: ignore
        config_rvt_batch_list_file = config_rvt_batch_dir / "RvtBatch.txt"
        config_rvt_batch_setting_file = config_rvt_batch_dir / "RvtBatch.Settings.json"
        
        # Create directory if it doesn't exist
        config_rvt_batch_list_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Write the list of .rvt files to RvtBatch.txt
        rvt_models_dir = Path(rvt_models_dir) # type: ignore
        with open(config_rvt_batch_list_file, 'w', encoding='utf-8') as f:
            for rvt_model in rvt_models_dir.glob("*.rvt"):
                f.write(str(rvt_model.resolve()) + '\n')
        
        # Update the JSON settings file
        if config_rvt_batch_setting_file.exists():
            with open(config_rvt_batch_setting_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        else:
            # Create default settings if file doesn't exist
            settings = {}
        
        # Update the file paths in the settings
        revit_file_list_path = get_path('config', 'rvt', 'RvtBatch.txt')
        task_script_path = get_path('config', 'rvt', 'RvtBatch.py')
        
        # Check if files exist before updating paths# type: ignore
        if Path(revit_file_list_path).exists(): # type: ignore
            settings["revitFileListFilePath"] = str(Path(revit_file_list_path).resolve()) # type: ignore
        
        if Path(task_script_path).exists(): # type: ignore
            settings["taskScriptFilePath"] = str(Path(task_script_path).resolve()) # type: ignore
        
        # Write the updated settings back to the file
        with open(config_rvt_batch_setting_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def run(self, verbose=True):
        """
        Runs BatchRvt.exe with the specified settings file.

        Parameters:
            verbose (bool): Whether to print output (default: True).
        """
        # Get the settings file path from the configuration
        settings_file = get_path('config', 'rvt', 'RvtBatch.Settings.json')
        
        command = [
            str(self.exe_path),
            "--settings_file",
            str(settings_file)
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=not verbose,
                text=True,
                check=True
            )
            if verbose:
                print(result.stdout)
        except subprocess.CalledProcessError as e:
            print("[ERROR] BatchRvt.exe failed.")
            if e.stderr:
                print(e.stderr)
            raise

def debug_authoring_batch_runner():

    """Debug function to test the AuthoringBatchRunner class."""
    print("=== AuthoringBatchRunner Debug ===")
    
    # Test paths
    project_root = Path(__file__).parent.parent.parent
    config_dir = project_root / "config" / "rvt"
    rvt_models_dir = project_root / "data" / "bim_models"
    
    print(f"Project root: {project_root}")
    print(f"Config directory: {config_dir}")
    print(f"RVT models directory: {rvt_models_dir}")
    print()
    
    # Check if directories exist
    print("Directory checks:")
    print(f"  Config dir exists: {config_dir.exists()}")
    print(f"  RVT models dir exists: {rvt_models_dir.exists()}")
    
    if rvt_models_dir.exists():
        rvt_files = list(rvt_models_dir.glob("*.rvt"))
        print(f"  Found {len(rvt_files)} .rvt files:")
        for rvt_file in rvt_files:
            print(f"    - {rvt_file.name}")
    print()
    
    try:
        # Test 1: Initialize with default paths
        print("Test 1: Initialize with default paths")
        runner = AuthoringBatchRunner()
        print("✓ Initialization successful")
        print(f"  Exe path: {runner.exe_path}")
        print(f"  Exe exists: {runner.exe_path.exists()}")
        print()
        
    except Exception as e:
        print(f"✗ Test 1 failed: {e}")
        print()
    
    try:
        # Test 2: Initialize with custom paths
        print("Test 2: Initialize with custom paths")
        runner = AuthoringBatchRunner(
            config_dir=config_dir,
            rvt_models_dir=rvt_models_dir
        )
        print("✓ Initialization successful")
        print()
        
    except Exception as e:
        print(f"✗ Test 2 failed: {e}")
        print()
    
    try:
        # Test 3: Check generated files
        print("Test 3: Check generated configuration files")
        
        batch_list_file = config_dir / "RvtBatch.txt"
        batch_settings_file = config_dir / "RvtBatch.Settings.json"
        
        print(f"  Batch list file: {batch_list_file}")
        print(f"  Batch list exists: {batch_list_file.exists()}")
        
        if batch_list_file.exists():
            with open(batch_list_file, 'r') as f:
                content = f.read().strip()
                lines = content.split('\n') if content else []
                print(f"  Batch list contains {len(lines)} files")
                for line in lines[:3]:  # Show first 3 lines
                    print(f"    - {Path(line).name}")
                if len(lines) > 3:
                    print(f"    ... and {len(lines) - 3} more")
        
        print(f"  Batch settings file: {batch_settings_file}")
        print(f"  Batch settings exists: {batch_settings_file.exists()}")
        
        if batch_settings_file.exists():
            with open(batch_settings_file, 'r') as f:
                settings = json.load(f)
                print(f"  Settings keys: {list(settings.keys())}")
                if "revitFileListFilePath" in settings:
                    print(f"  Revit file list path: {settings['revitFileListFilePath']}")
                if "taskScriptFilePath" in settings:
                    print(f"  Task script path: {settings['taskScriptFilePath']}")
        print()
        
    except Exception as e:
        print(f"✗ Test 3 failed: {e}")
        print()
    
    try:
        # Test 4: Test run method (dry run - don't actually execute)
        print("Test 4: Test run method (dry run)")
        runner = AuthoringBatchRunner(config_dir=config_dir, rvt_models_dir=rvt_models_dir)
        
        # Check if BatchRvt.exe exists before trying to run
        if runner.exe_path.exists():
            print(f"  BatchRvt.exe found at: {runner.exe_path}")
            print("  Note: Not actually running BatchRvt.exe in debug mode")
            print("  To run: runner.run(verbose=True)")
        else:
            print(f"  [FAIL] BatchRvt.exe not found at: {runner.exe_path}")
            print("  Please install Revit Batch Processor or update the path")
        print()
        
    except Exception as e:
        print(f"✗ Test 4 failed: {e}")
        print()
    
    print("=== Debug Complete ===")
    
if __name__ == "__main__":
    """
    Debug function for testing AuthoringBatchRunner class.
    """
    debug_authoring_batch_runner()
