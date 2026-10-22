from pathlib import Path
import os
import shutil
import subprocess
from itertools import permutations

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Automatic Compiler Optimization",
    page_icon="⚙️",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "bayesian"
PASSES = ("CF", "AS", "DCE", "CSE")

st.title("⚙️ Automatic Compiler Pass Ordering Using Bayesian Optimization")
st.caption(
    "Enter a program once. All result sections, charts, tables, "
    "and downloads will use that program's results."
)

# ============================================================
# COMPILER HELPERS
# ============================================================

def get_compiler():
    """Use an existing compiler or build it from bundled C sources."""

    bundled_exe = ROOT / "compiler.exe"

    if os.name == "nt" and bundled_exe.exists():
        return str(bundled_exe)

    built = ROOT / "compiler"
    gcc = shutil.which("gcc")

    if not gcc:
        raise RuntimeError(
            "gcc is unavailable. On Streamlit Cloud, add "
            "build-essential to packages.txt and redeploy."
        )

    source_files = [
        ROOT / "parser.tab.c",
        ROOT / "lex.yy.c",
        ROOT / "ast" / "ast.c",
        ROOT / "ir" / "ir.c",
        ROOT / "optimizer" / "algebraic_simplification.c",
        ROOT / "optimizer" / "common_subexpression.c",
        ROOT / "optimizer" / "constant_folding.c",
        ROOT / "optimizer" / "dead_code_elimination.c",
        ROOT / "optimizer" / "pass_manager.c",
    ]

    missing = [
        str(p.relative_to(ROOT))
        for p in source_files
        if not p.exists()
    ]

    if missing:
        raise RuntimeError(
            "Missing compiler source files: " + ", ".join(missing)
        )

    newest_source = max(p.stat().st_mtime for p in source_files)

    if not built.exists() or built.stat().st_mtime < newest_source:
        result = subprocess.run(
            [
                gcc,
                "-D_POSIX_C_SOURCE=200809L",
                "-O2",
                "-o",
                str(built),
                *[str(p) for p in source_files],
            ],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )

        if result.returncode:
            raise RuntimeError(
                "Compiler build failed:\n" + result.stderr[-5000:]
            )

    return str(built)


def extract_tac(output, marker):
    """Extract TAC instructions from compiler output."""

    if marker not in output:
        raise RuntimeError(
            f"Could not find '{marker}' in compiler output. "
            "Check the compiler's output headings.\n\n"
            + output[-3000:]
        )

    part = output.split(marker, 1)[1]

    if "Three Address Code:" in part:
        part = part.split("Three Address Code:", 1)[1]

    lines = []

    stop_markers = (
        "Executing Optimization Passes:",
        "After Optimization:",
        "Optimization Complete:",
    )

    for line in part.splitlines():
        line = line.strip()

        if any(text in line for text in stop_markers):
            break

        if line and not line.startswith("Enter program:"):
            lines.append(line)

    return lines


def evaluate_sequence(compiler, source_code, order):
    """Compile the current input using a particular pass sequence."""

    label = " -> ".join(order)

    result = subprocess.run(
        [compiler, *order],
        input=source_code,
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(ROOT),
    )

    output = result.stdout or ""

    if result.returncode != 0:
        return {
            "Sequence": label,
            "Optimized TAC instructions": None,
            "Status": "Failed",
            "Error": (
                result.stderr + "\n" + output
            ).strip()[-2500:],
            "Original TAC": [],
            "Optimized TAC": [],
        }

    try:
        original = extract_tac(
            output,
            "Before Optimization:",
        )

        optimized = extract_tac(
            output,
            "After Optimization:",
        )

    except RuntimeError as exc:
        return {
            "Sequence": label,
            "Optimized TAC instructions": None,
            "Status": "Failed",
            "Error": str(exc)[-2500:],
            "Original TAC": [],
            "Optimized TAC": [],
        }

    return {
        "Sequence": label,
        "Optimized TAC instructions": len(optimized),
        "Status": "Success",
        "Error": "",
        "Original TAC": original,
        "Optimized TAC": optimized,
    }


