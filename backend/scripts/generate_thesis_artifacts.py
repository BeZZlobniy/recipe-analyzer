from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator


ROOT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = ROOT_DIR / "app.db"
REPORT_DIR = ROOT_DIR / "reports" / "thesis"
CHART_DIR = REPORT_DIR / "charts"


def read_analyses() -> list[dict[str, Any]]:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT id, title, summary, diet_compatibility, restriction_compatibility, goal_compatibility, analysis_result_json
        FROM recipe_analyses
        ORDER BY id
        """
    ).fetchall()

    analyses: list[dict[str, Any]] = []
    for row in rows:
        payload = row["analysis_result_json"]
        result = json.loads(payload) if isinstance(payload, str) else payload
        analyses.append(
            {
                "id": row["id"],
                "title": row["title"],
                "summary": row["summary"],
                "diet_compatibility": row["diet_compatibility"],
                "restriction_compatibility": row["restriction_compatibility"],
                "goal_compatibility": row["goal_compatibility"],
                "result": result or {},
            }
        )
    con.close()
    return analyses


def _metric_value(result: dict[str, Any], group: str, metric: str) -> float:
    value = result.get(group, {}).get(metric, {}).get("value", 0)
    return float(value or 0)


def flatten_analyses(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for item in analyses:
        result = item["result"]
        quality = result.get("analysis_quality", {})
        compatibility = result.get("compatibility", {})

        flattened.append(
            {
                "id": item["id"],
                "title": item["title"],
                "summary": item["summary"],
                "calories_total": _metric_value(result, "nutrition_total", "calories"),
                "calories_per_serving": _metric_value(result, "nutrition_per_serving", "calories"),
                "protein_per_serving": _metric_value(result, "nutrition_per_serving", "protein"),
                "fat_per_serving": _metric_value(result, "nutrition_per_serving", "fat"),
                "carbohydrates_per_serving": _metric_value(result, "nutrition_per_serving", "carbohydrates"),
                "fiber_per_serving": _metric_value(result, "nutrition_per_serving", "fiber"),
                "sodium_per_serving": _metric_value(result, "nutrition_per_serving", "sodium"),
                "quality_score": float(quality.get("score", 0) or 0),
                "explicit_amount_ratio": float(quality.get("explicit_amount_ratio", 0) or 0),
                "matched_ratio": float(quality.get("matched_ratio", 0) or 0),
                "trusted_nutrition_ratio": float(quality.get("trusted_nutrition_ratio", 0) or 0),
                "unresolved_ratio": float(quality.get("unresolved_ratio", 0) or 0),
                "meaningful_fallback_ratio": float(quality.get("meaningful_fallback_ratio", 0) or 0),
                "diet_compatibility": item["diet_compatibility"] or compatibility.get("diet", ""),
                "restriction_compatibility": item["restriction_compatibility"] or compatibility.get("restriction", ""),
                "goal_compatibility": item["goal_compatibility"] or compatibility.get("goal", ""),
            }
        )
    return flattened


def ensure_dirs() -> None:
    CHART_DIR.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown_table(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    headers = list(rows[0].keys())
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[header]) for header in headers) + " |")
    path.write_text("\n".join(lines), encoding="utf-8")


def _average(rows: list[dict[str, Any]], key: str) -> float:
    return round(sum(float(row[key]) for row in rows) / max(len(rows), 1), 2)


def write_methodology_note(path: Path, rows: list[dict[str, Any]]) -> None:
    text = f"""Методологическая записка для подраздела 3.2.1

Тестирование проводилось на демонстрационной выборке из {len(rows)} рецептов, различающихся по калорийности и совместимости с пользовательским профилем.

В рамках проверки оценивались:
- корректность маршрутов frontend/backend;
- устойчивость полного конвейера анализа;
- полнота сопоставления ингредиентов с USDA;
- отсутствие unresolved ingredients в демонстрационных кейсах;
- реалистичность пищевой ценности;
- корректность compatibility по трем осям.

