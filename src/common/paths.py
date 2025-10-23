"""
Cross-platform path management utility.
Works seamlessly on Windows, macOS, and Linux.

Usage:
    from common.paths import get_path, pm
    
    # Get a specific path
    rkg_dir = get_path('data', 'processed', 'rkg')
    
    # Use the path
    output_file = rkg_dir / 'my_graph.json'
"""

import os
import platform
from pathlib import Path
import yaml


class PathManager:
    """
    Centralized path management for cross-platform compatibility.
    
    This class:
    - Automatically finds project root
    - Loads path configuration from YAML
    - Converts all paths to pathlib.Path objects
    - Handles Windows/Mac/Linux differences automatically
    - Creates directories as needed
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """Singleton pattern - only one PathManager instance."""
        if cls._instance is None:
            cls._instance = super(PathManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize path manager (only once)."""
        if not PathManager._initialized:
            self.platform = platform.system()  # 'Windows', 'Darwin', 'Linux'
            self.project_root = self._find_project_root()
            self.paths = self._load_paths()
            PathManager._initialized = True
    
    def _find_project_root(self):
        """
        Find project root by looking for pyproject.toml.
        Works from any subdirectory in the project.
        
        Returns:
            Path: Absolute path to project root
        """
        current = Path(__file__).resolve()
        
        # Walk up the directory tree
        for parent in [current] + list(current.parents):
            if (parent / 'pyproject.toml').exists():
                return parent
        
        # Fallback: assume project structure
        return Path(__file__).resolve().parent.parent.parent
    
    def _load_paths(self):
        """
        Load path configuration from config/paths.yaml.
        
        Returns:
            Dict: Nested dictionary of path configurations
            
        Raises:
            FileNotFoundError: If paths.yaml doesn't exist
        """
        config_path = self.project_root / 'config' / 'paths.yaml'
        
        if not config_path.exists():
            raise FileNotFoundError(
                f"Path configuration not found: {config_path}\n"
                f"Please create config/paths.yaml in your project root."
            )
        
        with open(config_path, 'r', encoding='utf-8') as f:
            paths_config = yaml.safe_load(f)
        
        return paths_config
    
    def get(self, *keys):
        """
        Get a path from the configuration.
        
        This method handles the OS-specific path conversion automatically.
        All paths are returned as pathlib.Path objects.
        
        Args:
            *keys: Nested keys to traverse the paths dictionary
                   e.g., get('data', 'processed', 'rkg')
        
        Returns:
            Path: Absolute path object (if string in config)
            Dict: Dictionary of paths (if dict in config)
        
        Examples:
            # Get a single path
            rkg_path = pm.get('data', 'processed', 'rkg')
            # Returns: WindowsPath('C:/Users/.../data/processed/graphs/rkg')
            #       or PosixPath('/Users/.../data/processed/graphs/rkg')
            
            # Get a dictionary of paths
            data_paths = pm.get('data', 'processed')
            # Returns: {'graphs': Path(...), 'rkg': Path(...), ...}
        """
        result = self.paths
        
        # Navigate through nested dictionary
        for key in keys:
            if key not in result:
                available_keys = ', '.join(result.keys())
                raise KeyError(
                    f"Path key '{key}' not found in configuration.\n"
                    f"Available keys at this level: {available_keys}"
                )
            result = result[key]
        
        # Convert to Path objects
        if isinstance(result, str):
            # Single path - convert to absolute Path
            return self.project_root / result
        elif isinstance(result, dict):
            # Dictionary of paths - convert all to absolute Paths
            return {
                k: self.project_root / v if isinstance(v, str) else v 
                for k, v in result.items()
            }
        else:
            # Fallback
            return self.project_root / str(result)
        
    def get_relative(self, absolute_path):
        """
        Convert absolute path to relative path from project root.
        
        Args:
            absolute_path: Absolute path to convert
        
        Returns:
            Path: Relative path from project root
        
        Example:
            abs_path = Path('C:/Users/me/project/data/file.txt')
            rel_path = pm.get_relative(abs_path)
            # Returns: Path('data/file.txt')
        """
        try:
            return absolute_path.relative_to(self.project_root)
        except ValueError:
            # Path is outside project root
            return absolute_path
    
    def is_windows(self):
        """Check if running on Windows."""
        return self.platform == 'Windows'
    
    def is_mac(self):
        """Check if running on macOS."""
        return self.platform == 'Darwin'
    
    def is_linux(self):
        """Check if running on Linux."""
        return self.platform == 'Linux'
    
    def get_temp_dir(self):
        """
        Get platform-appropriate temporary directory.
        
        Returns:
            Path: Absolute path to temp directory
        """
        temp_root = self.get('temp', 'root')
        temp_root.mkdir(parents=True, exist_ok=True)
        return temp_root
    
    def __repr__(self):
        """String representation for debugging."""
        return (
            f"PathManager(platform={self.platform}, "
            f"root={self.project_root})"
        )


# Global singleton instance
pm = PathManager()


# Convenience functions for easy importing
def get_path(*keys):
    """
    Shorthand for pm.get().
    
    Usage:
        from common.paths import get_path
        rkg_dir = get_path('data', 'processed', 'rkg')
    """
    return pm.get(*keys)


def get_project_root():
    """
    Get project root directory.
    
    Usage:
        from common.paths import get_project_root
        root = get_project_root()
    """
    return pm.project_root