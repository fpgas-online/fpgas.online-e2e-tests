"""The workflow passes its inputs to the shell as environment variables, never in the script text.

A dispatch input is free text (the board list, the seed). Interpolated into a
`run:` script as ${{ inputs.x }} it is shell syntax, so anyone who can dispatch
the workflow could run commands. Through `env:` it is data, and the script
quotes it.
"""

import re
from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "e2e.yml"
EXPRESSION = re.compile(r"\$\{\{.*?\}\}")


def _run_scripts():
    """Every line of every `run:` block, as (line number, text)."""
    lines = WORKFLOW.read_text().splitlines()
    found = []
    for i, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:- )?run:\s*(.*)$", line)
        if not match:
            continue
        indent, rest = len(match.group(1)), match.group(2)
        if rest and rest not in ("|", ">"):
            found.append((i + 1, rest))
            continue
        for j in range(i + 1, len(lines)):
            if lines[j].strip() and len(lines[j]) - len(lines[j].lstrip()) <= indent:
                break
            found.append((j + 1, lines[j]))
    return found


def test_no_run_script_has_a_github_expression_in_it():
    offenders = [(n, text.strip()) for n, text in _run_scripts() if EXPRESSION.search(text)]
    assert not offenders, f"expressions interpolated into shell scripts (pass them through env:): {offenders}"


def test_the_dispatch_inputs_reach_the_scripts_through_env():
    text = WORKFLOW.read_text()
    for variable, source in (
        ("BOARDS", "inputs.boards"),
        ("SEED", "inputs.seed"),
        ("DISRUPTIVE", "inputs.disruptive"),
        ("DISRUPTIVE", "inputs.audit_disruptive"),
    ):
        assert re.search(rf"^\s+{variable}: \$\{{\{{ {re.escape(source)} \}}\}}$", text, re.MULTILINE), source


def test_the_board_list_is_quoted_where_it_is_used():
    scripts = "\n".join(text for _, text in _run_scripts())
    assert '--boards "$BOARDS"' in scripts and '--seed "$SEED"' in scripts