# ============================================================
# ANALYSIS: EXHAUSTIVE SEARCH + BAYESIAN OPTIMIZATION
# ============================================================

def run_analysis(source_code, bo_trials, random_seed):
    """Run both search methods on the program supplied by the user."""

    from skopt import Optimizer
    from skopt.space import Categorical

    compiler = get_compiler()

    candidates = [
        order
        for length in range(1, len(PASSES) + 1)
        for order in permutations(PASSES, length)
    ]

    labels = [" -> ".join(order) for order in candidates]

    # --------------------------------------------------------
    # 1. EXHAUSTIVE SEARCH
    # --------------------------------------------------------

    exhaustive_rows = []
    exhaustive_cache = {}

    progress = st.progress(
        0,
        text="Exhaustive search: starting...",
    )

    for i, order in enumerate(candidates, start=1):
        row = evaluate_sequence(
            compiler,
            source_code,
            order,
        )

        exhaustive_cache[row["Sequence"]] = row

        exhaustive_rows.append({
            "Sequence": row["Sequence"],
            "Optimized TAC instructions": (
                row["Optimized TAC instructions"]
            ),
            "Status": row["Status"],
        })

        progress.progress(
            i / len(candidates),
            text=f"Exhaustive search: {i}/{len(candidates)}",
        )

    progress.empty()

    # --------------------------------------------------------
    # 2. BAYESIAN OPTIMIZATION
    # --------------------------------------------------------

    bayesian_cache = {}

    optimizer = Optimizer(
        dimensions=[
            Categorical(
                labels,
                name="pass_sequence",
            )
        ],
        base_estimator="RF",
        acq_func="EI",
        random_state=int(random_seed),
        n_initial_points=min(8, int(bo_trials)),
    )

    bayesian_rows = []

    progress = st.progress(
        0,
        text="Bayesian optimization: starting...",
    )

    for trial in range(1, int(bo_trials) + 1):
        suggestion = optimizer.ask()

        label = suggestion[0]
        order = tuple(label.split(" -> "))

        repeated = label in bayesian_cache

        if repeated:
            row = bayesian_cache[label]
        else:
            row = evaluate_sequence(
                compiler,
                source_code,
                order,
            )

            bayesian_cache[label] = row

        score = row["Optimized TAC instructions"]

        optimizer.tell(
            suggestion,
            float(score) if score is not None else 1_000_000.0,
        )

        bayesian_rows.append({
            "Trial": trial,
            "Sequence": label,
            "Optimized TAC instructions": score,
            "Status": row["Status"],
            "Evaluation": (
                "Repeated suggestion (cached)"
                if repeated
                else "New compiler evaluation"
            ),
        })

        progress.progress(
            trial / int(bo_trials),
            text=f"Bayesian optimization: {trial}/{bo_trials}",
        )

    progress.empty()

    # --------------------------------------------------------
    # 3. PREPARE RESULTS
    # --------------------------------------------------------

    ex_df = pd.DataFrame(exhaustive_rows)
    bo_df = pd.DataFrame(bayesian_rows)

    ex_df["Optimized TAC instructions"] = pd.to_numeric(
        ex_df["Optimized TAC instructions"],
        errors="coerce",
    )

    bo_df["Optimized TAC instructions"] = pd.to_numeric(
        bo_df["Optimized TAC instructions"],
        errors="coerce",
    )

    ex_ok = ex_df.dropna(
        subset=["Optimized TAC instructions"]
    )

    bo_ok = bo_df.dropna(
        subset=["Optimized TAC instructions"]
    )

    ex_best_label = None
    ex_best_count = None
    bo_best_label = None
    bo_best_count = None

    if not ex_ok.empty:
        best_index = ex_ok[
            "Optimized TAC instructions"
        ].idxmin()

        ex_best_label = str(
            ex_df.loc[best_index, "Sequence"]
        )

        ex_best_count = int(
            ex_df.loc[
                best_index,
                "Optimized TAC instructions",
            ]
        )

    if not bo_ok.empty:
        best_index = bo_ok[
            "Optimized TAC instructions"
        ].idxmin()

        bo_best_label = str(
            bo_df.loc[best_index, "Sequence"]
        )

        bo_best_count = int(
            bo_df.loc[
                best_index,
                "Optimized TAC instructions",
            ]
        )

    return {
        "source_code": source_code,
        "bo_trials": int(bo_trials),
        "random_seed": int(random_seed),
        "exhaustive_df": ex_df,
        "bayesian_df": bo_df,
        "exhaustive_cache": exhaustive_cache,
        "bayesian_cache": bayesian_cache,
        "ex_best_label": ex_best_label,
        "ex_best_count": ex_best_count,
        "bo_best_label": bo_best_label,
        "bo_best_count": bo_best_count,
        "candidate_count": len(candidates),
    }


