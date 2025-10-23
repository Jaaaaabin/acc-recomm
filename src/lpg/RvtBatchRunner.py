"""
AuthoringCall.py
----------------
Foundation module for Revit model authoring workflow.
Contains core classes for model duplication and batch processing.
"""

from pathlib import Path
import os
import subprocess
import json
import sys

# Add src directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from common.paths import get_path

class RvtBatchRunner:

    def __init__(self, config_dir=None, rvt_models_dir=None):
        """
        Initializes the batch runner.

        Parameters:
            settings_file (str or Path): Path to the .json settings file.
            exe_path (str or Path): Path to BatchRvt.exe. Defaults to standard LOCALAPPDATA path.
        """

        config_dir = Path(config_dir) if config_dir else None
        self.exe_path = Path.home() / "AppData/Local/RevitBatchProcessor/BatchRvt.exe"
        if not self.exe_path.exists():
            raise FileNotFoundError("BatchRvt.exe not found at {}".format(self.exe_path))
        
        self.settings_file = ''
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
        if rvt_models_dir is None:
            rvt_models_dir = get_path('data', 'bim_models')

        config_rvt_batch_dir = Path(config_rvt_batch_dir)
        rvt_batch_setting_file = os.path.join(config_rvt_batch_dir, "RvtBatch.Settings.json")
        self.settings_file = rvt_batch_setting_file

        rvt_batch_list_file = os.path.join(config_rvt_batch_dir, "RvtBatch.txt")
        rvt_script_file = os.path.join(config_rvt_batch_dir, "RvtBatch.py")
        
        # Write the list of .rvt files to RvtBatch.txt
        with open(rvt_batch_list_file, 'w', encoding='utf-8') as f:
            for rvt_model in rvt_models_dir.glob("*.rvt"):
                f.write(str(rvt_model.resolve()) + '\n')

        # Update the JSON settings file
        if Path(rvt_batch_setting_file).exists():
            with open(rvt_batch_setting_file, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        else:
            # Create default settings if file doesn't exist
            settings = {}
        
        # Check if files exist before updating paths
        if Path(rvt_batch_list_file).exists():
            settings["revitFileListFilePath"] = str(Path(rvt_batch_list_file).resolve())
        
        if Path(rvt_script_file).exists():
            settings["taskScriptFilePath"] = str(Path(rvt_script_file).resolve())
        
        # Write the updated settings back to the file
        with open(rvt_batch_setting_file, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)

    def run(self, verbose=True):
        """
        Runs BatchRvt.exe with the specified settings file.

        Parameters:
            verbose (bool): Whether to print output (default: True).
        """
        # Get the settings file path from the configuration

        
        command = [
            str(self.exe_path),
            "--settings_file",
            str(self.settings_file)
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