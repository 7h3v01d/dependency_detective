import ast
import argparse
import json
import logging
import os
import subprocess
import sys
import pathlib
import shutil
import tempfile
from pathlib import Path
from typing import Set, List, Dict

# --- Gracefully handle missing dependencies for the tool itself ---
try:
    import requests
    import tomli  # Add this import
    from rich.console import Console
    from rich_argparse import RichHelpFormatter
except ModuleNotFoundError:
    print("❌ Error: Missing dependencies required to run Dependency Detective.")
    print("   Please install them in your environment by running the following command:")
    # Add tomli to the install command
    print("\n      pip install requests rich rich-argparse tomli\n")
    sys.exit(1) 

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Folders to exclude from scanning
EXCLUDED_DIRS = {'.pytest_cache', '__pycache__', 'venv', '.venv', 'virtualenv', 'dist', 'build'}

# Package mappings for common aliases or top-level import names
PACKAGE_MAPPINGS = {
    # Data Science & Machine Learning
    'bs4': 'beautifulsoup4',
    'cv2': 'opencv-python',
    'dotenv': 'python-dotenv',
    'PIL': 'Pillow',
    'sklearn': 'scikit-learn',
    'yaml': 'PyYAML',
    'skimage': 'scikit-image',
    'mpl_toolkits': 'matplotlib',
    'google.cloud': 'google-cloud-storage', # Example for namespaced packages
    'google.auth': 'google-auth',
    'Crypto': 'pycryptodome',

    # Web Development & APIs
    'fastapi': 'fastapi',
    'starlette': 'starlette',
    'uvicorn': 'uvicorn',
    'jose': 'python-jose',
    'passlib': 'passlib',
    'jinja2': 'Jinja2',
    'werkzeug': 'Werkzeug',
    'jwt': 'PyJWT',

    # Utilities & Others
    'dateutil': 'python-dateutil',
    'faker': 'Faker',
    'lxml': 'lxml',
    'pydantic': 'pydantic',
    'serial': 'pyserial',
    'toml': 'toml',
    'win32api': 'pywin32', # For Windows
    'win32com': 'pywin32',
}

def find_project_root(start_path: Path) -> Path:
    """Find the project root by searching upwards for project markers like .git or pyproject.toml."""
    current_path = start_path.resolve()
    while current_path.parent != current_path:
        if (current_path / ".git").exists() or (current_path / "pyproject.toml").exists():
            logging.info(f"Identified project root: {current_path}")
            return current_path
        current_path = current_path.parent
    logging.warning("Could not identify a project root. Assuming current directory is the root.")
    return start_path.resolve()

def load_config_from_pyproject(project_root: Path) -> Dict:
    """Loads tool configuration from a pyproject.toml file if it exists."""
    config_file = project_root / "pyproject.toml"
    if not config_file.is_file():
        return {}  # Return empty config if no file found

    try:
        with open(config_file, "rb") as f:
            toml_data = tomli.load(f)
            # Look for our specific tool's configuration table
            return toml_data.get("tool", {}).get("depdetective", {})
    except tomli.TOMLDecodeError:
        logging.warning("Could not parse pyproject.toml due to a syntax error.")
        return {}

def load_blacklist() -> Set[str]:
    """Load non-pip-installable modules using the running Python interpreter's standard library."""
    if hasattr(sys, 'stdlib_module_names'):
        logging.debug("Loading standard library modules from sys.stdlib_module_names")
        return sys.stdlib_module_names
    else:
        logging.warning("Running on Python < 3.10. Cannot dynamically detect stdlib. Dependency list may be inaccurate.")
        return {"abc", "argparse", "array", "asyncio", "base64", "binascii", "bisect",
    "calendar", "cmath", "collections", "concurrent", "contextlib", "copy",
    "csv", "datetime", "decimal", "difflib", "dis", "enum", "errno",
    "faulthandler", "fractions", "functools", "gc", "getopt", "glob",
    "graphlib", "gzip", "hashlib", "heapq", "hmac", "html", "http", "imaplib",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "linecache", "locale", "logging", "lzma", "math", "mimetypes",
    "multiprocessing", "netrc", "numbers", "operator", "os", "pathlib",
    "pickle", "platform", "plistlib", "pprint", "profile", "pstats",
    "py_compile", "queue", "random", "re", "sched", "secrets", "selectors",
    "shlex", "shutil", "signal", "site", "smtplib", "socket", "sqlite3",
    "ssl", "stat", "statistics", "string", "struct", "subprocess", "sys",
    "sysconfig", "tabnanny", "tarfile", "tempfile", "textwrap", "threading",
    "time", "timeit", "tkinter", "token", "trace", "traceback", "types",
    "typing", "unicodedata", "unittest", "urllib", "uuid", "venv",
    "warnings", "wave", "weakref", "webbrowser", "xml", "zipfile",
    "zipimport", "zlib", "zoneinfo"}

