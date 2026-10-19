"""
Bayesian compiler optimization experiment.

Run from the project root or with:
    py bayesian/optimizer.py

Outputs:
    bayesian/optimization_results.csv
    bayesian/optimization_results.png  (if matplotlib is installed)
    bayesian/optimization_report.txt
    bayesian/optimization_comparison.csv

Search strategy:
- Evaluate four seed sequences, then four Bayesian-selected candidates (8 total by default).
- This is a budgeted search over 24 possible orders, not exhaustive evaluation.

Important:
- Correctness is checked only for the straight-line integer TAC supported below.
- Timing measures compiler invocation + optimization, not execution speed of generated machine code.
"""

import argparse
import csv
import random
import subprocess
import time
from pathlib import Path
from itertools import permutations
from math import erf, sqrt, pi, exp

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel, ConstantKernel

PROJECT_DIR = Path(__file__).resolve().parent.parent
COMPILER = PROJECT_DIR / "compiler.exe"
OUTPUT_DIR = Path(__file__).resolve().parent

# Keep test programs within the subset supported by this project's parser and TAC interpreter.
TEST_PROGRAMS = [
    {
        "name": "constant_folding",
        "source": """\
int a;
int b;
a = 10 + 20;
b = a * 2;
return b;
""",
    },
    {
        "name": "algebraic_simplification",
        "source": """\
int a;
int b;
int c;
a = 10;
b = a + 0;
c = b * 1;
return c;
""",
    },
    {
        "name": "repeated_expressions",
        "source": """\
int a;
int b;
int c;
int d;
a = 5 + 3;
b = 5 + 3;
c = a + b;
d = c + 0;
return d;
""",
    },
    {
        "name": "constant_propagation_chain",
        "source": """\
int a;
int b;
int c;
int d;
a = 4;
b = 6;
c = a + b;
d = c * 3;
return d;
""",
    },
    {
        "name": "dead_assignments",
        "source": """\
int a;
int b;
int c;
a = 100;
b = 200;
c = 7;
return c;
""",
    },
    {
        "name": "algebraic_identity_chain",
        "source": """\
int a;
int b;
int c;
int d;
a = 9;
b = a * 1;
c = b + 0;
d = c - 0;
return d;
""",
    },
    {
        "name": "mixed_arithmetic",
        "source": """\
int a;
int b;
int c;
a = 6 * 7;
b = a - 2;
c = b + 1;
return c;
""",
    },
    {
        "name": "integer_division",
        "source": """\
int a;
int b;
a = 24 / 3;
b = a + 2;
return b;
""",
    },
    {
        "name": "multiply_repeated_results",
        "source": """\
int a;
int b;
int c;
a = 2 + 3;
b = 2 + 3;
c = a * b;
return c;
""",
    },
    {
        "name": "multiplication_by_zero",
        "source": """\
int a;
int b;
int c;
a = 8;
b = 0;
c = a * b;
return c;
""",
    },
    {
        "name": "dynamic_repeated_sum",
        "source": """\
int x;
int y;
int a;
int b;
int c;
a = x + y;
b = x + y;
c = a + b;
return c;
""",
        "cases": [{"x": 2, "y": 3}, {"x": -4, "y": 7}, {"x": 0, "y": 0}],
    },
    {
        "name": "dynamic_algebraic_identities",
        "source": """\
int x;
int a;
int b;
int c;
a = x + 0;
b = a * 1;
c = b - 0;
return c;
""",
        "cases": [{"x": 11}, {"x": -8}, {"x": 0}],
    },
    {
        "name": "dynamic_mixed_expression",
        "source": """\
int x;
int y;
int a;
int b;
int c;
a = x * 3;
b = y - 2;
c = a + b;
return c;
""",
        "cases": [{"x": 4, "y": 9}, {"x": -2, "y": 1}, {"x": 0, "y": 0}],
    },
    {
        "name": "dynamic_dead_assignments",
        "source": """\
int x;
int unused;
int a;
int b;
unused = x * 99;
a = x + 4;
b = a * 2;
return b;
""",
        "cases": [{"x": 3}, {"x": -5}, {"x": 0}],
    },
    {
        "name": "dynamic_shared_subexpression",
        "source": """\
int x;
int y;
int a;
int b;
int c;
int d;
a = x * y;
b = x * y;
c = a + b;
d = c + x * y;
return d;
""",
        "cases": [{"x": 2, "y": 6}, {"x": -3, "y": 4}, {"x": 0, "y": 12}],
    },
    {
        "name": "dynamic_constant_propagation_boundary",
        "source": """\
int x;
int k;
int a;
int b;
k = 5;
a = x + k;
b = a + k;
return b;
""",
        "cases": [{"x": 1}, {"x": -10}, {"x": 0}],
    },
    {
        "name": "dynamic_zero_product",
        "source": """\
int x;
int a;
int b;
a = x * 0;
b = a + 7;
return b;
""",
        "cases": [{"x": 15}, {"x": -9}, {"x": 0}],
    },
    {
        "name": "dynamic_nested_reuse",
        "source": """\
int x;
int y;
int a;
int b;
int c;
int d;
a = x + y;
b = a * 2;
c = x + y;
d = b + c;
return d;
""",
        "cases": [{"x": 1, "y": 2}, {"x": 10, "y": -4}, {"x": -6, "y": -2}],
    },
]

