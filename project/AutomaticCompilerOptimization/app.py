from pathlib import Path
import os
import shutil
import subprocess

import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================================
# PAGE SETUP
# ============================================================

st.set_page_config(
    page_title="Automatic Compiler Optimization",
    page_icon="⚙️",
    layout="wide",
)

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "bayesian"

st.title("⚙️ Automatic Compiler Optimization")
st.write(
    "Interactive dashboard for comparing Bayesian optimization "
    "with exhaustive search."
)

# ============================================================
# LOAD EXISTING CSV RESULTS
# ============================================================

@st.cache_data
def load_csv(path, modified_time):
    return pd.read_csv(path)


def read_csv(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return None
    return load_csv(str(path), path.stat().st_mtime)


def is_verified(df):
    if "verified" not in df.columns:
        return pd.Series(False, index=df.index)

    return df["verified"].astype(str).str.lower().isin(
        ["true", "1", "yes"]
    )


def get_scores(df):
    if "combined_tac_count" not in df.columns:
        return pd.Series(float("nan"), index=df.index)

    return pd.to_numeric(
        df["combined_tac_count"],
        errors="coerce",
    )


exhaustive = read_csv("exhaustive_search_results.csv")

bayesian_results = {
    seed: read_csv(f"optimization_results_seed_{seed}.csv")
    for seed in (2026, 2027, 2028)
}

# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Try Your Code",
        "Exhaustive Search",
        "Bayesian Optimization",
        "Reports & Downloads",
    ],
)

st.sidebar.caption("Results are loaded from the bayesian folder.")

if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
    st.rerun()

# ============================================================
# EXHAUSTIVE METRICS
# ============================================================

if exhaustive is not None:
    ex_verified = is_verified(exhaustive)
    ex_scores = get_scores(exhaustive)
    valid_scores = ex_scores[ex_verified].dropna()

    best_tac = (
        valid_scores.min()
        if not valid_scores.empty
        else None
    )

    baseline = None

    if "baseline_tac_count" in exhaustive.columns:
        baseline_values = pd.to_numeric(
            exhaustive["baseline_tac_count"],
            errors="coerce",
        ).dropna()

        if not baseline_values.empty:
            baseline = baseline_values.iloc[0]
else:
    ex_verified = None
    ex_scores = None
    best_tac = None
    baseline = None


# ============================================================
# COMPILER HELPERS
# ============================================================

def get_compiler():
    """Return an existing compiler or build it from bundled C sources."""

    bundled_exe = ROOT / "compiler.exe"

    if os.name == "nt" and bundled_exe.exists():
        return str(bundled_exe)

    gcc = shutil.which("gcc")

    if not gcc:
        raise RuntimeError(
            "A C compiler (gcc) is not available on this deployment. "
            "Add `build-essential` to packages.txt and redeploy."
        )

    built = ROOT / "compiler"

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
        str(item.name)
        for item in source_files
        if not item.exists()
    ]

    if missing:
        raise RuntimeError(
            "Compiler source files are missing: "
            + ", ".join(missing)
        )

    newest_source = max(
        item.stat().st_mtime
        for item in source_files
    )

    if (
        not built.exists()
        or built.stat().st_mtime < newest_source
    ):
        command = [
            gcc,
            "-D_POSIX_C_SOURCE=200809L",
            "-O2",
            "-o",
            str(built),
        ] + [
            str(item)
            for item in source_files
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ROOT),
        )

        if result.returncode:
            raise RuntimeError(
                "Could not build compiler:\n"
                + result.stderr[-5000:]
            )

    return str(built)


def extract_tac(output, marker):
    """Extract TAC instructions from compiler output."""

    if marker not in output:
        raise RuntimeError(
            "Compiler output did not contain: " + marker
        )

    part = output.split(marker, 1)[1]

    if "Three Address Code:" in part:
        part = part.split("Three Address Code:", 1)[1]

    lines = []

    for line in part.splitlines():
        line = line.strip()

        if line in {
            "Executing Optimization Passes:",
            "After Optimization:",
        }:
            break

        if line and not line.startswith("Enter program:"):
            lines.append(line)

    return lines


