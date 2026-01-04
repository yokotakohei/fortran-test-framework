# Makefile for fortest example with Make build system
# 
# This example demonstrates how fortest can work with Make-based projects.
# The fortest command will detect this Makefile and use it to build dependencies.
# Note: Unlike CMake, this Makefile only builds the libraries/modules.
# The fortest tool will generate and compile test executables automatically.

# Compiler
FC = gfortran
FFLAGS = -Wall -std=f2008 -J$(MOD_DIR)

# Directories
SRC_DIR = src
TEST_DIR = test
BUILD_DIR = build
MOD_DIR = $(BUILD_DIR)

# Source files
SRC_FILES = $(SRC_DIR)/module_sample.f90

# Object files
SRC_OBJS = $(BUILD_DIR)/module_sample.o

# fortest-assertions location
FORTEST_SRC = ../../fortran/src/module_fortest_assertions.f90
FORTEST_OBJ = $(BUILD_DIR)/module_fortest_assertions.o

# Library
LIB = $(BUILD_DIR)/libsample.a

.PHONY: all clean test

all: $(BUILD_DIR) $(LIB)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

# Build fortest assertions module
$(FORTEST_OBJ): $(FORTEST_SRC) | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@

# Build source module
$(SRC_OBJS): $(SRC_FILES) | $(BUILD_DIR)
	$(FC) $(FFLAGS) -c $< -o $@

# Create static library
$(LIB): $(SRC_OBJS) $(FORTEST_OBJ)
	ar rcs $@ $^

test: all
	@echo "Build complete. Run tests with: fortest $(TEST_DIR)/"

clean:
	rm -rf $(BUILD_DIR)

