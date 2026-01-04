"""
Module for detecting build systems in Fortran projects.
"""

from pathlib import Path
from dataclasses import dataclass


@dataclass(frozen=True)
class BuildSystemInfo:
    """
    Information about detected build system.

    Attributes
    ----------
    build_type : str
        Type of build system ('cmake', 'fpm', or 'make')
    project_dir : Path
        Root directory of the project
    """
    build_type: str
    project_dir: Path


class BuildSystemDetector:
    """
    Detects build systems in Fortran projects.

    Searches for build system configuration files (fpm.toml, CMakeLists.txt, Makefile)
    starting from the test file directory and moving upwards.
    Priority order: FPM > CMake > Make
    """
    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize the build system detector.

        Parameters
        ----------
        verbose : bool, optional
            Enable verbose output, by default False
        """
        self._verbose: bool = verbose


    def detect(self, test_file: Path) -> BuildSystemInfo | None:
        """
        Detect if the project has a build system configuration.

        Priority order: FPM > CMake > Make
        (FPM is Fortran-specific and preferred when available)

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        BuildSystemInfo | None
            Build system information if detected, None otherwise
        """
        # Start from test file directory and search upwards
        current: Path = test_file.resolve().parent

        while current != current.parent:  # Stop at filesystem root
            # Check for fpm.toml (highest priority)
            if (current / "fpm.toml").exists():
                if self._verbose:
                    print(f"Detected FPM build system in {current}")
                return BuildSystemInfo("fpm", current)

            # Check for CMakeLists.txt
            if (current / "CMakeLists.txt").exists():
                if self._verbose:
                    print(f"Detected CMake build system in {current}")
                return BuildSystemInfo("cmake", current)

            # Check for Makefile
            if (current / "Makefile").exists():
                if self._verbose:
                    print(f"Detected Make build system in {current}")
                return BuildSystemInfo("make", current)

            current = current.parent

        if self._verbose:
            print("No build system detected")
        return None


    def find_cmake_executable(self, build_dir: Path, test_file: Path) -> Path | None:
        """
        Find test executable in CMake build directory.

        Parameters
        ----------
        build_dir : Path
            CMake build directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        test_stem: str = test_file.stem
        possible_names: list[str] = [
            test_stem,
            f"test_{test_stem.replace('test_', '')}",
            # fallback for examples
            "test_sample_module",
        ]

        for name in possible_names:
            executable: Path = build_dir / name
            if executable.exists():
                return executable

        if self._verbose:
            print(f"Warning: Could not find test executable in {build_dir}")
        return None


    def find_fpm_executable(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Find test executable in FPM build directory.

        Parameters
        ----------
        project_dir : Path
            FPM project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        build_dir: Path = project_dir / "build"
        test_stem: str = test_file.stem

        for test_dir in build_dir.glob("gfortran_*/test"):
            executable: Path = test_dir / test_stem
            if executable.exists():
                return executable

        if self._verbose:
            print(f"Warning: Could not find test executable in {build_dir}")
        return None


    def find_make_executable(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Find test executable in Make build directory.

        Parameters
        ----------
        project_dir : Path
            Make project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        test_stem: str = test_file.stem
        possible_paths: list[Path] = [
            project_dir / test_stem,
            project_dir / "build" / test_stem,
            project_dir / f"test_{test_stem.replace('test_', '')}",
        ]

        for executable in possible_paths:
            if executable.exists():
                return executable

        if self._verbose:
            print("Warning: Could not find test executable")
        return None