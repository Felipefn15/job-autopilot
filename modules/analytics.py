"""
Analytics Module
Lê jobs.db e gera métricas por fonte: volume, taxa de conversão (success/failed),
média de score (AI). Exibe dashboard no terminal com rich.
"""
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Rich para tabela no terminal (fallback para tabulate-style em texto se import falhar)
try:
    from rich.console import Console
    from rich.table import Table
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# Mapeamento source (DB/URL) -> nome de exibição no dashboard
SOURCE_DISPLAY = {
    "linkedin_post": "LinkedIn",
    "github_sniper": "GitHub Issues",
    "twitter_sniper": "Twitter/X",
    "google_dorks_sniper": "Google Dorks",
}


def _infer_source_from_url(url: str) -> str:
    """Inferir fonte a partir da URL quando coluna source não existir ou for NULL."""
    if not url:
        return "Unknown"
    u = url.lower()
    if u.startswith("email:"):
        return "Unknown"
    if "linkedin.com" in u:
        return "linkedin_post"
    if "github.com" in u:
        return "github_sniper"
    if "x.com" in u or "twitter.com" in u:
        return "twitter_sniper"
    for domain in ("lever.co", "greenhouse.io", "recruitee.com", "workable.com", "ashbyhq.com"):
        if domain in u:
            return "google_dorks_sniper"
    return "Unknown"


def _normalize_source(source: Optional[str], url: str) -> str:
    """Retorna chave normalizada para agregação (linkedin_post, github_sniper, etc.)."""
    if source and source.strip():
        return source.strip()
    return _infer_source_from_url(url)


def get_metrics_by_source(db_path: str = "jobs.db") -> List[Tuple[str, int, int, int, float, bool]]:
    """
    Lê jobs.db e agrega por fonte (exibição).
    Returns: list of (display_name, total, success, failed, avg_score, has_pending)
    """
    path = Path(db_path)
    if not path.exists():
        return []

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Verificar se coluna source existe
    cursor.execute("PRAGMA table_info(jobs_processed)")
    columns = [row[1] for row in cursor.fetchall()]
    has_source_col = "source" in columns

    if has_source_col:
        cursor.execute("SELECT url, status, match_score, source FROM jobs_processed")
    else:
        cursor.execute("SELECT url, status, match_score FROM jobs_processed")

    rows = cursor.fetchall()
    conn.close()

    # Agregação por fonte normalizada
    # total, success, failed, sum_score, count_score, has_pending
    agg: Dict[str, Tuple[int, int, int, float, int, bool]] = defaultdict(
        lambda: (0, 0, 0, 0.0, 0, False)
    )

    for row in rows:
        url = row["url"]
        status = row["status"]
        score = row["match_score"]
        source_raw = row["source"] if has_source_col else None
        key = _normalize_source(source_raw, url)

        total, success, failed, sum_s, count_s, pending = agg[key]
        total += 1
        if status == "SUCCESS" or status == "PENDING_REVIEW":
            success += 1
        elif status == "FAILED":
            failed += 1
        if status in ("EASY_APPLY_PENDING", "PENDING"):
            pending = True
        if score is not None and isinstance(score, (int, float)):
            sum_s += float(score)
            count_s += 1
        agg[key] = (total, success, failed, sum_s, count_s, pending)

    # Montar lista (display_name, total, success, failed, avg_score, has_pending)
    result = []
    for key, (total, success, failed, sum_s, count_s, pending) in agg.items():
        display = SOURCE_DISPLAY.get(key, key.replace("_", " ").title())
        avg = (sum_s / count_s) if count_s else 0.0
        result.append((display, total, success, failed, round(avg, 2), pending))
    result.sort(key=lambda x: -x[1])  # Por volume total decrescente
    return result


def print_dashboard(db_path: str = "jobs.db") -> None:
    """Imprime o JOB ENGINE PERFORMANCE DASHBOARD no terminal."""
    metrics = get_metrics_by_source(db_path)

    if RICH_AVAILABLE:
        console = Console()
        table = Table(
            title="JOB ENGINE PERFORMANCE DASHBOARD",
            show_header=True,
            header_style="bold",
            border_style="dim",
        )
        table.add_column("SOURCE", style="cyan", no_wrap=True)
        table.add_column("TOTAL", justify="right", style="green")
        table.add_column("SUCCESS", justify="right", style="green")
        table.add_column("FAILED", justify="right", style="red")
        table.add_column("AVG SCORE", justify="right", style="yellow")

        for display_name, total, success, failed, avg_score, has_pending in metrics:
            score_str = f"{avg_score:.2f}"
            if has_pending and success == 0 and failed == 0:
                score_str += " (Pending)"
            table.add_row(display_name, str(total), str(success), str(failed), score_str)

        console.print()
        console.print(table)
        console.print()
        return

    # Fallback sem rich
    width = 60
    print()
    print("=" * width)
    print("JOB ENGINE PERFORMANCE DASHBOARD")
    print("=" * width)
    print(f"{'SOURCE':<18} | {'TOTAL':>6} | {'SUCCESS':>7} | {'FAILED':>6} | {'AVG SCORE':>10}")
    print("-" * width)
    for display_name, total, success, failed, avg_score, has_pending in metrics:
        score_str = f"{avg_score:.2f}"
        if has_pending and success == 0 and failed == 0:
            score_str += " (Pending)"
        print(f"{display_name:<18} | {total:>6} | {success:>7} | {failed:>6} | {score_str:>10}")
    print("=" * width)
    print()


def run_stats(db_path: str = "jobs.db") -> None:
    """Entrypoint para ./run.sh --stats: carrega jobs.db e imprime dashboard."""
    print("\n📊 Analytics (jobs.db)\n")
    print_dashboard(db_path)


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "jobs.db"
    run_stats(db_path)