def find_local_imports(project_root: Path) -> Set[str]:
    """
    Scans the project to find all local, importable modules and packages.
    - A directory is a package if it contains '__init__.py'.
    - A '.py' file is a module.
    """
    local_imports = set()
    scan_paths = [project_root]
    
    src_path = project_root / "src"
    if src_path.is_dir():
        scan_paths.append(src_path)

    for path in scan_paths:
        for item in path.iterdir():
            # Case 1: It's a package directory
            if item.is_dir() and (item / "__init__.py").exists():
                logging.info(f"Found local package: '{item.name}'")
                local_imports.add(item.name)
            # Case 2: It's an importable .py module
            elif item.is_file() and item.suffix == '.py':
                logging.info(f"Found local module: '{item.stem}'")
                local_imports.add(item.stem)
                
    return local_imports

def is_venv() -> bool:
    """Determine if running in a virtual environment."""
    return hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

def get_python_executable() -> str:
    """Get the appropriate Python executable."""
    return sys.executable

def get_installed_packages(python_exe: str) -> Dict[str, str]:
    """Get a dictionary of installed packages and their versions."""
    cmd = [python_exe, '-m', 'pip', 'list', '--format=json']
    try:
        output = subprocess.check_output(cmd, universal_newlines=True, stderr=subprocess.DEVNULL)
        packages = json.loads(output)
        return {pkg['name'].lower(): pkg['version'] for pkg in packages}
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        logging.error(f"Failed to get pip list: {e}")
        return {}

def get_latest_version(package_name: str) -> str | None:
    """Queries the PyPI API to find the latest version of a package."""
    try:
        url = f"https://pypi.org/pypi/{package_name}/json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        data = response.json()
        return data.get("info", {}).get("version")
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not fetch version for '{package_name}' from PyPI: {e}")
        return None

