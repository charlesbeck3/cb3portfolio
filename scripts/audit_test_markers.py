import ast
import os
from pathlib import Path


def audit_markers(test_dir):
    """Scan test files for pytest markers."""
    missing_markers = []
    total_files = 0

    # Valid markers
    valid_markers = {
        "unit",
        "integration",
        "e2e",
        "functional",
        "slow",
        "django_db",
        "models",
        "views",
        "services",
        "forms",
    }

    for root, _, files in os.walk(test_dir):
        for file in files:
            if not file.startswith("test_") or not file.endswith(".py"):
                continue

            total_files += 1
            file_path = Path(root) / file

            with open(file_path) as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError:
                    print(f"Syntax error in {file_path}")
                    continue

            has_file_marker = False
            # Check for pytestmark at module level
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "pytestmark":
                            has_file_marker = True

            if has_file_marker:
                continue

            # Check classes and functions
            file_has_markers = False
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and (
                    node.name.startswith("Test") or node.name.startswith("test_")
                ):
                    # Check decorators
                    has_marker = False
                    for decorator in node.decorator_list:
                        if isinstance(decorator, ast.Attribute) and decorator.attr in valid_markers:
                            has_marker = True
                        elif isinstance(decorator, ast.Call):
                            if (
                                isinstance(decorator.func, ast.Attribute)
                                and decorator.func.attr == "mark"
                            ):
                                has_marker = True  # imprecise but ok
                            if (
                                isinstance(decorator.func, ast.Attribute)
                                and decorator.func.attr in valid_markers
                            ):
                                has_marker = True
                            # handle @pytest.mark.foo
                            try:
                                if (
                                    decorator.func.value.attr == "mark"
                                    and decorator.func.attr in valid_markers
                                ):
                                    has_marker = True
                            except AttributeError:
                                pass

                        if has_marker:
                            file_has_markers = True
                            break  # Found at least one marked test entity, good enough for now

            if not file_has_markers:
                missing_markers.append(str(file_path))

    print(f"Scanned {total_files} test files.")
    print(f"Found {len(missing_markers)} files potentially missing standard markers.")
    for f in missing_markers:
        print(f"  - {f}")


if __name__ == "__main__":
    audit_markers("portfolio/tests")
