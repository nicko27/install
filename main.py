import sys
import os
import glob

# Configure logging first
from ui.utils.logging import get_logger

logger = get_logger('main')

# Add package directory to Python path
pkg_dir = os.path.dirname(os.path.abspath(__file__))
for subdir in glob.glob(os.path.join(pkg_dir, '*')):
    if os.path.isdir(subdir) and (
        subdir.endswith('.dist-info') or
        os.path.exists(os.path.join(subdir, '__init__.py')) or
        subdir.endswith('.data')
    ):
        # Add the parent directory to the search path
        parent_dir = os.path.dirname(subdir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
            logger.debug(f"Added {parent_dir} to sys.path")

    # Also add the main package directory to the path
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)
        logger.debug(f"Added {pkg_dir} to sys.path")

from ui.app_manager import AppManager

if __name__ == "__main__":
    app_manager = AppManager()
    app_manager.run()