# ============================================================
# SHARED INPUT
# ============================================================

default_source = """int a;
int b;
int c;
a = 10 + 20;
b = a * 2;
c = b + 0;
return c;
"""

with st.sidebar:
    st.header("Your program")

    source_code = st.text_area(
        "C-like source input",
        value=st.session_state.get(
            "source_code",
            default_source,
        ),
        height=240,
        help=(
            "Enter code supported by your compiler. "
            "Example: int x; x = 2 + 3; return x;"
        ),
    )

    bo_trials = st.slider(
        "Bayesian evaluation budget",
        min_value=8,
        max_value=40,
        value=int(
            st.session_state.get("bo_trials", 16)
        ),
        step=4,
    )

    random_seed = st.number_input(
        "Bayesian random seed",
        min_value=1,
        max_value=999999,
        value=int(
            st.session_state.get("random_seed", 2026)
        ),
        step=1,
    )

    run_button = st.button(
        "Analyze this input",
        type="primary",
        use_container_width=True,
    )

    st.caption(
        "After changing your input or settings, click "
        "'Analyze this input' to update every section."
    )

st.session_state["source_code"] = source_code
st.session_state["bo_trials"] = bo_trials
st.session_state["random_seed"] = random_seed

if run_button:
    if not source_code.strip():
        st.error("Enter a program before running the analysis.")
    else:
        try:
            with st.spinner(
                "Compiling your program and comparing search strategies..."
            ):
                st.session_state["analysis_result"] = run_analysis(
                    source_code,
                    bo_trials,
                    random_seed,
                )

            st.success(
                "Analysis completed. All result pages now reflect this input."
            )

        except ImportError:
            st.error(
                "The Bayesian optimization package is missing. "
                "Add scikit-optimize to requirements.txt and redeploy."
            )

        except (
            RuntimeError,
            subprocess.TimeoutExpired,
            OSError,
            ValueError,
        ) as exc:
            st.error(str(exc))

# ============================================================
# CURRENT RESULT VALIDATION
# ============================================================

result = st.session_state.get("analysis_result")

result_matches_input = (
    result is not None
    and result["source_code"] == source_code
    and result["bo_trials"] == bo_trials
    and result["random_seed"] == random_seed
)

if result is not None and not result_matches_input:
    st.warning(
        "Your input or settings have changed. Click "
        "'Analyze this input' to refresh the results."
    )

# ============================================================
# NAVIGATION
# ============================================================

page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Try Your Code",
        "Exhaustive Search",
        "Bayesian Optimization",
        "Reports & Downloads",
        "ML / RL Comparison",
    ],
)
# ============================================================
# TRY YOUR CODE
# ============================================================

if page == "Try Your Code":
    st.header("Try Your Code")

    st.write(
        "This is the exact source currently selected in the sidebar."
    )

    st.code(source_code, language="c")

    st.info(
        "Click 'Analyze this input' in the sidebar. "
        "All results, charts and reports will use this program."
    )

    st.subheader("Available optimization passes")

    st.dataframe(
        pd.DataFrame([
            {
                "Pass": "CF",
                "Meaning": "Constant Folding",
            },
            {
                "Pass": "AS",
                "Meaning": "Algebraic Simplification",
            },
            {
                "Pass": "DCE",
                "Meaning": "Dead Code Elimination",
            },
            {
                "Pass": "CSE",
                "Meaning": "Common Subexpression Elimination",
            },
        ]),
        use_container_width=True,
        hide_index=True,
    )

# ============================================================
# OVERVIEW
# ============================================================