PASSES = ["CF", "AS", "DCE", "CSE"]
CSV_PATH = OUTPUT_DIR / "optimization_results.csv"
CHART_PATH = OUTPUT_DIR / "optimization_results.png"
REPORT_PATH = OUTPUT_DIR / "optimization_report.txt"
COMPARISON_CSV_PATH = OUTPUT_DIR / "optimization_comparison.csv"
FIXED_SEQUENCE = ("CF", "AS", "DCE", "CSE")


def run_compiler(sequence, program):
    """Compile one program with the specified pass sequence."""
    result = subprocess.run(
        [str(COMPILER), *sequence],
        input=program,
        text=True,
        capture_output=True,
        cwd=PROJECT_DIR,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Compiler failed for {' -> '.join(sequence) or 'no passes'}:\n"
            f"{result.stderr}\n{result.stdout}"
        )
    return result.stdout


def extract_tac_section(output, section_marker):
    """Extract TAC instructions from a named compiler output section."""
    if section_marker not in output:
        raise ValueError(f"Compiler section '{section_marker}' was not found.")
    section_output = output.split(section_marker, 1)[1]
    tac_marker = "Three Address Code:"
    if tac_marker not in section_output:
        raise ValueError(f"TAC section was not found under '{section_marker}'.")
    tac_text = section_output.split(tac_marker, 1)[1]
    # Stop at the next section header, if one appears after the TAC.
    lines = []
    for line in tac_text.splitlines():
        stripped = line.strip()
        if stripped in {"Executing Optimization Passes:", "After Optimization:"}:
            break
        if stripped:
            lines.append(stripped)
    return lines


def extract_before_tac(output):
    """Extract the original TAC, before any optimization passes are applied."""
    return extract_tac_section(output, "Before Optimization:")


def extract_final_tac(output):
    """Extract final TAC instruction lines from compiler output."""
    return extract_tac_section(output, "After Optimization:")


def get_return_value(instructions, initial_values=None):
    """
    Interpret the straight-line integer TAC subset used by these tests.
    Return None if a result cannot be determined safely.
    """
    values = dict(initial_values or {})

    def resolve(token):
        token = token.strip()
        if token.lstrip("-").isdigit():
            return int(token)
        return values.get(token)

    for line in instructions:
        if line.startswith("return "):
            return resolve(line[len("return "):].strip())

        if " = " not in line:
            return None

        destination, expression = line.split(" = ", 1)
        destination = destination.strip()
        expression = expression.strip()
        parts = expression.split()

        if len(parts) == 1:
            value = resolve(expression)
            if value is None:
                return None
            values[destination] = value
            continue

        if len(parts) != 3:
            return None

        left, operator, right = parts
        a = resolve(left)
        b = resolve(right)
        if a is None or b is None:
            return None

        if operator == "+":
            value = a + b
        elif operator == "-":
            value = a - b
        elif operator == "*":
            value = a * b
        elif operator == "/":
            if b == 0:
                return None
            value = abs(a) // abs(b)
            if (a < 0) != (b < 0):
                value = -value
        else:
            return None

        if not -(2**31) <= value <= (2**31 - 1):
            return None
        values[destination] = value

    return None


