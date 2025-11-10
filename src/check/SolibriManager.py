"""
Solibri Manager Module
Manages all Solibri operations including:
- Registry settings for 3D viewer configuration
- Batch file execution and process monitoring
- Result cleanup and organization
"""

import os
import sys
import time
import ast
import psutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

try:
    import winreg
except ImportError:
    winreg = None  # type: ignore
    
# Add src directory to Python path for imports
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from common.paths import get_path

class SolibriRegistryManager:
    """
    Manages Solibri 3D viewer settings through Windows Registry.
    Handles backup, modification, and restoration of registry values.
    """
    
    REGISTRY_PATH = r"Software\JavaSoft\Prefs\com\solibri\saf\plugins\java3dplugin"
    
    def __init__(self):
        """
        Initialize registry manager.
        
        Args:
            backup_dir: Directory to store registry backups. Defaults to checks_with_solibri folder.
        """

        self.backup_dir = get_path('acc', 'root')
        self.backup_file = os.path.join(self.backup_dir, "backup_solibri_settings.reg") # type: ignore
        
        # Default settings template
        self.settings = {
            "back-clip-distance": None,
            "front-clip-distance": None,
            "field-of-view": None,
            "height-of-eyes": None
        }
    
    def _get_project_root(self) -> str:
        """Get project root directory. Override this if needed."""
        # This would normally call utils.get_project_root()
        # For now, return current working directory
        return os.getcwd()
    
    def check_registry_path(self) -> bool:
        """Check if the Solibri registry path exists."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH):
                return True
        except FileNotFoundError:
            return False
    
    def export_registry(self):
        """Export current registry settings to backup file."""
        os.makedirs(self.backup_dir, exist_ok=True) # type: ignore
        command = f'reg export "HKCU\\{self.REGISTRY_PATH}" "{self.backup_file}" /y'
        os.system(command)
    
    def read_registry_settings(self) -> Dict[str, str]:
        """
        Read current registry values for all settings.
        
        Returns:
            Dictionary of setting names to values
        """
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REGISTRY_PATH) as key:
                for setting in self.settings.keys():
                    try:
                        value, _ = winreg.QueryValueEx(key, setting)
                        self.settings[setting] = value
                    except FileNotFoundError:
                        self.settings[setting] = None
        except FileNotFoundError:
            print("Registry path not found!")
        
        return self.settings # type: ignore
    
    def modify_registry(self, new_settings: Dict[str, str]):
        """
        Modify multiple registry settings.
        
        Args:
            new_settings: Dictionary of setting names to new values
        """
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, 
                self.REGISTRY_PATH, 
                0, 
                winreg.KEY_SET_VALUE
            ) as key:
                for setting, new_value in new_settings.items():
                    if setting in self.settings:
                        winreg.SetValueEx(key, setting, 0, winreg.REG_SZ, str(new_value))
        except FileNotFoundError:
            print("Error: Registry path not found!")
    
    def restore_registry(self):
        """Restore registry settings from backup file."""
        if os.path.exists(self.backup_file):
            subprocess.run(["regedit", "/s", self.backup_file], check=True)
            print("Registry settings restored from backup.")
        else:
            print("No backup file found!")
    
    def update_solibri_3d_settings(self, new_values: Dict[str, str]):
        """
        Complete update workflow: backup, read, modify registry settings.
        
        Args:
            new_values: Dictionary of settings to update
        """
        if not self.check_registry_path():
            print("Registry path not found!")
            return
        
        self.export_registry()
        self.read_registry_settings()
        self.modify_registry(new_values)


class SolibriExecutor:
    """
    Handles Solibri batch execution and process monitoring.
    """
    
    def __init__(self):

        self.res_dir = get_path('acc', 'res')
    
    def cleanup_result_folders(self):
        """
        Delete previous result files before running Solibri.
        Cleans: .bcfzip, .json and .smc files
        """
        patterns = [
            (os.path.join(self.res_dir, "bcfzip"), ".bcfzip"), # type: ignore
            (os.path.join(self.res_dir, "issues"), ".json"), # type: ignore
            (os.path.join(self.res_dir, "smc"), ".smc"), # type: ignore
        ]
        
        for folder, ext in patterns:
            if not os.path.isdir(folder):
                continue
            
            for filename in os.listdir(folder):
                if filename.lower().endswith(ext):
                    try:
                        os.remove(os.path.join(folder, filename))
                    except Exception as e:
                        print(f"Warning: Could not delete {filename} in {folder}: {e}")
    
    def run_batch(self, batch_file: str) -> bool:
        """
        Execute Solibri batch file and monitor until completion.
        
        Args:
            batch_file: Absolute path to batch file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            batch_file = os.path.abspath(batch_file)
            
            if not os.path.exists(batch_file):
                print(f"Error: Batch file not found: {batch_file}")
                return False
            
            process = subprocess.Popen(batch_file, shell=True)
            self._monitor_process(process)
            
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error: Batch file failed with error code {e.returncode}")
            return False
        except Exception as e:
            print(f"Unexpected error executing batch file: {e}")
            return False
    
    def _monitor_process(self, process: subprocess.Popen):
        """
        Monitor a subprocess until it exits.
        
        Args:
            process: Subprocess to monitor
        """
        try:
            while process.poll() is None:
                time.sleep(5)
        except Exception as e:
            print(f"Error monitoring process: {e}")
    
    def wait_for_solibri_exit(self, process_name: str = "Solibri.exe"):
        """
        Wait until Solibri process completely exits.
        
        Args:
            process_name: Name of Solibri executable
        """
        print(f"\033[1m\033[92m [Solibri Execution] \033[0m running...")
        
        while any(proc.name().lower() == process_name.lower() 
                  for proc in psutil.process_iter()):
            time.sleep(1)