# ============================================================
# TRY YOUR CODE: BAYESIAN VS EXHAUSTIVE
# ============================================================

if page == "Try Your Code":
    from itertools import permutations

    st.header("Bayesian Optimization vs Exhaustive Search")

    st.write(
        "Run both methods on the same program. Exhaustive search "
        "evaluates every non-empty ordered subset of CF, AS, DCE "
        "and CSE (64 candidates). Bayesian optimization uses "
        "previous evaluations to guide its next choices."
    )

    default_source = """int a;
int b;
int c;
a = 10 + 20;
b = a * 2;
c = b + 0;
return c;
"""

    source_code = st.text_area(
        "Enter your program",
        value=default_source,
        height=240,
        help="Example: int x; x = 2 + 3; return x;",
    )

    bo_trials = st.slider(
        "Bayesian optimization evaluation budget",
        min_value=8,
        max_value=40,
        value=16,
        step=4,
        help=(
            "Number of Bayesian optimizer suggestions. "
            "Repeated suggestions may reuse cached results."
        ),
    )

    if st.button(
        "Compare Bayesian vs Exhaustive",
        type="primary",
    ):
        if not source_code.strip():
            st.error("Enter a program first.")

        else:
            try:
                from skopt import Optimizer
                from skopt.space import Categorical

                compiler = get_compiler()

                passes = ("CF", "AS", "DCE", "CSE")

                # Generate all non-empty ordered pass sequences.
                candidates = [
                    order
                    for length in range(1, len(passes) + 1)
                    for order in permutations(passes, length)
                ]

                candidate_labels = [
                    " -> ".join(order)
                    for order in candidates
                ]

                cache = {}

                def evaluate_sequence(order):
                    """Compile a program using a particular pass sequence."""

                    label = " -> ".join(order)

                    if label in cache:
                        return dict(cache[label])

                    result = subprocess.run(
                        [compiler, *order],
                        input=source_code,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        cwd=str(ROOT),
                    )

                    output = result.stdout

                    if result.returncode != 0:
                        row = {
                            "Sequence": label,
                            "Optimized TAC instructions": None,
                            "Status": "Failed",
                            "Error": (
                                result.stderr + "\n" + output
                            ).strip()[-2000:],
                            "Original TAC": [],
                            "Optimized TAC": [],
                        }

                    else:
                        original = extract_tac(
                            output,
                            "Before Optimization:",
                        )

                        optimized = extract_tac(
                            output,
                            "After Optimization:",
                        )

                        row = {
                            "Sequence": label,
                            "Optimized TAC instructions": len(
                                optimized
                            ),
                            "Status": "Success",
                            "Error": "",
                            "Original TAC": original,
                            "Optimized TAC": optimized,
                        }

                    cache[label] = dict(row)

                    return row

                # ------------------------------------------------
                # EXHAUSTIVE SEARCH
                # ------------------------------------------------

                st.subheader("1. Exhaustive Search")

                ex_progress = st.progress(
                    0,
                    text="Evaluating all 64 candidate sequences...",
                )

                exhaustive_rows = []

                for i, order in enumerate(
                    candidates,
                    start=1,
                ):
                    row = evaluate_sequence(order)

                    exhaustive_rows.append({
                        "Sequence": row["Sequence"],
                        "Optimized TAC instructions": (
                            row["Optimized TAC instructions"]
                        ),
                        "Status": row["Status"],
                    })

                    ex_progress.progress(
                        i / len(candidates),
                        text=(
                            f"Exhaustive: {i}/{len(candidates)}"
                        ),
                    )

                ex_progress.empty()

                # ------------------------------------------------
                # BAYESIAN OPTIMIZATION
                # ------------------------------------------------

                st.subheader("2. Bayesian Optimization")

                st.caption(
                    "The optimizer models the discrete sequence "
                    "choice and uses a random-forest surrogate to "
                    "select promising candidates. Its objective is "
                    "to minimize TAC instruction count."
                )

                optimizer = Optimizer(
                    dimensions=[
                        Categorical(
                            candidate_labels,
                            name="pass_sequence",
                        )
                    ],
                    base_estimator="RF",
                    acq_func="EI",
                    random_state=2026,
                    n_initial_points=min(8, bo_trials),
                )

                bo_rows = []

                bo_progress = st.progress(
                    0,
                    text="Starting Bayesian optimization...",
                )

                for trial in range(bo_trials):
                    suggestion = optimizer.ask()

                    label = suggestion[0]
                    order = tuple(label.split(" -> "))

                    row = evaluate_sequence(order)

                    score = row[
                        "Optimized TAC instructions"
                    ]

                    # Penalize failed compilations.
                    optimizer.tell(
                        suggestion,
                        (
                            float(score)
                            if score is not None
                            else 1_000_000.0
                        ),
                    )

                    already_seen = any(
                        item["Sequence"] == label
                        for item in bo_rows
                    )

                    bo_rows.append({
                        "Trial": trial + 1,
                        "Sequence": label,
                        "Optimized TAC instructions": score,
                        "Status": row["Status"],
                        "Evaluation": (
                            "Repeated suggestion"
                            if already_seen
                            else "Evaluated / retrieved"
                        ),
                    })

                    bo_progress.progress(
                        (trial + 1) / bo_trials,
                        text=(
                            f"Bayesian: {trial + 1}/{bo_trials}"
                        ),
                    )

                bo_progress.empty()

                # ------------------------------------------------
                # PREPARE RESULTS
                # ------------------------------------------------

                ex_df = pd.DataFrame(
                    exhaustive_rows
                ).sort_values(
                    "Optimized TAC instructions",
                    na_position="last",
                )

                bo_df = pd.DataFrame(bo_rows)

                ex_ok = ex_df.dropna(
                    subset=["Optimized TAC instructions"]
                )

                bo_ok = bo_df.dropna(
                    subset=["Optimized TAC instructions"]
                )

                if ex_ok.empty:
                    st.error(
                        "No candidate sequence compiled successfully. "
                        "Check the compiler output and source program."
                    )

                    failures = [
                        cache[key]
                        for key in cache
                        if cache[key]["Status"] != "Success"
                    ]

                    if failures and failures[0].get("Error"):
                        st.code(
                            failures[0]["Error"],
                            language="text",
                        )

                else:
                    ex_best_count = int(
                        ex_ok[
                            "Optimized TAC instructions"
                        ].min()
                    )

                    ex_best_label = str(
                        ex_ok.iloc[0]["Sequence"]
                    )

                    ex_best = cache[ex_best_label]

                    if not bo_ok.empty:
                        bo_best_count = int(
                            bo_ok[
                                "Optimized TAC instructions"
                            ].min()
                        )

                        bo_best_label = str(
                            bo_ok.sort_values(
                                "Optimized TAC instructions"
                            ).iloc[0]["Sequence"]
                        )

                        bo_best = cache[bo_best_label]

                    else:
                        bo_best_count = None
                        bo_best_label = (
                            "No successful Bayesian trial"
                        )
                        bo_best = None

                    # --------------------------------------------
                    # SUMMARY METRICS
                    # --------------------------------------------

                    st.subheader("Results Comparison")

                    m1, m2, m3, m4 = st.columns(4)

                    m1.metric(
                        "Exhaustive candidates",
                        f"{len(ex_ok)}/{len(candidates)}",
                    )

                    m2.metric(
                        "Exhaustive best TAC",
                        ex_best_count,
                    )

                    m3.metric(
                        "Bayesian trials",
                        bo_trials,
                    )

                    m4.metric(
                        "Bayesian best TAC",
                        (
                            bo_best_count
                            if bo_best_count is not None
                            else "N/A"
                        ),
                    )

                    compare_rows = [
                        {
                            "Method": "Exhaustive Search",
                            "Candidates / trials": len(candidates),
                            "Best sequence": ex_best_label,
                            "Best TAC count": ex_best_count,
                        },
                        {
                            "Method": "Bayesian Optimization",
                            "Candidates / trials": bo_trials,
                            "Best sequence": bo_best_label,
                            "Best TAC count": bo_best_count,
                        },
                    ]

                    st.dataframe(
                        pd.DataFrame(compare_rows),
                        use_container_width=True,
                        hide_index=True,
                    )

                    if bo_best_count is not None:
                        if bo_best_count == ex_best_count:
                            st.success(
                                "Bayesian optimization matched "
                                "the exhaustive-search best TAC "
                                "count on this program."
                            )

                        else:
                            st.info(
                                f"Bayesian search used a smaller "
                                f"evaluation budget and found "
                                f"{bo_best_count} TAC instructions; "
                                f"exhaustive search found "
                                f"{ex_best_count}. Bayesian "
                                f"optimization does not guarantee "
                                f"the global optimum."
                            )

                    # --------------------------------------------
                    # WINNING SEQUENCES
                    # --------------------------------------------

                    left, right = st.columns(2)

                    with left:
                        st.markdown(
                            "**Exhaustive Search Winner**"
                        )

                        st.code(
                            ex_best_label,
                            language="text",
                        )

                        st.caption(
                            f"Optimized TAC instructions: "
                            f"{ex_best_count}"
                        )

                        st.markdown("Original TAC")

                        st.code(
                            "\n".join(
                                ex_best["Original TAC"]
                            ) or "(no instructions)",
                            language="text",
                        )

                        st.markdown("Optimized TAC")

                        st.code(
                            "\n".join(
                                ex_best["Optimized TAC"]
                            ) or "(no instructions)",
                            language="text",
                        )

                    with right:
                        st.markdown(
                            "**Bayesian Optimization Winner**"
                        )

                        st.code(
                            bo_best_label,
                            language="text",
                        )

                        if bo_best is not None:
                            st.caption(
                                f"Optimized TAC instructions: "
                                f"{bo_best_count}"
                            )

                            st.markdown("Original TAC")

                            st.code(
                                "\n".join(
                                    bo_best["Original TAC"]
                                ) or "(no instructions)",
                                language="text",
                            )

                            st.markdown("Optimized TAC")

                            st.code(
                                "\n".join(
                                    bo_best["Optimized TAC"]
                                ) or "(no instructions)",
                                language="text",
                            )

                    # --------------------------------------------
                    # EXHAUSTIVE RESULTS TABLE AND CHART
                    # --------------------------------------------

                    st.subheader(
                        "Exhaustive Search — All Candidates"
                    )

                    st.dataframe(
                        ex_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    ex_plot = ex_df.dropna(
                        subset=["Optimized TAC instructions"]
                    )

                    if not ex_plot.empty:
                        st.plotly_chart(
                            px.bar(
                                ex_plot,
                                x="Sequence",
                                y="Optimized TAC instructions",
                                title=(
                                    "Exhaustive Search: "
                                    "TAC Count by Sequence"
                                ),
                            ),
                            use_container_width=True,
                        )

                    # --------------------------------------------
                    # BAYESIAN RESULTS TABLE AND CHART
                    # --------------------------------------------

                    st.subheader(
                        "Bayesian Optimization — Trial History"
                    )

                    st.dataframe(
                        bo_df,
                        use_container_width=True,
                        hide_index=True,
                    )

                    if not bo_ok.empty:
                        bo_plot = bo_df.dropna(
                            subset=[
                                "Optimized TAC instructions"
                            ]
                        )

                        st.plotly_chart(
                            px.line(
                                bo_plot,
                                x="Trial",
                                y="Optimized TAC instructions",
                                markers=True,
                                title=(
                                    "Bayesian Optimization: "
                                    "TAC Count by Trial"
                                ),
                            ),
                            use_container_width=True,
                        )

                    # --------------------------------------------
                    # DOWNLOAD REPORT
                    # --------------------------------------------

                    report = (
                        pd.DataFrame(compare_rows).to_csv(
                            index=False
                        )
                        + "\n\nEXHAUSTIVE RESULTS\n"
                        + ex_df.to_csv(index=False)
                        + "\nBAYESIAN TRIALS\n"
                        + bo_df.to_csv(index=False)
                    )

                    st.download_button(
                        "Download Comparison CSV Report",
                        report.encode("utf-8"),
                        file_name=(
                            "bayesian_vs_exhaustive_comparison.csv"
                        ),
                        mime="text/csv",
                    )

                    st.caption(
                        "Both methods optimize TAC instruction count, "
                        "not measured runtime. This comparison does not "
                        "independently prove semantic equivalence of "
                        "each optimization result."
                    )

            except ImportError:
                st.error(
                    "Bayesian optimization package is missing. "
                    "Add `scikit-optimize` to requirements.txt "
                    "and redeploy."
                )

            except (
                RuntimeError,
                subprocess.TimeoutExpired,
                OSError,
                ValueError,
            ) as exc:
                st.error(str(exc))


# ============================================================
# OVERVIEW PAGE
# ============================================================

if page == "Overview":
    st.header("Project Overview")

    if exhaustive is None:
        st.error(
            "Could not find bayesian/exhaustive_search_results.csv"
        )
        st.stop()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Baseline TAC",
        int(baseline) if baseline is not None else "N/A",
    )

    col2.metric(
        "Best TAC",
        int(best_tac) if best_tac is not None else "N/A",
    )

    if (
        baseline is not None
        and best_tac is not None
        and baseline
    ):
        reduction = (
            (baseline - best_tac) / baseline * 100
        )

        col3.metric(
            "TAC Reduction",
            f"{reduction:.2f}%",
        )
    else:
        col3.metric("TAC Reduction", "N/A")

    col4.metric(
        "Verified Exhaustive Orders",
        f"{int(ex_verified.sum())}/{len(exhaustive)}",
    )

    st.subheader("Bayesian Optimization Summary")

    summary = []

    for seed, df in bayesian_results.items():
        if df is None:
            continue

        verified = is_verified(df)
        scores = get_scores(df)[verified].dropna()

        summary.append({
            "Seed": seed,
            "Candidates": len(df),
            "Verified": int(verified.sum()),
            "Best TAC": (
                int(scores.min())
                if not scores.empty
                else None
            ),
            "Matches exhaustive best": (
                bool(scores.min() == best_tac)
                if (
                    not scores.empty
                    and best_tac is not None
                )
                else None
            ),
        })

    if summary:
        summary_df = pd.DataFrame(summary)

        st.dataframe(
            summary_df,
            use_container_width=True,
            hide_index=True,
        )

        fig = px.bar(
            summary_df,
            x="Seed",
            y="Best TAC",
            title="Best TAC Count by Bayesian Random Seed",
            text="Best TAC",
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    else:
        st.warning(
            "No Bayesian result files were found."
        )

    st.info(
        "TAC reduction measures instruction-count reduction, "
        "not necessarily runtime speedup."
    )


# ============================================================
# EXHAUSTIVE SEARCH RESULTS PAGE
# ============================================================

elif page == "Exhaustive Search":
    st.header("Exhaustive Search Results")

    if exhaustive is None:
        st.error("Exhaustive result CSV not found.")
        st.stop()

    verified = is_verified(exhaustive)
    scores = get_scores(exhaustive)

    st.write(
        f"Orders tested: **{len(exhaustive)}**"
    )

    st.write(
        f"Verified: **{int(verified.sum())}**"
    )

    st.write(
        f"Failed or unverified: **{int((~verified).sum())}**"
    )

    best_rows = exhaustive.loc[
        verified & scores.eq(best_tac)
    ]

    st.subheader("Best Sequences")

    st.dataframe(
        best_rows,
        use_container_width=True,
        hide_index=True,
    )

    plot_df = exhaustive.copy()
    plot_df["TAC Count"] = get_scores(plot_df)

    plot_df["Status"] = is_verified(plot_df).map({
        True: "Verified",
        False: "Not verified",
    })

    fig = px.bar(
        plot_df,
        x="sequence",
        y="TAC Count",
        color="Status",
        title="TAC Count for All Pass Orderings",
        hover_data=["sequence"],
    )

    fig.update_layout(
        xaxis_tickangle=-45
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    st.subheader("All Results")

    st.dataframe(
        exhaustive,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "Download Exhaustive Results CSV",
        exhaustive.to_csv(index=False).encode("utf-8"),
        file_name="exhaustive_search_results.csv",
        mime="text/csv",
    )


# ============================================================
# BAYESIAN OPTIMIZATION RESULTS PAGE
# ============================================================

elif page == "Bayesian Optimization":
    st.header("Bayesian Optimization Results")

    seed = st.selectbox(
        "Select random seed",
        [2026, 2027, 2028],
    )

    df = bayesian_results[seed]

    if df is None:
        st.warning(
            f"Results for seed {seed} were not found."
        )
        st.stop()

    verified = is_verified(df)
    scores = get_scores(df)[verified].dropna()

    c1, c2, c3 = st.columns(3)

    c1.metric("Candidates", len(df))

    c2.metric(
        "Verified",
        f"{int(verified.sum())}/{len(df)}",
    )

    c3.metric(
        "Best TAC",
        int(scores.min()) if not scores.empty else "N/A",
    )

    st.subheader("Candidate Results")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )

    plot_df = df.copy()
    plot_df["TAC Count"] = get_scores(plot_df)

    plot_df["Status"] = is_verified(plot_df).map({
        True: "Verified",
        False: "Not verified",
    })

    fig = px.bar(
        plot_df,
        x="sequence",
        y="TAC Count",
        color="Status",
        title=f"Bayesian Candidates — Seed {seed}",
        hover_data=["sequence"],
    )

    fig.update_layout(
        xaxis_tickangle=-45
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
    )

    st.download_button(
        f"Download Seed {seed} CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"optimization_results_seed_{seed}.csv",
        mime="text/csv",
    )

    image_path = (
        DATA_DIR
        / f"optimization_results_seed_{seed}.png"
    )

    if image_path.exists():
        st.subheader("Saved Optimization Plot")

        st.image(
            str(image_path),
            use_container_width=True,
        )


# ============================================================
# REPORTS AND DOWNLOADS PAGE
# ============================================================

elif page == "Reports & Downloads":
    st.header("Reports & Downloads")

    for seed in (2026, 2027, 2028):
        report_path = (
            DATA_DIR
            / f"optimization_report_seed_{seed}.txt"
        )

        if report_path.exists():
            with st.expander(
                f"Optimization Report — Seed {seed}"
            ):
                report_text = report_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )

                st.text(report_text)

                st.download_button(
                    f"Download Report {seed}",
                    report_text,
                    file_name=(
                        f"optimization_report_seed_{seed}.txt"
                    ),
                    mime="text/plain",
                    key=f"report_{seed}",
                )

    st.subheader("All Available Result Files")

    for path in (
        sorted(DATA_DIR.iterdir())
        if DATA_DIR.exists()
        else []
    ):
        if not path.is_file():
            continue

        if path.suffix.lower() in [
            ".csv",
            ".txt",
            ".png",
        ]:
            st.write(
                f"**{path.name}** "
                f"({path.stat().st_size:,} bytes)"
            )

            if path.suffix.lower() == ".png":
                with st.expander(
                    f"Preview {path.name}"
                ):
                    st.image(
                        str(path),
                        use_container_width=True,
                    )

            else:
                st.download_button(
                    f"Download {path.name}",
                    data=path.read_bytes(),
                    file_name=path.name,
                    key=f"download_{path.name}",
                )