def test_cases(test):
    """Return explicit input cases, defaulting to one empty input environment."""
    return test.get("cases", [{}])


def measure_baseline():
    """Measure original TAC and derive expected returns for every test input case."""
    expected_values = []
    baseline_counts = []
    for test in TEST_PROGRAMS:
        output = run_compiler([], test["source"])
        instructions = extract_before_tac(output)
        baseline_counts.append(len(instructions))
        case_values = []
        for case in test_cases(test):
            value = get_return_value(instructions, case)
            if value is None:
                raise RuntimeError(
                    f"Could not calculate baseline result for '{test['name']}' "
                    f"with inputs {case}. Check the compiler's TAC format."
                )
            case_values.append(value)
        expected_values.append(case_values)
    return expected_values, baseline_counts


def evaluate_sequence(sequence, expected_values, verbose=True):
    """Evaluate a pass order against every program and its input cases."""
    total_count = 0
    counts = []
    start = time.perf_counter()

    for index, test in enumerate(TEST_PROGRAMS):
        output = run_compiler(sequence, test["source"])
        instructions = extract_final_tac(output)
        count = len(instructions)
        counts.append(count)
        total_count += count

        for case_index, case in enumerate(test_cases(test)):
            actual = get_return_value(instructions, case)
            expected = expected_values[index][case_index]
            if verbose:
                print(
                    f"    {test['name']} (case {case_index + 1}): "
                    f"expected={expected}, actual={actual}; {count} TAC instructions"
                )
            if actual is None:
                raise ValueError(
                    f"Cannot verify '{test['name']}' with inputs {case} "
                    "using the supported TAC interpreter."
                )
            if actual != expected:
                raise ValueError(
                    f"Incorrect result for '{test['name']}' with inputs {case}: "
                    f"expected {expected}, got {actual}."
                )

    elapsed = time.perf_counter() - start
    return total_count, counts, elapsed


def sequence_features(sequence):
    """Encode each pass's position as numeric features."""
    return [
        sequence.index("CF"),
        sequence.index("AS"),
        sequence.index("DCE"),
        sequence.index("CSE"),
    ]


def expected_improvement(model, candidates, best_score):
    """Expected Improvement acquisition function for minimization."""
    features = np.array([sequence_features(s) for s in candidates], dtype=float)
    mean, std = model.predict(features, return_std=True)
    std = np.maximum(std, 1e-9)
    improvement = best_score - mean
    z = improvement / std
    cdf = np.array([0.5 * (1.0 + erf(v / sqrt(2.0))) for v in z])
    pdf = np.array([exp(-0.5 * v * v) / sqrt(2.0 * pi) for v in z])
    return improvement * cdf + std * pdf


def write_csv(scores, baseline_total):
    """Write one row per verified sequence."""
    with CSV_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([
            "sequence",
            "combined_tac_count",
            "baseline_tac_count",
            "tac_reduction_percent",
            "compiler_elapsed_seconds",
            "verified",
        ])
        for sequence, data in sorted(scores.items(), key=lambda item: item[1]["score"]):
            score = data["score"]
            reduction = (
                100.0 * (baseline_total - score) / baseline_total
                if baseline_total else 0.0
            )
            writer.writerow([
                " -> ".join(sequence),
                score,
                baseline_total,
                f"{reduction:.2f}",
                f"{data['elapsed']:.6f}",
                True,
            ])