Средний quality score по демонстрационной выборке: {_average(rows, "quality_score")}.
Средняя калорийность на рецепт: {_average(rows, "calories_total")} ккал.
Средняя калорийность на порцию: {_average(rows, "calories_per_serving")} ккал.
Средний explicit_amount_ratio: {_average(rows, "explicit_amount_ratio")}.
Средний meaningful_fallback_ratio: {_average(rows, "meaningful_fallback_ratio")}.
"""
    path.write_text(text, encoding="utf-8")


def write_comparison_note(path: Path) -> None:
    text = """Сравнительная записка для подраздела 3.2.2

Для сравнительного анализа предлагается использовать следующие классы решений:
- ручные калькуляторы калорий;
- rule-based решения без LLM;
- LLM-only решения;
- разработанную гибридную систему.

Ключевые преимущества разработанной системы:
- поддержка свободного текста рецепта;
- автоматическое извлечение ингредиентов;
- deterministic nutrition layer на базе USDA;
- персонализация по пользовательскому профилю;
- хранение истории и построение dashboard;
- наличие внутренних quality metrics анализа.
"""
    path.write_text(text, encoding="utf-8")


def write_comparison_table(path: Path) -> None:
    rows = [
        {
            "Критерий": "Свободный текст рецепта",
            "Ручной калькулятор": "нет",
            "Rule-based only": "частично",
            "LLM-only": "да",
            "Разработанная система": "да",
        },
        {
            "Критерий": "Автоматическое извлечение ингредиентов",
            "Ручной калькулятор": "нет",
            "Rule-based only": "частично",
            "LLM-only": "да",
            "Разработанная система": "да",
        },
        {
            "Критерий": "Верифицируемый источник нутриентов",
            "Ручной калькулятор": "частично",
            "Rule-based only": "зависит от реализации",
            "LLM-only": "нет",
            "Разработанная система": "да",
        },
        {
            "Критерий": "Персонализация по профилю",
            "Ручной калькулятор": "ограниченно",
            "Rule-based only": "частично",
            "LLM-only": "частично",
            "Разработанная система": "да",
        },
        {
            "Критерий": "История и dashboard",
            "Ручной калькулятор": "редко",
            "Rule-based only": "нет",
            "LLM-only": "редко",
            "Разработанная система": "да",
        },
    ]
    write_markdown_table(path, rows)


def _configure_plot(ax: plt.Axes) -> None:
    ax.set_facecolor("#fffdf9")
    ax.grid(axis="x", color="#d9d0c3", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#b7aa98")
    ax.spines["bottom"].set_color("#b7aa98")


def write_bar_chart(path: Path, title: str, rows: list[dict[str, Any]], value_key: str, unit: str, color: str) -> None:
    titles = [str(row["title"]) for row in rows]
    values = [float(row[value_key]) for row in rows]

    fig, ax = plt.subplots(figsize=(13, 7), dpi=180)
    fig.patch.set_facecolor("#f7f2e9")
    _configure_plot(ax)

    bars = ax.barh(titles, values, color=color, edgecolor="#4b3621", linewidth=0.8)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel(unit, fontsize=12)

    max_value = max(values, default=1) or 1
    ax.set_xlim(0, max_value * 1.18)
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6))

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width() + max_value * 0.015,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.2f} {unit}",
            va="center",
            ha="left",
            fontsize=11,
            color="#2d2116",
            fontweight="bold",
        )

    plt.tight_layout()
    fig.savefig(path, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def write_grouped_compatibility_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    levels = ["high", "medium", "low"]
    labels = {
        "high": "Высокая",
        "medium": "Средняя",
        "low": "Низкая",
    }
    dimensions = [
        ("Совместимость с типом питания", "diet_compatibility"),
        ("Совместимость с ограничениями", "restriction_compatibility"),
        ("Совместимость с целью", "goal_compatibility"),
    ]
    colors = {
        "high": "#497d4e",
        "medium": "#d1a33c",
        "low": "#b5533d",
    }

    counts = {title: Counter(row[key] for row in rows) for title, key in dimensions}
    fig, ax = plt.subplots(figsize=(13, 7), dpi=180)
    fig.patch.set_facecolor("#f7f2e9")
    _configure_plot(ax)

    x_positions = range(len(dimensions))
    width = 0.22
    offsets = [-width, 0, width]

    for offset, level in zip(offsets, levels):
        values = [counts[title].get(level, 0) for title, _ in dimensions]
        bars = ax.bar(
            [x + offset for x in x_positions],
            values,
            width=width,
            label=labels[level],
            color=colors[level],
            edgecolor="#4b3621",
            linewidth=0.8,
        )
        for bar, value in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.05,
                str(value),
                ha="center",
                va="bottom",
                fontsize=11,
                color="#2d2116",
                fontweight="bold",
            )

    ax.set_title("Распределение совместимости по осям", fontsize=18, fontweight="bold", pad=16)
    ax.set_xticks(list(x_positions))
    ax.set_xticklabels([title for title, _ in dimensions], rotation=0, fontsize=11)
    ax.set_ylabel("Количество рецептов", fontsize=12)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(frameon=False, fontsize=11)

    plt.tight_layout()
    fig.savefig(path, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def remove_legacy_svg() -> None:
    for name in (
        "calories_total.svg",
        "calories_per_serving.svg",
        "quality_score.svg",
        "compatibility_distribution.svg",
    ):
        legacy = CHART_DIR / name
        if legacy.exists():
            legacy.unlink()


def write_overview_markdown(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Материалы для раздела 3.2",
        "",
        "Скрипт автоматически собрал метрики и графики по демонстрационным рецептам из `backend/app.db`.",
        "",
        "## Сгенерированные файлы",
        "",
        "- `demo_metrics.json` — полный набор численных метрик по рецептам;",
        "- `demo_metrics.csv` — табличный экспорт;",
        "- `demo_metrics.md` — markdown-таблица для вставки в черновик;",
        "- `comparison_table.md` — сравнительная таблица для 3.2.2;",
        "- `methodology_note.txt` — служебная записка для 3.2.1;",
        "- `comparison_note.txt` — служебная записка для 3.2.2;",
        "- `charts/calories_total.png` — столбчатая диаграмма по калорийности рецептов;",
        "- `charts/quality_score.png` — столбчатая диаграмма по quality score;",
        "- `charts/compatibility_distribution.png` — график распределения compatibility.",
        "",
        "## Демонстрационные кейсы",
        "",
    ]
    for row in rows:
        lines.append(
            f"- **{row['title']}**: {row['calories_total']:.2f} ккал/рецепт, "
            f"{row['calories_per_serving']:.2f} ккал/порция, "
            f"quality {row['quality_score']:.2f}, compatibility "
            f"{row['diet_compatibility']}/{row['restriction_compatibility']}/{row['goal_compatibility']}."
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    analyses = read_analyses()
    rows = flatten_analyses(analyses)
    if not rows:
        raise SystemExit("No analyses found in backend/app.db")

    rows_for_md = [
        {
            "Рецепт": row["title"],
            "Ккал/рецепт": f"{row['calories_total']:.2f}",
            "Ккал/порция": f"{row['calories_per_serving']:.2f}",
            "Quality score": f"{row['quality_score']:.2f}",
            "Matched ratio": f"{row['matched_ratio']:.2f}",
            "Unresolved ratio": f"{row['unresolved_ratio']:.2f}",
            "Тип питания": row["diet_compatibility"],
            "Ограничения": row["restriction_compatibility"],
            "Цель": row["goal_compatibility"],
        }
        for row in rows
    ]

    remove_legacy_svg()
    write_json(REPORT_DIR / "demo_metrics.json", rows)
    write_csv(REPORT_DIR / "demo_metrics.csv", rows)
    write_markdown_table(REPORT_DIR / "demo_metrics.md", rows_for_md)
    write_methodology_note(REPORT_DIR / "methodology_note.txt", rows)
    write_comparison_note(REPORT_DIR / "comparison_note.txt")
    write_comparison_table(REPORT_DIR / "comparison_table.md")
    write_bar_chart(CHART_DIR / "calories_total.png", "Калорийность демонстрационных рецептов", rows, "calories_total", "ккал", "#bd5a3c")
    write_bar_chart(CHART_DIR / "quality_score.png", "Значения quality score по рецептам", rows, "quality_score", "балл", "#4d8451")
    write_grouped_compatibility_chart(CHART_DIR / "compatibility_distribution.png", rows)
    write_overview_markdown(REPORT_DIR / "README.md", rows)
    print(f"Generated thesis artifacts in: {REPORT_DIR}")


if __name__ == "__main__":
    main()
