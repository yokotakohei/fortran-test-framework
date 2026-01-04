"""
Tests of fortest/build_system_detector.py
Tests are ordered according to method definitions in build_system_detector.py.
"""
from pathlib import Path

import pytest

from fortest.build_system_detector import BuildSystemDetector, BuildSystemInfo


@pytest.fixture
def detector() -> BuildSystemDetector:
    """
    Returns detector used in tests.
    """
    return BuildSystemDetector(verbose=False)


def write_file(path: Path, content: str) -> None:
    """
    Helper to write file with content.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def test_detect_fpm(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test detecting FPM build system.
    """
    test_file = tmp_path / "test" / "test_sample.f90"
    write_file(test_file, "program test\nend program")
    write_file(tmp_path / "fpm.toml", "[build]")
    
    result = detector.detect(test_file)
    
    assert result is not None
    assert result.build_type == "fpm"
    assert result.project_dir == tmp_path


def test_detect_cmake(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test detecting CMake build system.
    """
    test_file = tmp_path / "test" / "test_sample.f90"
    write_file(test_file, "program test\nend program")
    write_file(tmp_path / "CMakeLists.txt", "project(test)")
    
    result = detector.detect(test_file)
    
    assert result is not None
    assert result.build_type == "cmake"
    assert result.project_dir == tmp_path


def test_detect_make(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test detecting Make build system.
    """
    test_file = tmp_path / "test" / "test_sample.f90"
    write_file(test_file, "program test\nend program")
    write_file(tmp_path / "Makefile", "all:")
    
    result = detector.detect(test_file)
    
    assert result is not None
    assert result.build_type == "make"
    assert result.project_dir == tmp_path


def test_detect_priority_fpm_over_cmake(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test that FPM has priority over CMake.
    """
    test_file = tmp_path / "test" / "test_sample.f90"
    write_file(test_file, "program test\nend program")
    write_file(tmp_path / "fpm.toml", "[build]")
    write_file(tmp_path / "CMakeLists.txt", "project(test)")
    
    result = detector.detect(test_file)
    
    assert result is not None
    assert result.build_type == "fpm"


def test_detect_none(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test when no build system is detected.
    """
    test_file = tmp_path / "test_sample.f90"
    write_file(test_file, "program test\nend program")
    
    result = detector.detect(test_file)
    
    assert result is None


def test_find_cmake_executable(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test finding CMake executable.
    """
    test_file = tmp_path / "test_sample.f90"
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    executable = build_dir / "test_sample"
    executable.touch()
    
    result = detector.find_cmake_executable(build_dir, test_file)
    
    assert result == executable


def test_find_cmake_executable_with_alternative_name(
    detector: BuildSystemDetector, tmp_path: Path
) -> None:
    """
    Test finding CMake executable with alternative naming.
    """
    test_file = tmp_path / "test_sample.f90"
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    executable = build_dir / "test_sample"
    executable.touch()
    
    result = detector.find_cmake_executable(build_dir, test_file)
    
    assert result == executable


def test_find_cmake_executable_not_found(
    detector: BuildSystemDetector, tmp_path: Path
) -> None:
    """
    Test when CMake executable is not found.
    """
    test_file = tmp_path / "test_sample.f90"
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    
    result = detector.find_cmake_executable(build_dir, test_file)
    
    assert result is None


def test_find_fpm_executable(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test finding FPM executable.
    """
    test_file = tmp_path / "test_sample.f90"
    test_dir = tmp_path / "build" / "gfortran_ABC123" / "test"
    test_dir.mkdir(parents=True)
    executable = test_dir / "test_sample"
    executable.touch()
    
    result = detector.find_fpm_executable(tmp_path, test_file)
    
    assert result == executable


def test_find_fpm_executable_not_found(
    detector: BuildSystemDetector, tmp_path: Path
) -> None:
    """
    Test when FPM executable is not found.
    """
    test_file = tmp_path / "test_sample.f90"
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    
    result = detector.find_fpm_executable(tmp_path, test_file)
    
    assert result is None


def test_find_make_executable(detector: BuildSystemDetector, tmp_path: Path) -> None:
    """
    Test finding Make executable.
    """
    test_file = tmp_path / "test_sample.f90"
    executable = tmp_path / "test_sample"
    executable.touch()
    
    result = detector.find_make_executable(tmp_path, test_file)
    
    assert result == executable


def test_find_make_executable_in_build_dir(
    detector: BuildSystemDetector, tmp_path: Path
) -> None:
    """
    Test finding Make executable in build directory.
    """
    test_file = tmp_path / "test_sample.f90"
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    executable = build_dir / "test_sample"
    executable.touch()
    
    result = detector.find_make_executable(tmp_path, test_file)
    
    assert result == executable


def test_find_make_executable_not_found(
    detector: BuildSystemDetector, tmp_path: Path
) -> None:
    """
    Test when Make executable is not found.
    """
    test_file = tmp_path / "test_sample.f90"
    
    result = detector.find_make_executable(tmp_path, test_file)
    
    assert result is None