class SolibriManager:
    """
    High-level manager combining registry and execution control.
    """
    
    def __init__(self, settings: Optional[Dict[str, str]] = None):
        """
        Initialize Solibri manager.
        
        Args:
            project_root: Root directory of the project (defaults to paths.yaml root_dir)
            backup_dir: Directory for registry backups
            settings: Default Solibri 3D settings (from env or config)
        """
        self.project_root = str(get_path("root_dir"))
        self.registry_manager = SolibriRegistryManager() # type: ignore
        self.executor = SolibriExecutor() # type: ignore
        
        # Default settings
        self.settings = settings or self._load_default_settings()
    
    def _load_default_settings(self) -> Dict[str, str]:
        """
        Load default Solibri 3D settings from environment variables.
        
        Returns:
            Dictionary of setting names to values
        """
        return {
            "back-clip-distance": os.getenv("SOLIBRI_BACK_CLIP_DISTANCE", "100000.0"),
            "front-clip-distance": os.getenv("SOLIBRI_FRONT_CLIP_DISTANCE", "50000.0"),
            "height-of-eyes": os.getenv("SOLIBRI_HEIGHT_OF_EYES", "2500.0"),
            "field-of-view": os.getenv("SOLIBRI_FIELD_OF_VIEW", "35.0"),
        }
    
    def get_batch_path(self, relative_path: Optional[list] = None) -> str:
        """
        Get absolute path to Solibri Autorun batch file.
        
        Args:
            relative_path: List of path components from project root (optional, uses paths.yaml if None)
        
        Returns:
            Absolute path to batch file
        """
        if relative_path is None:
            # Use paths.yaml configuration: acc/setup/autorun.bat
            setup_dir = get_path('acc', 'setup')
            # Convert to Path if it's not already, then append autorun.bat
            if isinstance(setup_dir, Path):
                batch_path = setup_dir / "autorun.bat"
            else:
                batch_path = Path(str(setup_dir)) / "autorun.bat"
            return str(batch_path)
        
        # Fallback: use provided relative_path
        return os.path.join(self.project_root, *relative_path)
    
    def execute_check(
        self, 
        batch_path: Optional[str] = None,
        update_settings: bool = True
    ) -> bool:
        """
        Execute complete Solibri checking workflow.
        
        Args:
            batch_path: Path to batch file (auto-detected if None)
            update_settings: Whether to update registry settings before execution
        
        Returns:
            True if successful, False otherwise
        """
        # Cleanup old results
        self.executor.cleanup_result_folders()
        
        # Update Solibri 3D settings
        if update_settings:
            self.registry_manager.update_solibri_3d_settings(self.settings)
        
        # Get batch file path
        if batch_path is None:
            batch_path = self.get_batch_path()
        
        # Execute batch file
        success = self.executor.run_batch(batch_path)
        
        print(f"\033[1m\033[92m [Solibri Execution] \033[0m {'started' if success else 'failed'}")
        
        if success:
            # Wait for Solibri to complete
            self.executor.wait_for_solibri_exit()
            print(f"\033[1m\033[92m [Solibri Execution] \033[0m completed")
        
        return success
    
    def update_settings(self, new_settings: Dict[str, str]):
        """
        Update Solibri 3D settings.
        
        Args:
            new_settings: Dictionary of settings to update
        """
        self.settings.update(new_settings)
        self.registry_manager.update_solibri_3d_settings(self.settings)
    
    def restore_original_settings(self):
        """Restore original Solibri settings from backup."""
        self.registry_manager.restore_registry()


# Standalone function for backward compatibility
def run_solibri_check(
    batch_path: Optional[str] = None,
    settings: Optional[Dict[str, str]] = None
) -> bool:
    """
    Simplified function to run Solibri check.
    
    Args:
        project_root: Root directory of the project
        batch_path: Path to batch file
        settings: Solibri 3D settings
    
    Returns:
        True if successful, False otherwise
    """
    manager = SolibriManager(settings=settings)
    return manager.execute_check(batch_path)