if page == "Overview":
    st.header("Project Overview")

    st.write(
        "Compare exhaustive pass-order search against "
        "Bayesian-guided candidate selection for your current program."
    )

    st.subheader("Current program")
    st.code(source_code, language="c")

    if not result_matches_input:
        st.info(
            "Click 'Analyze this input' to calculate metrics "
            "for the current program."
        )

    else:
        c1, c2, c3, c4 = st.columns(4)

        c1.metric(
            "Exhaustive candidates",
            result["candidate_count"],
        )

        c2.metric(
            "Exhaustive best TAC",
            (
                result["ex_best_count"]
                if result["ex_best_count"] is not None
                else "N/A"
            ),
        )

        c3.metric(
            "Bayesian trials",
            result["bo_trials"],
        )

        c4.metric(
            "Bayesian best TAC",
            (
                result["bo_best_count"]
                if result["bo_best_count"] is not None
                else "N/A"
            ),
        )

        if (
            result["ex_best_count"] is not None
            and result["bo_best_count"] is not None
        ):
            if (
                result["bo_best_count"]
                == result["ex_best_count"]
            ):
                st.success(
                    "Bayesian optimization matched the exhaustive "
                    "best TAC count for this input."
                )
            else:
                st.info(
                    "Bayesian optimization did not find the exhaustive "
                    "best count within this trial budget. It does not "
                    "guarantee the global optimum."
                )

        summary = pd.DataFrame([
            {
                "Method": "Exhaustive Search",
                "Candidates / trials": result["candidate_count"],
                "Best sequence": (
                    result["ex_best_label"]
                    or "No successful candidate"
                ),
                "Best TAC count": result["ex_best_count"],
            },
            {
                "Method": "Bayesian Optimization",
                "Candidates / trials": result["bo_trials"],
                "Best sequence": (
                    result["bo_best_label"]
                    or "No successful trial"
                ),
                "Best TAC count": result["bo_best_count"],
            },
        ])

        st.subheader("Live comparison for this input")

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True,
        )

        chart_data = summary.dropna(
            subset=["Best TAC count"]
        )

        if not chart_data.empty:
            st.plotly_chart(
                px.bar(
                    chart_data,
                    x="Method",
                    y="Best TAC count",
                    color="Method",
                    title=(
                        "Best TAC instruction count "
                        "for the current program"
                    ),
                ),
                use_container_width=True,
            )

        st.caption(
            "TAC instruction count is a proxy metric. "
            "It is not a direct measurement of execution time."
        )

# ============================================================
# EXHAUSTIVE SEARCH
# ============================================================

if page == "Exhaustive Search":
    st.header("Exhaustive Search")

    st.write(
        "Every non-empty ordered subset of CF, AS, DCE and CSE "
        "is tested on the current input."
    )

    if not result_matches_input:
        st.info(
            "Run 'Analyze this input' to populate this page."
        )

    else:
        df = result["exhaustive_df"].copy()

        df["Optimized TAC instructions"] = pd.to_numeric(
            df["Optimized TAC instructions"],
            errors="coerce",
        )

        ok = df.dropna(
            subset=["Optimized TAC instructions"]
        )

        c1, c2, c3 = st.columns(3)

        c1.metric("Candidates tested", len(df))
        c2.metric("Successful", len(ok))
        c3.metric("Failed", len(df) - len(ok))

        if result["ex_best_label"]:
            best = result["exhaustive_cache"][
                result["ex_best_label"]
            ]

            st.subheader("Best sequence for this input")
            st.code(result["ex_best_label"])

            st.metric(
                "Optimized TAC instructions",
                result["ex_best_count"],
            )

            left, right = st.columns(2)

            with left:
                st.markdown("**Original TAC**")
                st.code(
                    "\n".join(best["Original TAC"])
                    or "(no instructions)"
                )

            with right:
                st.markdown("**Optimized TAC**")
                st.code(
                    "\n".join(best["Optimized TAC"])
                    or "(no instructions)"
                )

        st.subheader("All candidate results")

        st.dataframe(
            df.sort_values(
                "Optimized TAC instructions",
                na_position="last",
            ),
            use_container_width=True,
            hide_index=True,
        )

        if not ok.empty:
            st.plotly_chart(
                px.bar(
                    ok,
                    x="Sequence",
                    y="Optimized TAC instructions",
                    title=(
                        "Exhaustive search: TAC count "
                        "by pass sequence"
                    ),
                ),
                use_container_width=True,
            )

        failures = [
            row
            for row in result["exhaustive_cache"].values()
            if row["Status"] != "Success"
        ]

        if failures:
            with st.expander("Show a sample compiler failure"):
                st.code(
                    failures[0]["Error"]
                    or "No compiler error text was returned."
                )