def write_chart(scores):
    """Create a TAC-count comparison chart if matplotlib is available."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Chart skipped: matplotlib is not installed (CSV/report are still saved).")
        return False

    ordered = sorted(scores.items(), key=lambda item: item[1]["score"])
    labels = [" → ".join(sequence) for sequence, _ in ordered]
    values = [data["score"] for _, data in ordered]

    height = max(6, len(labels) * 0.32)
    fig, ax = plt.subplots(figsize=(12, height))
    positions = np.arange(len(labels))
    ax.barh(positions, values)
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("Combined TAC instruction count (lower is better)")
    ax.set_title("Bayesian Search: Optimization Pass Order vs TAC Count")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHART_PATH, dpi=160)
    plt.close(fig)
    return True


def write_comparison_csv(baseline_total, baseline_elapsed, fixed_data, best_sequence, best_data, search_elapsed):
    """Write a direct comparison of baseline, fixed order, and selected order."""
    rows = [
        ("No optimization (original TAC)", baseline_total, baseline_elapsed, "Reference baseline"),
        ("Fixed: " + " -> ".join(FIXED_SEQUENCE), fixed_data["score"], fixed_data["elapsed"], "Verified"),
        ("Bayesian-selected: " + " -> ".join(best_sequence), best_data["score"], best_data["elapsed"], "Verified"),
    ]
    with COMPARISON_CSV_PATH.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["strategy", "combined_tac_count", "reduction_vs_baseline_percent", "compiler_elapsed_seconds", "correctness_status", "total_search_elapsed_seconds"])
        for strategy, count, elapsed, status in rows:
            reduction = 100.0 * (baseline_total - count) / baseline_total if baseline_total else 0.0
            writer.writerow([strategy, count, f"{reduction:.2f}", f"{elapsed:.6f}", status, f"{search_elapsed:.6f}"])


def write_report(best_sequence, best_data, scores, baseline_total, attempted_count, baseline_elapsed, search_elapsed):
    reduction = (
        100.0 * (baseline_total - best_data["score"]) / baseline_total
        if baseline_total else 0.0
    )
    best_sequences = [
        " -> ".join(sequence)
        for sequence, data in scores.items()
        if data["score"] == best_data["score"]
    ]

    lines = [
        "AUTOMATIC COMPILER OPTIMIZATION — EXPERIMENT REPORT",
        "=" * 58,
        f"Test programs: {len(TEST_PROGRAMS)}",
        f"Input cases: {sum(len(test_cases(test)) for test in TEST_PROGRAMS)}",
        f"Available pass sequences: {len(list(permutations(PASSES)))}",
        f"Attempted sequences: {attempted_count}",
        f"Verified sequences: {len(scores)}",
        f"Baseline combined TAC count: {baseline_total}",
        f"Baseline measurement elapsed: {baseline_elapsed:.6f}s",
        f"Total search elapsed (including candidate compiler runs and model fitting): {search_elapsed:.6f}s",
        f"Best combined TAC count: {best_data['score']}",
        f"TAC count reduction: {reduction:.2f}%",
        f"One best sequence: {' -> '.join(best_sequence)}",
        "",
        "Strategy comparison:",
        f"  No optimization: {baseline_total} TAC instructions (0.00% reduction)",
        f"  Fixed CF -> AS -> DCE -> CSE: {scores.get(FIXED_SEQUENCE, {}).get('score', 'not verified')} TAC instructions",
        f"  Bayesian-selected {' -> '.join(best_sequence)}: {best_data['score']} TAC instructions ({reduction:.2f}% reduction)",
        f"  Search budget: {attempted_count} of {len(list(permutations(PASSES)))} orders attempted; this is budgeted Bayesian search, not exhaustive evaluation.",
        "",
        "All best-scoring sequences:",
    ]
    lines.extend(f"  {sequence}" for sequence in best_sequences)
    lines.extend([
        "",
        "Verified sequence scores (ascending):",
    ])
    for sequence, data in sorted(scores.items(), key=lambda item: item[1]["score"]):
        lines.append(f"  {' -> '.join(sequence)} : {data['score']} TAC instructions")
    lines.extend([
        "",
        "Method and limitations:",
        "- The objective is the combined number of final TAC instructions across the test suite.",
        "- Baseline TAC counts and expected return values come from the Before Optimization section.",
        "- Candidate TAC counts come from the After Optimization section for each requested pass order.",
        "- Timing is compiler invocation/optimization time, not generated-program execution time.",
        "- Dynamic tests use declared-but-unassigned integer variables as test inputs; expected results are derived from original TAC.",
        "- The search stops after a fixed budget; it may miss the globally best order.",
        "- The interpreter supports only simple straight-line integer TAC and +, -, *, /.",
        "- Matching these tests does not prove general compiler correctness.",
        "- Lower TAC count does not necessarily mean faster machine-code execution.",
    ])
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    if not COMPILER.exists():
        print(f"Compiler not found: {COMPILER}")
        print("Build compiler.exe before running this script.")
        return

    global CSV_PATH, CHART_PATH, REPORT_PATH, COMPARISON_CSV_PATH
    parser = argparse.ArgumentParser(description="Budgeted Bayesian compiler optimization")
    parser.add_argument("--seed", type=int, default=2026, help="reproducible random seed (default: 2026)")
    args = parser.parse_args()
    random_seed = args.seed

    # Keep each run's outputs so results from independent seeds can be compared.
    suffix = f"_seed_{random_seed}"
    CSV_PATH = OUTPUT_DIR / f"optimization_results{suffix}.csv"
    CHART_PATH = OUTPUT_DIR / f"optimization_results{suffix}.png"
    REPORT_PATH = OUTPUT_DIR / f"optimization_report{suffix}.txt"
    COMPARISON_CSV_PATH = OUTPUT_DIR / f"optimization_comparison{suffix}.csv"

    all_sequences = [list(sequence) for sequence in permutations(PASSES)]

    # Reproducible initial seeds. Exclude every previously known 72-TAC order
    # from initial seeds, while leaving them available for Bayesian selection.
    rng = random.Random(random_seed)
    known_optimal_sequences = {
        ("AS", "CSE", "CF", "DCE"),
        ("AS", "CF", "CSE", "DCE"),
    }

    seed_pool = [
        tuple(sequence)
        for sequence in all_sequences
        if tuple(sequence) != FIXED_SEQUENCE
        and tuple(sequence) not in known_optimal_sequences
    ]

    # Always measure the fixed pipeline for comparison, then select three
    # reproducible random orders that exclude all previously known optima.
    initial_sequences = [list(FIXED_SEQUENCE)]
    initial_sequences.extend(
        list(sequence) for sequence in rng.sample(seed_pool, 3)
    )

    print("Bayesian Compiler Optimization")
    print("=" * 60)
    print(f"Test programs: {len(TEST_PROGRAMS)}")
    print(f"Input cases: {sum(len(test_cases(test)) for test in TEST_PROGRAMS)}")
    print(f"Available pass sequences: {len(all_sequences)}")
    print("Objective: minimize TAC count while preserving test return values")
    print(f"Reproducible random seed: {random_seed}")
    print("Previously known 72-TAC sequences excluded from initial seeds:")
    for sequence in sorted(known_optimal_sequences):
        print("  " + " -> ".join(sequence))
    print("Initial seed orders:")
    for sequence in initial_sequences:
        print("  " + " -> ".join(sequence))
    if any(tuple(sequence) in known_optimal_sequences for sequence in initial_sequences):
        raise RuntimeError("A known optimal sequence unexpectedly appeared in the initial seeds.")

    baseline_start = time.perf_counter()
    try:
        expected_values, baseline_counts = measure_baseline()
        baseline_elapsed = time.perf_counter() - baseline_start
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"\nCould not establish baseline: {error}")
        return

    baseline_total = sum(baseline_counts)
    print(f"Baseline return values by program/input case: {expected_values}")
    print(f"Baseline TAC counts: {baseline_counts}")
    print(f"Baseline combined TAC count: {baseline_total}")

    search_start = time.perf_counter()

    # scores contains only verified sequences. attempted also tracks rejected sequences,
    # preventing a failing candidate from being retried indefinitely.
    scores = {}
    attempted = set()

    def test_and_record(sequence, label):
        key = tuple(sequence)
        if key in attempted:
            return False
        attempted.add(key)
        print(f"\n{label}: {' -> '.join(sequence)}")
        try:
            score, counts, elapsed = evaluate_sequence(sequence, expected_values)
            scores[key] = {
                "score": score,
                "counts": counts,
                "elapsed": elapsed,
            }
            reduction = (
                100.0 * (baseline_total - score) / baseline_total
                if baseline_total else 0.0
            )
            print(
                f"  VERIFIED: combined TAC={score}; "
                f"TAC reduction={reduction:.2f}%; "
                f"compiler elapsed={elapsed:.4f}s"
            )
            return True
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            print(f"  REJECTED: {error}")
            return False

    for sequence in initial_sequences:
        test_and_record(sequence, "Initial test")

    # Use the Bayesian model to choose additional candidates.
    # Four seeds + four model-selected candidates = eight evaluations by default.
    # Increase this budget to explore more of the 24 possible orders.
    budget = 4
    for step in range(budget):
        candidates = [
            sequence for sequence in all_sequences
            if tuple(sequence) not in attempted
        ]
        if not candidates:
            break

        if len(scores) < 2:
            # If too many candidates fail verification, keep exploring deterministically.
            chosen = candidates[0]
        else:
            training_x = np.array(
                [sequence_features(list(sequence)) for sequence in scores],
                dtype=float,
            )
            training_y = np.array(
                [data["score"] for data in scores.values()],
                dtype=float,
            )
            kernel = (
                ConstantKernel(1.0)
                * Matern(length_scale=1.0, nu=2.5)
                + WhiteKernel(noise_level=0.1)
            )
            model = GaussianProcessRegressor(
                kernel=kernel,
                normalize_y=True,
                n_restarts_optimizer=2,
                random_state=42,
            )
            try:
                model.fit(training_x, training_y)
                ei = expected_improvement(model, candidates, float(np.min(training_y)))
                chosen = candidates[int(np.argmax(ei))]
            except (ValueError, np.linalg.LinAlgError) as error:
                print(f"Bayesian model warning ({error}); choosing next untested sequence.")
                chosen = candidates[0]

        test_and_record(chosen, f"Bayesian trial {step + 1}")

    search_elapsed = time.perf_counter() - search_start

    if not scores:
        print("\nNo sequences passed correctness checks. Review compiler output and TAC format.")
        return

    best_sequence, best_data = min(scores.items(), key=lambda item: item[1]["score"])
    best_score = best_data["score"]
    reduction = (
        100.0 * (baseline_total - best_score) / baseline_total
        if baseline_total else 0.0
    )

    print("\n" + "=" * 60)
    print("BAYESIAN OPTIMIZATION RESULTS")
    print("=" * 60)
    print(f"Best verified sequence: {' -> '.join(best_sequence)}")
    print(f"Baseline combined TAC count: {baseline_total}")
    print(f"Best combined TAC count: {best_score}")
    print(f"TAC count reduction: {reduction:.2f}%")
    print(f"Attempted sequences: {len(attempted)} / {len(all_sequences)}")
    print(f"Verified sequences: {len(scores)}")
    print(f"Unattempted sequences: {len(all_sequences) - len(attempted)}")
    print("Search budget: 4 seed orders + up to 4 Bayesian-selected orders (8 total).")
    print(f"Baseline measurement time: {baseline_elapsed:.4f}s")
    print(f"Total search time (all candidate runs + model fitting): {search_elapsed:.4f}s")

    print("\nSTRATEGY COMPARISON")
    print("-" * 60)
    fixed_data = scores.get(FIXED_SEQUENCE)
    if fixed_data is None:
        print("Fixed sequence CF -> AS -> DCE -> CSE: not verified")
        fixed_data = {"score": baseline_total, "elapsed": 0.0}
    for label, count in [("No optimization", baseline_total), ("Fixed CF -> AS -> DCE -> CSE", fixed_data["score"]), ("Bayesian-selected", best_score)]:
        pct = 100.0 * (baseline_total - count) / baseline_total if baseline_total else 0.0
        print(f"{label:<38} TAC={count:<4} reduction={pct:6.2f}%")
    print(f"Budgeted search: attempted {len(attempted)} of {len(all_sequences)} possible orders.")
    print("A limited budget can reduce compiler runs, but it may miss the global optimum.")

    print("\nVerified results (lowest count first):")
    for sequence, data in sorted(scores.items(), key=lambda item: item[1]["score"]):
        print(f"{' -> '.join(sequence)} : {data['score']}")

    write_csv(scores, baseline_total)
    write_report(best_sequence, best_data, scores, baseline_total, len(attempted), baseline_elapsed, search_elapsed)
    write_comparison_csv(baseline_total, baseline_elapsed, fixed_data, best_sequence, best_data, search_elapsed)
    chart_created = write_chart(scores)

    print("\nSaved experiment outputs:")
    print(f"  CSV results: {CSV_PATH}")
    print(f"  Text report: {REPORT_PATH}")
    print(f"  Strategy comparison CSV: {COMPARISON_CSV_PATH}")
    if chart_created:
        print(f"  Chart: {CHART_PATH}")

    print(
        "\nLimitations: return-value checks cover only these test programs and the "
        "supported straight-line integer TAC subset. Compiler timing is not a "
        "measurement of optimized program runtime. More comprehensive tests are needed."
    )


if __name__ == "__main__":
    main()
