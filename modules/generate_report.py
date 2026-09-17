"""
Report de Sniper: consolida as últimas 24h em estatísticas e destaque por score.
Saída no terminal e opcionalmente em arquivo .txt para controle do pipeline.
"""
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path


def generate_daily_report(db_path: str = "jobs.db", output_file: str = None, quiet: bool = False):
    """
    Gera relatório das últimas 24h usando jobs_processed (processed_at).
    output_file: se informado, grava também em arquivo .txt
    quiet: se True, não imprime no terminal (útil quando só quer salvar)
    """
    db = sqlite3.connect(db_path)
    cursor = db.cursor()

    # Janela 24h: processed_at em ISO (SQLite aceita datetime('now', '-1 day'))
    cursor.execute("""
        SELECT status, COUNT(*) FROM jobs_processed
        WHERE processed_at > datetime('now', '-1 day')
        GROUP BY status
    """)
    stats = dict(cursor.fetchall())

    success = stats.get("SUCCESS", 0)
    pending = stats.get("PENDING", 0)
    manual = stats.get("MANUAL_REVIEW", 0)
    skipped = stats.get("SKIPPED", 0)
    failed = stats.get("FAILED", 0)
    total_24h = success + pending + manual + skipped + failed

    # ROI: vagas “encontradas” (qualquer status) vs e-mails enviados com sucesso
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append("📊 RELATÓRIO DE PERFORMANCE - SNIPER ENGINE")
    lines.append("Período: Últimas 24h")
    lines.append("=" * 60)
    lines.append("")
    lines.append("1. Estatísticas gerais (24h)")
    lines.append("-" * 40)
    lines.append(f"  ✅ Sucessos (Gmail SMTP): {success}")
    lines.append(f"  ⏳ Pendentes de envio:    {pending}")
    lines.append(f"  🔍 Em revisão manual:     {manual}")
    lines.append(f"  🚫 Pulados/Rejeitados:    {skipped}")
    lines.append(f"  ❌ Falhas:                {failed}")
    lines.append("-" * 60)
    lines.append("")
    lines.append("2. ROI (últimas 24h)")
    lines.append("-" * 40)
    lines.append(f"  Vagas processadas: {total_24h}  |  E-mails enviados: {success}")
    if total_24h > 0:
        pct = 100.0 * success / total_24h
        lines.append(f"  Taxa de envio:     {pct:.1f}%")
    lines.append("-" * 60)
    lines.append("")
    lines.append("3. 🏆 Top candidaturas enviadas (maiores scores)")
    lines.append("-" * 40)

    try:
        cursor.execute("""
            SELECT title, company, match_score, email
            FROM jobs_processed
            WHERE status = 'SUCCESS' AND processed_at > datetime('now', '-1 day')
            ORDER BY match_score DESC
            LIMIT 5
        """)
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        cursor.execute("""
            SELECT title, company, match_score
            FROM jobs_processed
            WHERE status = 'SUCCESS' AND processed_at > datetime('now', '-1 day')
            ORDER BY match_score DESC
            LIMIT 5
        """)
        rows = [(r[0], r[1], r[2], None) for r in cursor.fetchall()]

    if rows:
        for row in rows:
            title, company, score = row[0], row[1], row[2]
            email = row[3] if len(row) > 3 else None
            score_str = f"{score:.2f}" if score is not None else "N/A"
            email_short = ((email or "-")[:40]) if email else "-"
            lines.append(f"  ⭐ [{score_str}] {title} @ {company}")
            lines.append(f"      {email_short}")
    else:
        lines.append("  (nenhuma candidatura com sucesso nas últimas 24h)")
    lines.append("")
    lines.append("=" * 60)
    lines.append("")

    db.close()

    text = "\n".join(lines)
    if not quiet:
        print(text)

    if output_file:
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if not quiet:
            print(f"  📄 Report salvo em: {path.resolve()}")

    return {
        "success": success,
        "pending": pending,
        "manual_review": manual,
        "skipped": skipped,
        "failed": failed,
        "total_24h": total_24h,
    }


if __name__ == "__main__":
    import os
    db_path = os.getenv("JOBS_DB_PATH", "jobs.db")
    output = os.getenv("REPORT_OUTPUT")  # e.g. reports/daily.txt
    quiet = "--quiet" in sys.argv or "-q" in sys.argv
    generate_daily_report(db_path=db_path, output_file=output, quiet=quiet)