# ============================================================
# BAYESIAN OPTIMIZATION
# ============================================================

if page == "Bayesian Optimization":
    st.header("Bayesian Optimization")

    st.write(
        "Bayesian optimization uses a random-forest surrogate model "
        "and Expected Improvement (EI) to suggest pass sequences "
        "using the results from its own trials."
    )

    if not result_matches_input:
        st.info(
            "Run 'Analyze this input' to populate Bayesian results."
        )

    else:
        df = result["bayesian_df"].copy()

        df["Optimized TAC instructions"] = pd.to_numeric(
            df["Optimized TAC instructions"],
            errors="coerce",
        )

        valid = df.dropna(
            subset=["Optimized TAC instructions"]
        )

        c1, c2, c3 = st.columns(3)

        c1.metric(
            "Trial budget",
            result["bo_trials"],
        )

        c2.metric(
            "Unique sequences evaluated",
            len(result["bayesian_cache"]),
        )

        c3.metric(
            "Best TAC",
            (
                result["bo_best_count"]
                if result["bo_best_count"] is not None
                else "N/A"
            ),
        )

        if result["bo_best_label"]:
            best = result["bayesian_cache"][
                result["bo_best_label"]
            ]

            st.subheader(
                "Best sequence found by Bayesian optimization"
            )

            st.code(result["bo_best_label"])

            st.metric(
                "Optimized TAC instructions",
                result["bo_best_count"],
            )

            left, right = st.columns(2)

            with left:
                st.markdown("**Original TAC**")
                st.code(
                    "\n".join(best["Original TAC"])
                    or "(no instructions)"
                )

            with right:
                st.markdown("**Optimized TAC**")
                st.code(
                    "\n".join(best["Optimized TAC"])
                    or "(no instructions)"
                )

        st.subheader("Bayesian trial history")

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

        if not valid.empty:
            st.plotly_chart(
                px.line(
                    valid,
                    x="Trial",
                    y="Optimized TAC instructions",
                    markers=True,
                    title=(
                        "Bayesian optimization: "
                        "TAC count by trial"
                    ),
                ),
                use_container_width=True,
            )

        st.caption(
            "Repeated suggestions use cached results and are "
            "not counted as new compiler evaluations."
        )

# ============================================================
# REPORTS AND DOWNLOADS
# ============================================================

if page == "Reports & Downloads":
    st.header("Reports & Downloads")

    if not result_matches_input:
        st.info(
            "Run 'Analyze this input' first. Reports will then "
            "be generated from the current program and settings."
        )

    else:
        ex_df = result["exhaustive_df"]
        bo_df = result["bayesian_df"]

        summary = pd.DataFrame([
            {
                "Method": "Exhaustive Search",
                "Candidates / trials": result["candidate_count"],
                "Best sequence": result["ex_best_label"],
                "Best TAC count": result["ex_best_count"],
            },
            {
                "Method": "Bayesian Optimization",
                "Candidates / trials": result["bo_trials"],
                "Best sequence": result["bo_best_label"],
                "Best TAC count": result["bo_best_count"],
            },
        ])

        report = (
            "INPUT PROGRAM\n"
            + result["source_code"]
            + "\n\nSETTINGS\n"
            + f"Bayesian trial budget: {result['bo_trials']}\n"
            + f"Random seed: {result['random_seed']}\n"
            + "\nSUMMARY\n"
            + summary.to_csv(index=False)
            + "\nEXHAUSTIVE RESULTS\n"
            + ex_df.to_csv(index=False)
            + "\nBAYESIAN TRIAL HISTORY\n"
            + bo_df.to_csv(index=False)
        )

        st.download_button(
            "Download complete analysis report (.txt)",
            report,
            file_name="compiler_optimization_report.txt",
            mime="text/plain",
        )

        st.download_button(
            "Download exhaustive results (.csv)",
            ex_df.to_csv(index=False),
            file_name="exhaustive_results_current_input.csv",
            mime="text/csv",
        )

        st.download_button(
            "Download Bayesian trials (.csv)",
            bo_df.to_csv(index=False),
            file_name="bayesian_trials_current_input.csv",
            mime="text/csv",
        )

        st.subheader("Current input")
        st.code(result["source_code"], language="c")

        st.subheader("Comparison summary")

        st.dataframe(
            summary,
            use_container_width=True,
            hide_index=True,
        )