def extract_imports(file_path: Path) -> Set[str]:
    """Extract imported module names from a Python file using AST."""
    imports = set()
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            tree = ast.parse(f.read(), filename=str(file_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.add(name.name.split('.')[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    imports.add(node.module.split('.')[0])
    except SyntaxError as e:
        logging.warning(f"Skipping {file_path} due to a syntax error: {e}")
    except Exception as e:
        logging.error(f"Failed to parse {file_path} due to an unexpected error: {e}")
    return imports

def resolve_package(module: str, local_imports: Set[str], blacklist: Set[str], package_mappings: Dict[str, str]) -> str:
    """Resolve a module name to its package name, excluding blacklisted and local project modules."""
    if module in local_imports:
        logging.debug(f"Skipping local project module '{module}'.")
        return None
    if module in blacklist:
        logging.debug(f"Skipping standard library module '{module}'")
        return None
    return package_mappings.get(module, module)

def scan_directory(directory: Path, project_root: Path, blacklist: Set[str], local_imports: Set[str], script_name: str, excluded_dirs: Set[str], package_mappings: Dict[str, str]) -> Set[str]:
    """Scan directory for Python files and return required packages."""
    dependencies = set()
    for file_path in directory.rglob('*.py'):
        # --- NEW: Exclude the script itself from the scan ---
        if file_path.name == script_name:
            logging.info(f"Skipping self-analysis of '{script_name}'")
            continue

        if any(excluded in file_path.parts for excluded in excluded_dirs):
            continue
            
        logging.info(f"Analyzing {file_path}")
        imports = extract_imports(file_path)
        for module in imports:
            package = resolve_package(module, local_imports, blacklist, package_mappings)
            if package:
                dependencies.add(package)
    return dependencies

def install_dependencies(missing_deps: List[str], python_exe: str) -> List[str]:
    """
    Install missing dependencies one by one and return a list of any that failed.
    """
    failed_installs = []
    for dep in missing_deps:
        try:
            logging.info(f"Installing {dep}...")
            cmd = [python_exe, '-m', 'pip', 'install', dep]
            # Use DEVNULL to hide pip's output from our console for a cleaner look
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:
            logging.error(f"Failed to install '{dep}'.")
            failed_installs.append(dep)
            
    return failed_installs

def generate_requirements_file(dependencies: Set[str], installed_packages: Dict[str, str]):
    """Generate a requirements.txt file with pinned versions."""
    file_path = Path.cwd() / "requirements.txt"
    try:
        with open(file_path, "w") as f:
            sorted_deps = sorted(list(dependencies))
            for dep in sorted_deps:
                # First, check if the package is already installed
                version = installed_packages.get(dep.lower())
                
                # If not installed, fetch the latest version from PyPI
                if not version:
                    logging.info(f"'{dep}' not found in local environment, querying PyPI for latest version...")
                    version = get_latest_version(dep)

                # Write the dependency with the found version, or unpinned as a fallback
                if version:
                    f.write(f"{dep}=={version}\n")
                else:
                    logging.warning(f"Could not determine a version for '{dep}'. Adding it unpinned.")
                    f.write(f"{dep}\n")

        logging.info(f"Generated requirements.txt with {len(dependencies)} dependencies.")
        print(f"Generated requirements.txt file at: {file_path}")
    except IOError as e:
        logging.error(f"Failed to write requirements.txt: {e}")

def run_project(project_file: str, python_exe: str):
    """Run the main project file."""
    try:
        logging.info(f"Running project: {project_file}")
        subprocess.check_call([python_exe, project_file])
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to run project: {e}")
        sys.exit(1)

def run_in_temp_venv(required_deps: Set[str], project_file: str):
    """Create a temporary venv, install deps, run the project, and clean up."""
    with tempfile.TemporaryDirectory() as temp_dir:
        venv_path = Path(temp_dir) / "venv"
        logging.info(f"Creating temporary virtual environment at: {venv_path}")
        try:
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
            venv_python = venv_path / "Scripts" / "python.exe" if os.name == "nt" else venv_path / "bin" / "python"
            
            logging.info("Installing dependencies in temporary venv...")
            for dep in required_deps:
                subprocess.check_call([str(venv_python), "-m", "pip", "install", dep])
            
            logging.info(f"Running project {project_file} in temporary venv...")
            subprocess.check_call([str(venv_python), project_file])
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to run project in temporary venv: {e}")
            sys.exit(1)
        finally:
            logging.info("Temporary virtual environment is being deleted.")

def main():
    # --- UPGRADE: Use RichHelpFormatter for a beautiful, modern help menu ---
    # By simply changing the formatter_class, Rich takes over the help output.
    parser = argparse.ArgumentParser(
        description="📦 A tool to automatically manage Python project dependencies.",
        epilog="✨ Example: python testdep.py my_app.py --venv",
        formatter_class=RichHelpFormatter
    )

    parser.add_argument(
        "project_file",
        nargs='?',
        default="main.py",
        metavar="PROJECT_FILE",
        help="The main project file to run. Defaults to 'main.py'."
    )
    parser.add_argument(
        "--generate-requirements",
        action="store_true",
        help="Scan for dependencies, generate a requirements.txt file, and exit."
    )
    parser.add_argument(
        "--venv",
        action="store_true",
        help="Create a persistent './venv' and install all found dependencies into it."
    )
    parser.add_argument(
        "--temp-venv",
        action="store_true",
        help="Run the project in a temporary, isolated environment that is deleted after execution."
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically answer 'yes' to any installation prompts."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan for dependencies and show what would be installed, but do not make any changes."
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        metavar="DIR",
        help="Add a directory to the exclusion list. Can be used multiple times."
    )
    parser.add_argument(
        "--map",
        action="append",
        metavar="IMPORT:PACKAGE",
        help="Add a custom import-to-package mapping (e.g., --map SoCo:soco)."
    )    

    args = parser.parse_args()

    directory = Path.cwd()
    project_root = find_project_root(directory)

    # Load configuration from pyproject.toml 
    config = load_config_from_pyproject(project_root)

    # Apply configurations with precedence: defaults < config file < CLI args
    excluded_dirs = set(EXCLUDED_DIRS)
    if "exclude" in config:
        for d in config["exclude"]:
            excluded_dirs.add(d)
    if args.exclude_dir:
        for d in args.exclude_dir:
            excluded_dirs.add(d)

    # Start with the default package mappings
    package_mappings = dict(PACKAGE_MAPPINGS)
    if args.map:
        for m in args.map:
            if ':' not in m:
                console.print(f"[bold red]Error:[/bold red] Invalid map format '{m}'. Use 'IMPORT:PACKAGE'.")
                sys.exit(1)
            import_name, package_name = m.split(':', 1)
            package_mappings[import_name] = package_name
        logging.info(f"Custom package mappings added: {args.map}")

    # --- UPGRADE: Add a professional title banner ---
    console = Console()
    console.print("\n[bold green]📦 Dependency Detective[/bold green]", style="bold")
    console.print("-" * 40)

    # --- NEW: Get the name of the script itself to avoid self-analysis ---
    script_name = Path(sys.argv[0]).name

    project_file = directory / args.project_file
    
    blacklist = load_blacklist()
    python_exe = get_python_executable()

    # Scan for all local modules and packages
    local_imports = find_local_imports(project_root)
    
    logging.info(f"Using Python executable: {python_exe}")
    if is_venv():
        logging.info(f"Running in a virtual environment: {sys.prefix}")
    else:
        logging.info("Running in system environment. Consider using a virtual environment.")

    required_deps = scan_directory(directory, project_root, blacklist, local_imports, script_name, excluded_dirs, package_mappings)
    installed_deps = get_installed_packages(python_exe)

    if args.generate_requirements:
        generate_requirements_file(required_deps, installed_deps)
        sys.exit(0)

    if args.temp_venv:
        run_in_temp_venv(required_deps, str(project_file))
        sys.exit(0)

    if args.venv:
        venv_path = directory / 'venv'
        if venv_path.exists():
            console.print("[bold red]Error:[/bold red] A './venv' directory already exists. Please remove it first to create a new one.")
            sys.exit(1)
        
        try:
            console.print("[cyan]Creating a new virtual environment in './venv'...")
            subprocess.check_call([sys.executable, "-m", "venv", str(venv_path)])
            venv_python = venv_path / "Scripts" / "python.exe" if os.name == "nt" else venv_path / "bin" / "python"
            
            if required_deps:
                console.print("[cyan]Installing dependencies into new venv...")
                for dep in required_deps:
                    subprocess.check_call([str(venv_python), "-m", "pip", "install", dep])

            console.print("\n[bold green]✅ Virtual environment created and dependencies installed.[/bold green]")
            console.print("To activate it, run:")
            if os.name == 'nt':
                console.print(f"  [yellow].\\venv\\Scripts\\activate[/yellow]")
            else:
                console.print(f"  [yellow]source venv/bin/activate[/yellow]")
        except subprocess.CalledProcessError as e:
            console.print(f"[bold red]Error:[/bold red] Failed to create virtual environment or install dependencies: {e}")
            sys.exit(1)
        sys.exit(0)

    missing_deps = [dep for dep in required_deps if dep.lower() not in installed_deps]

    # --- NEW: Handle the --dry-run flag ---
    if args.dry_run:
        console.print("\n[bold cyan]-- Dry Run Mode --[/bold cyan]")
        console.print(f"Discovered dependencies: {', '.join(sorted(list(required_deps)))}")
        if missing_deps:
            console.print(f"Dependencies that would be installed: [yellow]{', '.join(missing_deps)}[/yellow]")
        else:
            console.print("[green]All dependencies are already satisfied. No action would be taken.[/green]")
        sys.exit(0) # Exit without taking any further action

    if missing_deps:
        console.print(f"\n[bold yellow]Warning:[/bold yellow] The following dependencies are missing: [cyan]{', '.join(missing_deps)}[/cyan]")
        response = 'n'
        if args.yes:
            console.print("[cyan]Proceeding with installation due to --yes flag.[/cyan]")
            response = 'y'
        else:
            response = input("Would you like to install them now? (y/n): ").strip().lower()

        if response == 'y':
            failed_packages = install_dependencies(missing_deps, python_exe)
            if not failed_packages:
                console.print("[bold green]✅ All missing dependencies installed successfully.[/bold green]")
            else:
                failed_list = ", ".join(failed_packages)
                console.print(f"[bold red]Error:[/bold red] Failed to install the following packages: [yellow]{failed_list}[/yellow]. Please check the log.")
                sys.exit(1)
        else:
            console.print("[yellow]Dependencies not installed. Exiting.[/yellow]")
            sys.exit(1)
    else:
        console.print("[bold green]✅ All dependencies are satisfied.[/bold green]")

    if not project_file.exists():
        console.print(f"[bold red]Error:[/bold red] Project file '{project_file}' does not exist.")
        sys.exit(1)
    
    run_project(str(project_file), python_exe)

if __name__ == '__main__':
    main()