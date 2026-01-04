"""
Module for building and compiling Fortran projects and tests.
"""

import subprocess
from pathlib import Path

from fortest.build_system_detector import BuildSystemInfo, BuildSystemDetector
from fortest.module_dependency_resolver import ModuleDependencyResolver
from fortest.test_code_generator import TestCodeGenerator
from fortest.test_result import Colors


class ProjectBuilder:
    """
    Builds Fortran projects and compiles test files.

    Supports building with build systems (CMake, FPM, Make) and
    falls back to direct compilation with gfortran when needed.
    """

    def __init__(
        self,
        compiler: str = "gfortran",
        verbose: bool = False,
        detector: BuildSystemDetector | None = None,
        resolver: ModuleDependencyResolver | None = None,
        generator: TestCodeGenerator | None = None,
    ) -> None:
        """
        Initialize the project builder.

        Parameters
        ----------
        compiler : str, optional
            Fortran compiler command, by default "gfortran"
        verbose : bool, optional
            Enable verbose output, by default False
        detector : BuildSystemDetector | None, optional
            Build system detector instance, by default None (creates new one)
        resolver : ModuleDependencyResolver | None, optional
            Module dependency resolver instance, by default None (creates new one)
        generator : TestCodeGenerator | None, optional
            Test code generator instance, by default None (creates new one)
        """
        self.compiler: str = compiler
        self.verbose: bool = verbose
        self.detector: BuildSystemDetector = detector or BuildSystemDetector(verbose)
        self.resolver: ModuleDependencyResolver = resolver or ModuleDependencyResolver(verbose)
        self.generator: TestCodeGenerator = generator or TestCodeGenerator(verbose)

    def build_with_system(self, build_info: BuildSystemInfo, test_file: Path) -> Path | None:
        """
        Build the project using the detected build system.

        Parameters
        ----------
        build_info : BuildSystemInfo
            Build system information from detect_build_system
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        build_type: str = build_info.build_type
        project_dir: Path = build_info.project_dir

        if self.verbose:
            print(f"Building with {build_type} in {project_dir}")

        try:
            if build_type == "cmake":
                return self._build_with_cmake(project_dir, test_file)
            elif build_type == "fpm":
                return self._build_with_fpm(project_dir, test_file)
            elif build_type == "make":
                return self._build_with_make(project_dir, test_file)

        except subprocess.CalledProcessError as e:
            print(
                f"{Colors.RED.value}Build failed with {build_type}"
                f"{Colors.RESET.value}"
            )
            if self.verbose:
                print(e.stderr)
            return None
        except Exception as e:
            if self.verbose:
                print(f"Error during build: {e}")
            return None

        return None

    def compile_test(self, test_file: Path, output_dir: Path) -> Path | None:
        """
        Compile a Fortran test file with its dependencies.

        First tries to use a detected build system (CMake, FPM, Make),
        then falls back to direct compilation with gfortran.

        Parameters
        ----------
        test_file : Path
            Path to the test file to compile
        output_dir : Path
            Directory for output executable

        Returns
        -------
        Path | None
            Path to the compiled executable, or None if compilation failed
        """
        # Try to detect and use build system first
        build_info: BuildSystemInfo | None = self.detector.detect(test_file)
        if build_info is not None:
            executable_built: Path | None = self.build_with_system(build_info, test_file)
            if executable_built is not None:
                return executable_built

            # If build system detected but failed, fall back to direct compilation
            if self.verbose:
                print("Falling back to direct compilation with gfortran")

        # Check if this is a standalone program or module-based test
        if self._is_standalone_program(test_file):
            return self._compile_standalone_program(test_file, output_dir)
        else:
            return self._compile_module_test(test_file, output_dir)

    def _build_with_cmake(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Build the project using CMake.

        Parameters
        ----------
        project_dir : Path
            CMake project directory
        test_file : Path
            Path to the test file

        Returns
        -------
        Path | None
            Path to the test executable if found, None otherwise
        """
        build_dir: Path = project_dir / "build"
        build_dir.mkdir(exist_ok=True)

        # Run cmake configuration
        subprocess.run(
            ["cmake", ".."],
            cwd=build_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        # Build
        subprocess.run(
            ["make"],
            cwd=build_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        return self.detector.find_cmake_executable(build_dir, test_file)

    def _build_with_fpm(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Build the project using FPM (Fortran Package Manager).

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
        subprocess.run(
            ["fpm", "build"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        return self.detector.find_fpm_executable(project_dir, test_file)

    def _build_with_make(self, project_dir: Path, test_file: Path) -> Path | None:
        """
        Build the project using Make.

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
        subprocess.run(
            ["make"],
            cwd=project_dir,
            capture_output=True,
            text=True,
            check=True,
        )

        return self.detector.find_make_executable(project_dir, test_file)

    def _is_standalone_program(self, test_file: Path) -> bool:
        """
        Check if a test file is a standalone program (not a module).

        Parameters
        ----------
        test_file : Path
            Path to the test file

        Returns
        -------
        bool
            True if the file contains a program statement or is an error_stop test
        """
        import re
        with open(test_file, "r") as f:
            content: str = f.read()
        is_program = re.search(
            r"\bprogram\s+\w+",
            content,
            re.IGNORECASE,
        )
        return "error_stop" in test_file.name.lower() or is_program is not None

    def _compile_standalone_program(self, test_file: Path, output_dir: Path) -> Path | None:
        """
        Compile a standalone Fortran program.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        Path | None
            Path to the compiled executable, or None if compilation failed
        """
        executable: Path = output_dir / test_file.stem
        compile_cmd: list[str] = [
            self.compiler,
            "-J", str(output_dir),
            "-o",
            str(executable),
            str(test_file),
        ]

        if self.verbose:
            print(f"Compiling standalone program: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return executable
        except subprocess.CalledProcessError as e:
            print(
                f"{Colors.RED.value}Compilation failed for {test_file}"
                f"{Colors.RESET.value}"
            )
            print(e.stderr)
            return None

    def _compile_module_test(self, test_file: Path, output_dir: Path) -> Path | None:
        """
        Compile a module-based test file with its dependencies.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        output_dir : Path
            Directory for output executable

        Returns
        -------
        Path | None
            Path to the compiled executable, or None if compilation failed
        """
        # Extract test information
        test_module_name: str | None = self.resolver.extract_module_name(test_file)
        if not test_module_name:
            print(
                f"{Colors.YELLOW.value}Warning: Could not find module in "
                f"{test_file}{Colors.RESET.value}"
            )
            return None

        test_subroutines: list[str] = self.generator.extract_test_subroutines(test_file)
        if not test_subroutines:
            print(
                f"{Colors.YELLOW.value}Warning: No test subroutines found in "
                f"{test_file}{Colors.RESET.value}"
            )
            return None

        # Find module dependencies (including assertions for standalone mode)
        module_files: list[Path] = self.resolver.find_module_files(test_file, include_assertions=True)

        # Generate main program
        main_program: Path = self.generator.generate_test_program(
            test_file,
            test_module_name,
            test_subroutines,
            output_dir,
        )

        # Compile all files
        executable = output_dir / test_file.stem
        compile_cmd = [
            self.compiler,
            "-J", str(output_dir),
            "-o", str(executable),
        ]

        # Add all module files in dependency order
        compile_cmd.extend([str(f) for f in module_files])
        compile_cmd.append(str(test_file))
        compile_cmd.append(str(main_program))

        if self.verbose:
            print(f"Compiling: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return executable
        except subprocess.CalledProcessError as e:
            print(
                f"{Colors.RED.value}Compilation failed for {test_file}"
                f"{Colors.RESET.value}"
            )
            print(e.stderr)
            return None

    def compile_module_dependencies(
        self,
        module_files: list[Path],
        test_file: Path,
        output_dir: Path,
    ) -> tuple[list[Path], str | None]:
        """
        Compile module dependencies.

        Parameters
        ----------
        module_files : list[Path]
            List of module files to compile
        test_file : Path
            Path to the test file (for finding build directories)
        output_dir : Path
            Directory for output objects

        Returns
        -------
        tuple[list[Path], str | None]
            Tuple of (compiled_objects, error_message)
            Returns ([], None) on success, ([], error_msg) on failure
        """
        build_dirs = self.resolver.find_build_directories(test_file)
        compiled_objects: list[Path] = []

        for module_file in module_files:
            compile_result = self._compile_single_module(
                module_file,
                build_dirs,
                output_dir,
            )

            if compile_result is None:
                return [], f"Failed to compile dependency {module_file.name}"

            compiled_objects.append(compile_result)

        return compiled_objects, None

    def _compile_single_module(
        self,
        module_file: Path,
        build_dirs: list[Path],
        output_dir: Path,
    ) -> Path | None:
        """
        Compile a single module file.

        Parameters
        ----------
        module_file : Path
            Path to the module file
        build_dirs : list[Path]
            Build directories for module search path
        output_dir : Path
            Directory for output object

        Returns
        -------
        Path | None
            Path to compiled object file, or None on failure
        """
        compile_mod_cmd = [self.compiler, "-c", str(module_file)]

        for build_dir in build_dirs:
            compile_mod_cmd.extend(["-I", str(build_dir)])

        output_obj = output_dir / f"{module_file.stem}.o"
        compile_mod_cmd.extend([
            "-J", str(output_dir),
            "-o", str(output_obj),
        ])

        if self.verbose:
            print(f"Compiling module dependency: {' '.join(compile_mod_cmd)}")

        try:
            subprocess.run(
                compile_mod_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return output_obj

        except subprocess.CalledProcessError as e:
            print(f"{Colors.RED.value}Compilation error:{Colors.RESET.value}")
            print(f"  Module: {module_file.name}")
            if e.stderr:
                print(f"  Error details:")
                print(e.stderr)
            return None

    def compile_test_executable(
        self,
        test_file: Path,
        program_file: Path,
        executable_path: Path,
        compiled_objects: list[Path],
        output_dir: Path,
    ) -> str | None:
        """
        Compile test executable.

        Parameters
        ----------
        test_file : Path
            Path to the test file
        program_file : Path
            Path to the generated program file
        executable_path : Path
            Path for the output executable
        compiled_objects : list[Path]
            List of compiled object files
        output_dir : Path
            Directory for module files

        Returns
        -------
        str | None
            Error message if compilation failed, None on success
        """
        build_dirs = self.resolver.find_build_directories(test_file)
        compile_cmd = [self.compiler, "-o", str(executable_path)]

        for build_dir in build_dirs:
            compile_cmd.extend(["-I", str(build_dir)])

        compile_cmd.extend(["-I", str(output_dir), "-J", str(output_dir)])
        compile_cmd.extend([str(obj) for obj in compiled_objects])
        compile_cmd.append(str(test_file))
        compile_cmd.append(str(program_file))

        if self.verbose:
            print(f"Compiling test: {' '.join(compile_cmd)}")

        try:
            subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            return None

        except subprocess.CalledProcessError as e:
            if e.stderr:
                print(f"{Colors.RED.value}Compilation error:{Colors.RESET.value}")
                print(e.stderr)
            return f"Compilation failed: {e.stderr}"
