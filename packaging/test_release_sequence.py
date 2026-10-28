"""Regression checks against the workflow's actual release/PR conditions."""
from pathlib import Path
import re
import unittest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github/workflows/release-please.yml"


def step(name):
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^      - name: " + re.escape(name) + r"\n(.*?)(?=^      - |\Z)",
                      text, re.M | re.S)
    if not match:
        raise AssertionError(f"Missing workflow step: {name}")
    return match[1]


def enabled(name, outputs):
    lines = step(name).splitlines()
    index = next(i for i, line in enumerate(lines) if line.startswith("        if: "))
    expression = lines[index].split("if: ", 1)[1]
    if expression == ">-":
        parts = []
        for line in lines[index + 1:]:
            if not line.startswith("          "):
                break
            parts.append(line.strip())
        expression = " ".join(parts)
    expression = re.sub(r"steps\.(\w+)\.outputs\.(\w+)",
                        lambda m: repr(outputs.get((m[1], m[2]), "")), expression)
    # Evaluate only the equality/boolean subset used by these conditions.
    expression = expression.replace("&&", " and ").replace("||", " or ")
    return bool(eval(expression, {"__builtins__": {}}, {}))


class ReleaseSequenceTests(unittest.TestCase):
    def check_flow(self, ready, created, expected):
        outputs = {("pending", "ready"): ready, ("release", "release_created"): created}
        actual = tuple(enabled(name, outputs) for name in
                       ("Create the reviewed release", "Propose the next version", "Start the tagged installer build"))
        self.assertEqual(actual, expected)

    def test_new_release_does_not_also_open_next_version(self):
        self.check_flow("true", "true", (True, False, True))

    def test_no_merged_version_can_prepare_a_pr(self):
        self.check_flow("true", "false", (True, True, False))

    def test_pending_draft_blocks_both_actions(self):
        self.check_flow("false", "", (False, False, False))

    def test_release_and_pr_calls_are_separate(self):
        self.assertIn("skip-github-pull-request: true", step("Create the reviewed release"))
        self.assertIn("skip-github-release: true", step("Propose the next version"))


if __name__ == "__main__":
    unittest.main()
