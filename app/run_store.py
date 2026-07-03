"""Local persistence and static reports for app research runs."""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from .utils import redact_secrets

DEFAULT_RESULTS_DIR = Path("results")
RUNS_DIR_ENV = "CO_SCIENTIST_RUNS_DIR"

SECRET_PATTERNS = [
    re.compile(r"sk-or-v1-[A-Za-z0-9_-]+"),
    re.compile(r"sk-proj-[A-Za-z0-9_-]+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s<>'\"]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s<>'\"]+"),
]


def get_results_dir() -> Path:
    return Path(os.getenv(RUNS_DIR_ENV, DEFAULT_RESULTS_DIR))


def get_runs_dir() -> Path:
    return get_results_dir() / "runs"


def get_reports_dir() -> Path:
    return get_results_dir() / "reports"


def report_file_url(report_path: Path) -> str:
    """Return a Gradio file-serving URL for a generated report."""
    return f"/gradio_api/file={quote(report_path.resolve().as_posix())}"


def generate_run_id(created_at: Optional[dt.datetime] = None) -> str:
    timestamp = (created_at or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%d-%H%M%S")
    return f"run-{timestamp}-{uuid.uuid4().hex[:8]}"


def redact_text(text: str) -> str:
    redacted = redact_secrets(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(
            lambda match: f"{match.group(1)}***REDACTED***" if match.groups() else "***REDACTED***", redacted
        )
    return redacted


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    return value


def research_goal_to_dict(research_goal: Any) -> Dict[str, Any]:
    if research_goal is None:
        return {}
    return sanitize(
        {
            "description": getattr(research_goal, "description", ""),
            "constraints": getattr(research_goal, "constraints", {}),
            "llm_model": getattr(research_goal, "llm_model", None),
            "num_hypotheses": getattr(research_goal, "num_hypotheses", None),
            "generation_temperature": getattr(research_goal, "generation_temperature", None),
            "reflection_temperature": getattr(research_goal, "reflection_temperature", None),
            "elo_k_factor": getattr(research_goal, "elo_k_factor", None),
            "top_k_hypotheses": getattr(research_goal, "top_k_hypotheses", None),
        }
    )


def save_run(
    *,
    research_goal: Any,
    cycle_details: Dict[str, Any],
    status: str,
    references_html: str,
    results_html: str,
    log_file: Optional[str] = None,
    run_id: Optional[str] = None,
    created_at: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    created = created_at or dt.datetime.now(dt.timezone.utc)
    run = sanitize(
        {
            "run_id": run_id or generate_run_id(created),
            "created_at": created.isoformat(),
            "research_goal": research_goal_to_dict(research_goal),
            "status": status,
            "log_file": log_file,
            "cycle_details": cycle_details,
            "references_html": references_html,
            "results_html": results_html,
        }
    )
    get_runs_dir().mkdir(parents=True, exist_ok=True)
    run_path = get_run_path(run["run_id"])
    run_path.write_text(json.dumps(run, indent=2, sort_keys=True), encoding="utf-8")
    return run


def get_run_path(run_id: str) -> Path:
    safe_run_id = Path(run_id).name
    return get_runs_dir() / f"{safe_run_id}.json"


def load_run(run_id: str) -> Dict[str, Any]:
    return json.loads(get_run_path(run_id).read_text(encoding="utf-8"))


def list_runs(limit: int = 20) -> List[Dict[str, Any]]:
    runs_dir = get_runs_dir()
    if not runs_dir.exists():
        return []

    summaries = []
    for path in runs_dir.glob("*.json"):
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        goal = run.get("research_goal", {})
        cycle = run.get("cycle_details", {})
        summaries.append(
            {
                "run_id": run.get("run_id", path.stem),
                "created_at": run.get("created_at", ""),
                "goal": goal.get("description", ""),
                "model": goal.get("llm_model", ""),
                "iteration": cycle.get("iteration", ""),
                "status": run.get("status", ""),
            }
        )

    return sorted(summaries, key=lambda item: item.get("created_at", ""), reverse=True)[:limit]


def render_report(run: Dict[str, Any]) -> str:
    goal = run.get("research_goal", {})
    cycle = run.get("cycle_details", {})
    steps = cycle.get("steps", {})
    final_hypotheses = _final_hypotheses(steps)

    html_parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(run.get('run_id'), 'Run report')}</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;line-height:1.5;margin:32px;color:#1f2933;background:#fff}",
        "main{max-width:960px;margin:0 auto}",
        "section{border-top:1px solid #d9e2ec;padding-top:18px;margin-top:24px}",
        ".meta{color:#52606d}.hypothesis{border-left:4px solid #2f80ed;padding-left:12px;margin:14px 0}",
        "pre{white-space:pre-wrap;background:#f5f7fa;padding:12px;border-radius:6px;overflow:auto}",
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #d9e2ec;padding:8px;text-align:left}",
        "</style>",
        "</head>",
        "<body><main>",
        f"<h1>Research Run {_escape(run.get('run_id'))}</h1>",
        f'<p class="meta">Created: {_escape(run.get("created_at"))}</p>',
        f"<p>{_escape(run.get('status'))}</p>",
        "<section><h2>Research Goal</h2>",
        f"<p>{_escape(goal.get('description'))}</p>",
        _settings_table(goal),
        "</section>",
        "<section><h2>Final Hypotheses</h2>",
    ]

    if final_hypotheses:
        for index, hypothesis in enumerate(final_hypotheses, start=1):
            html_parts.append(_hypothesis_block(index, hypothesis))
    else:
        html_parts.append("<p>No final hypotheses were available for this run.</p>")

    html_parts.append("</section><section><h2>Cycle Steps</h2>")
    for step_name, step_data in steps.items():
        hypotheses = step_data.get("hypotheses", []) if isinstance(step_data, dict) else []
        html_parts.append(f"<h3>{_escape(step_name)}</h3>")
        html_parts.append(f"<p>{len(hypotheses)} hypotheses</p>")
        if step_name == "meta_review":
            html_parts.append(f"<pre>{_escape(json.dumps(step_data, indent=2, sort_keys=True))}</pre>")

    html_parts.extend(
        [
            "</section><section><h2>References</h2>",
            "<p>Reference results are stored from the app display for this run.</p>",
            f"<pre>{_escape(run.get('references_html'))}</pre>",
            "</section>",
            "</main></body></html>",
        ]
    )
    return "\n".join(html_parts)


def write_report(run: Dict[str, Any]) -> Path:
    get_reports_dir().mkdir(parents=True, exist_ok=True)
    report_path = get_reports_dir() / f"{Path(run['run_id']).name}.html"
    report_path.write_text(render_report(run), encoding="utf-8")
    return report_path


def ensure_report(run_id: str) -> Path:
    return write_report(load_run(run_id))


def history_html(limit: int = 20) -> str:
    runs = list_runs(limit=limit)
    if not runs:
        return "<p>No saved runs yet.</p>"

    rows = []
    for run in runs:
        try:
            report_path = ensure_report(run["run_id"])
            report_link = report_file_url(report_path)
        except OSError:
            report_link = "#"
        rows.append(
            "<tr>"
            f"<td>{_escape(run.get('created_at'))}</td>"
            f"<td>{_escape(run.get('goal'))}</td>"
            f"<td>{_escape(run.get('iteration'))}</td>"
            f"<td><code>{_escape(run.get('run_id'))}</code></td>"
            f'<td><a href="{_escape(report_link)}" target="_blank">Open report</a></td>'
            "</tr>"
        )

    return (
        "<table><thead><tr><th>Created</th><th>Goal</th><th>Iteration</th><th>Run ID</th><th>Report</th></tr>"
        "</thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _settings_table(goal: Dict[str, Any]) -> str:
    fields = [
        "llm_model",
        "num_hypotheses",
        "generation_temperature",
        "reflection_temperature",
        "elo_k_factor",
        "top_k_hypotheses",
    ]
    rows = "".join(f"<tr><th>{_escape(field)}</th><td>{_escape(goal.get(field))}</td></tr>" for field in fields)
    return f"<table><tbody>{rows}</tbody></table>"


def _final_hypotheses(steps: Dict[str, Any]) -> List[Dict[str, Any]]:
    for step_name in ("ranking_final", "ranking2", "ranking", "ranking1"):
        hypotheses = steps.get(step_name, {}).get("hypotheses", [])
        if hypotheses:
            return sorted(hypotheses, key=lambda item: item.get("elo_score", 0), reverse=True)
    for step_data in steps.values():
        hypotheses = step_data.get("hypotheses", []) if isinstance(step_data, dict) else []
        if hypotheses:
            return hypotheses
    return []


def _hypothesis_block(index: int, hypothesis: Dict[str, Any]) -> str:
    comments = hypothesis.get("review_comments") or []
    comments_html = "".join(f"<li>{_escape(comment)}</li>" for comment in comments)
    return (
        '<div class="hypothesis">'
        f"<h3>{index}. {_escape(hypothesis.get('title'), 'Untitled')}</h3>"
        f"<p><strong>ID:</strong> {_escape(hypothesis.get('id'))} | "
        f"<strong>Elo:</strong> {_escape(hypothesis.get('elo_score'))}</p>"
        f"<p>{_escape(hypothesis.get('text'))}</p>"
        f"<p><strong>Novelty:</strong> {_escape(hypothesis.get('novelty_review'))} | "
        f"<strong>Feasibility:</strong> {_escape(hypothesis.get('feasibility_review'))}</p>"
        f"<ul>{comments_html}</ul>"
        "</div>"
    )


def _escape(value: Any, default: str = "") -> str:
    if value is None:
        value = default
    return html.escape(str(value))