# ============================================================
# ML / RL LITERATURE COMPARISON
# ============================================================

if page == "ML / RL Comparison":
    st.header("Comparison with Machine Learning and Reinforcement Learning")

    st.warning(
        "ML and RL values below are qualitative literature comparisons, "
        "not experimental results from this custom compiler. This app does "
        "not run ML or RL models. Do not interpret literature results as "
        "accuracy measured on our program."
    )

    st.subheader("1. Methods comparison")

    comparison_df = pd.DataFrame([
        {
            "Method": "Exhaustive Search",
            "How it works": "Evaluates every candidate sequence",
            "Uses feedback": "Evaluates each sequence",
            "Separate training required": "No",
            "Main advantage": "Finds the best candidate in the defined search space",
            "Main limitation": "Evaluates all 64 candidates"
        },
        {
            "Method": "Bayesian Optimization (our implementation)",
            "How it works": "Uses a Random Forest surrogate and Expected Improvement",
            "Uses feedback": "Yes",
            "Separate training required": "No separate labelled dataset",
            "Main advantage": "Can explore promising candidates with fewer evaluations",
            "Main limitation": "May miss the exhaustive-search best sequence within a small budget"
        },
        {
            "Method": "Supervised Machine Learning",
            "How it works": "Learns from labelled programs and optimization outcomes",
            "Uses feedback": "Through its labelled training data",
            "Separate training required": "Yes",
            "Main advantage": "Can predict a sequence quickly after training",
            "Main limitation": "Needs representative labelled examples and may not generalize"
        },
        {
            "Method": "Reinforcement Learning",
            "How it works": "Learns sequential pass decisions from rewards",
            "Uses feedback": "Yes, via rewards",
            "Separate training required": "Usually requires training interactions",
            "Main advantage": "Can learn multi-step optimization policies",
            "Main limitation": "Training and exploration can be costly"
        }
    ])

    st.dataframe(
        comparison_df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download method comparison (CSV)",
        data=comparison_df.to_csv(index=False).encode("utf-8"),
        file_name="bo_ml_rl_method_comparison.csv",
        mime="text/csv"
    )

    st.subheader("2. Search-space size")

    from math import factorial

    space_rows = []
    for k in range(1, len(PASSES) + 1):
        count = factorial(len(PASSES)) // factorial(len(PASSES) - k)
        space_rows.append({
            "Sequence length": k,
            "Possible sequences": count
        })

    space_df = pd.DataFrame(space_rows)

    st.latex(
        r"\sum_{k=1}^{4} P(4,k) = 4 + 12 + 24 + 24 = 64"
    )

    fig_space = px.bar(
        space_df,
        x="Sequence length",
        y="Possible sequences",
        text="Possible sequences",
        title="Candidate Sequences by Number of Passes"
    )
    fig_space.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig_space, use_container_width=True)

    st.subheader("3. Evaluation budget versus exhaustive search")

    actual_unique = (
        len(result["bayesian_cache"])
        if result_matches_input
        else None
    )

    bo_evaluations = (
        int(result["bo_trials"])
        if result_matches_input
        else int(bo_trials)
    )

    budget_rows = [
        {
            "Method": "Bayesian Optimization",
            "Configured trials": bo_evaluations,
            "Unique sequences": actual_unique
        },
        {
            "Method": "Exhaustive Search",
            "Configured trials": 64,
            "Unique sequences": 64
        }
    ]

    budget_df = pd.DataFrame(budget_rows)

    budget_df["Configured budget (% of 64)"] = (
        budget_df["Configured trials"] / 64 * 100
    ).clip(upper=100)

    fig_budget = px.bar(
        budget_df,
        x="Method",
        y="Configured trials",
        color="Method",
        text="Configured trials",
        title="Configured Candidate Evaluation Budget"
    )

    fig_budget.update_layout(yaxis_title="Candidate evaluations")

    st.plotly_chart(
        fig_budget,
        use_container_width=True,
    )

    st.dataframe(
        budget_df,
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "The BO budget is the number of trials requested, not necessarily "
        "the number of unique sequences: repeated suggestions can be cached. "
        "Configured budget is not the same as unique search-space coverage."
    )

    st.subheader("4. Current-program optimization results")

    if not result_matches_input:
        st.info(
            "Run 'Analyze this input' in the sidebar first to show actual "
            "exhaustive-search and Bayesian Optimization results for the "
            "current program."
        )

    else:
        method_rows = []

        if result["ex_best_count"] is not None:
            method_rows.append({
                "Method": "Exhaustive Search",
                "Best TAC instructions": result["ex_best_count"],
                "Best sequence": result["ex_best_label"],
                "Evaluations": result["candidate_count"]
            })

        if result["bo_best_count"] is not None:
            method_rows.append({
                "Method": "Bayesian Optimization",
                "Best TAC instructions": result["bo_best_count"],
                "Best sequence": result["bo_best_label"],
                "Evaluations": result["bo_trials"]
            })

        current_results = pd.DataFrame(method_rows)

        if not current_results.empty:
            st.dataframe(
                current_results,
                use_container_width=True,
                hide_index=True
            )

            fig_tac = px.bar(
                current_results,
                x="Method",
                y="Best TAC instructions",
                color="Method",
                text="Best TAC instructions",
                title=(
                    "Measured Best TAC Count for This Program "
                    "(Lower Is Better)"
                )
            )

            st.plotly_chart(
                fig_tac,
                use_container_width=True,
            )

            if (
                result["ex_best_count"] is not None
                and result["bo_best_count"] is not None
            ):
                matched = (
                    result["bo_best_count"] == result["ex_best_count"]
                )

                st.metric(
                    "BO matched exhaustive best TAC count on this input",
                    "Yes" if matched else "No"
                )

                st.caption(
                    "This is a result for one input program only. It is not "
                    "a general ML/RL accuracy score or a statistical accuracy "
                    "estimate."
                )

    st.subheader("5. Accuracy: what can honestly be shown?")

    st.markdown(
        """
        For this project, *accuracy* is meaningful only if we define a
        prediction target and have measured predictions against ground truth.
        For example, a pass-sequence hit rate could measure how often a model
        predicts a sequence that matches the exhaustive-search best sequence
        on held-out programs.

        We have not run standalone supervised ML or RL models on this
        compiler, so their accuracy values are **not available**. We should
        not fill the chart with invented percentages or numbers copied from
        unrelated papers.
        """
    )

    st.subheader("6. Research references")

    st.markdown(
        """
        - Huang et al., **AutoPhase: Juggling HLS Phase Orderings in Random
          Forests with Deep Reinforcement Learning** (2020).
          [Paper](https://arxiv.org/abs/2003.00671)

        - Cummins et al., **CompilerGym: Robust, Performant Compiler
          Optimization Environments for Reinforcement Learning** (2022).
          [Paper](https://arxiv.org/abs/2110.06944)

        These studies use their own environments, benchmarks and objectives.
        Their reported results are useful background, but they are not
        directly comparable to TAC counts from this custom compiler.
        """
    )

    st.info(
        "Suggested report wording: 'We experimentally compare exhaustive "
        "search and Bayesian Optimization on our custom compiler. ML and RL "
        "are compared qualitatively using published literature; they were "
        "not experimentally evaluated in this prototype.'"
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "This application compares TAC instruction counts. "
    "It does not currently prove semantic equivalence of every "
    "optimization result or measure actual program runtime."
)
