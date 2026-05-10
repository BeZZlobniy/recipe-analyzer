from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
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
    rows = con.execute(
        """
        SELECT
            ra.id,
            ra.title,
            ra.summary,
            ra.diet_compatibility,
            ra.restriction_compatibility,
            ra.goal_compatibility,
            ra.analysis_result_json,
            ra.profile_id,
            up.name AS profile_name,
            up.diet_type,
            up.goal
        FROM recipe_analyses ra
        JOIN user_profiles up ON up.id = ra.profile_id
        ORDER BY ra.id
        """
    ).fetchall()
    con.close()

    analyses: list[dict[str, Any]] = []
    for row in rows:
        payload = row["analysis_result_json"]
        result = json.loads(payload) if isinstance(payload, str) else payload
        result = result or {}
        analyses.append(
            {
                "id": row["id"],
                "profile_id": row["profile_id"],
                "profile": row["profile_name"],
                "diet_type": row["diet_type"],
                "goal": row["goal"],
                "title": row["title"],
                "summary": row["summary"],
                "diet_compatibility": row["diet_compatibility"] or (result.get("compatibility") or {}).get("diet"),
                "restriction_compatibility": row["restriction_compatibility"] or (result.get("compatibility") or {}).get("restriction"),
                "goal_compatibility": row["goal_compatibility"] or (result.get("compatibility") or {}).get("goal"),
                "result": result,
            }
        )
    return analyses


def metric(result: dict[str, Any], group: str, key: str) -> float:
    return float(((result.get(group) or {}).get(key) or {}).get("value") or 0)


def flatten(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in analyses:
        result = item["result"]
        quality = result.get("analysis_quality") or {}
        detailed = result.get("detailed_ingredients") or []
        structured = (result.get("structured_recipe") or {}).get("ingredients") or []
        rows.append(
            {
                "analysis_id": item["id"],
                "profile": item["profile"],
                "diet_type": item["diet_type"],
                "goal": item["goal"],
                "recipe": item["title"],
                "ingredients": len(structured),
                "llm_ingredients": sum(1 for ing in structured if isinstance(ing, dict) and ing.get("source") == "llm_normalized"),
                "heuristic_ingredients": sum(1 for ing in structured if isinstance(ing, dict) and ing.get("source") == "heuristic_fallback"),
                "fallback_grams": sum(1 for detail in detailed if isinstance(detail, dict) and detail.get("used_fallback_grams")),
                "unresolved": len(result.get("unresolved_ingredients") or []),
                "rag_context": len(result.get("rag_context") or []),
                "quality_score": float(quality.get("score") or 0),
                "matched_ratio": float(quality.get("matched_ratio") or 0),
                "trusted_nutrition_ratio": float(quality.get("trusted_nutrition_ratio") or 0),
                "explicit_amount_ratio": float(quality.get("explicit_amount_ratio") or 0),
                "calories_total": metric(result, "nutrition_total", "calories"),
                "calories_per_serving": metric(result, "nutrition_per_serving", "calories"),
                "protein_per_serving": metric(result, "nutrition_per_serving", "protein"),
                "fat_per_serving": metric(result, "nutrition_per_serving", "fat"),
                "carbs_per_serving": metric(result, "nutrition_per_serving", "carbs"),
                "sodium_per_serving": metric(result, "nutrition_per_serving", "sodium"),
                "recommended_servings": (result.get("portion_guidance") or {}).get("recommended_recipe_servings") or result.get("servings") or 1,
                "diet_compatibility": item["diet_compatibility"] or "unknown",
                "restriction_compatibility": item["restriction_compatibility"] or "unknown",
                "goal_compatibility": item["goal_compatibility"] or "unknown",
                "issues": result.get("detected_issues") or [],
                "recommendations": result.get("recommendations") or [],
            }
        )
    return rows


def avg(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def pct(part: int, total: int) -> str:
    return f"{round(part / max(total, 1) * 100, 1)}%"


def group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return dict(grouped)


def summary_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_ingredients = sum(int(row["ingredients"]) for row in rows)
    heuristic = sum(int(row["heuristic_ingredients"]) for row in rows)
    fallback_grams = sum(int(row["fallback_grams"]) for row in rows)
    unresolved = sum(int(row["unresolved"]) for row in rows)
    return [
        {"Показатель": "Количество анализов", "Значение": len(rows)},
        {"Показатель": "Уникальные рецепты", "Значение": len({row["recipe"] for row in rows})},
        {"Показатель": "Профили пользователей", "Значение": len({row["profile"] for row in rows})},
        {"Показатель": "Всего ингредиентов", "Значение": total_ingredients},
        {"Показатель": "LLM-normalized ingredients", "Значение": pct(total_ingredients - heuristic, total_ingredients)},
        {"Показатель": "Heuristic fallback ingredients", "Значение": pct(heuristic, total_ingredients)},
        {"Показатель": "Fallback grams", "Значение": pct(fallback_grams, total_ingredients)},
        {"Показатель": "Unresolved ingredients", "Значение": pct(unresolved, total_ingredients)},
        {"Показатель": "Средний RAG context", "Значение": avg([float(row["rag_context"]) for row in rows])},
        {"Показатель": "Средний quality score", "Значение": avg([float(row["quality_score"]) for row in rows])},
    ]


def profile_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    for profile, items in group_by(rows, "profile").items():
        low_diet = sum(1 for row in items if row["diet_compatibility"] == "low")
        low_restriction = sum(1 for row in items if row["restriction_compatibility"] == "low")
        low_goal = sum(1 for row in items if row["goal_compatibility"] == "low")
        table.append(
            {
                "Профиль": profile,
                "Анализов": len(items),
                "Средний quality": avg([float(row["quality_score"]) for row in items]),
                "Средние ккал/порция": avg([float(row["calories_per_serving"]) for row in items]),
                "Diet low": low_diet,
                "Restrictions low": low_restriction,
                "Goal low": low_goal,
            }
        )
    return table


def recipe_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    for recipe, items in group_by(rows, "recipe").items():
        table.append(
            {
                "Рецепт": recipe,
                "Анализов": len(items),
                "Ингредиентов": int(items[0]["ingredients"]),
                "Средний quality": avg([float(row["quality_score"]) for row in items]),
                "Ккал/порция": avg([float(row["calories_per_serving"]) for row in items]),
                "Fallback grams": int(items[0]["fallback_grams"]),
                "Unresolved": int(items[0]["unresolved"]),
            }
        )
    return table


def compatibility_table(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table: list[dict[str, Any]] = []
    dimensions = [
        ("Тип питания", "diet_compatibility"),
        ("Ограничения/аллергии", "restriction_compatibility"),
        ("Цель", "goal_compatibility"),
    ]
    for label, key in dimensions:
        counts = Counter(row[key] for row in rows)
        table.append(
            {
                "Ось совместимости": label,
                "High": counts.get("high", 0),
                "Medium": counts.get("medium", 0),
                "Low": counts.get("low", 0),
            }
        )
    return table


def issue_table(rows: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for issue in row["issues"]:
            text = str(issue).strip()
            if text and "явных конфликтов" not in text.lower():
                counter[text] += 1
    return [{"Проблема": issue, "Количество": count} for issue, count in counter.most_common(limit)]


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
        path.write_text("", encoding="utf-8")
        return
    headers = list(rows[0].keys())
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row[header]).replace("|", "/") for header in headers) + " |")
    path.write_text("\n".join(lines), encoding="utf-8")


def chart_style(ax: plt.Axes) -> None:
    ax.set_facecolor("#fffdf9")
    ax.grid(axis="x", color="#d9d0c3", linewidth=0.8, alpha=0.8)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#b7aa98")
    ax.spines["bottom"].set_color("#b7aa98")


def save_barh(path: Path, title: str, labels: list[str], values: list[float], unit: str, color: str) -> None:
    fig, ax = plt.subplots(figsize=(14, max(7, len(labels) * 0.35)), dpi=180)
    fig.patch.set_facecolor("#f7f2e9")
    chart_style(ax)
    bars = ax.barh(labels, values, color=color, edgecolor="#4b3621", linewidth=0.7)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=17, fontweight="bold", pad=14)
    ax.set_xlabel(unit)
    max_value = max(values, default=1) or 1
    ax.set_xlim(0, max_value * 1.2)
    for bar, value in zip(bars, values):
        ax.text(bar.get_width() + max_value * 0.015, bar.get_y() + bar.get_height() / 2, f"{value:.2f}", va="center", fontsize=9)
    plt.tight_layout()
    fig.savefig(path, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_compatibility_chart(path: Path, rows: list[dict[str, Any]]) -> None:
    table = compatibility_table(rows)
    levels = ["High", "Medium", "Low"]
    colors = {"High": "#497d4e", "Medium": "#d1a33c", "Low": "#b5533d"}
    x = list(range(len(table)))
    width = 0.23
    offsets = [-width, 0, width]
    fig, ax = plt.subplots(figsize=(12, 6), dpi=180)
    fig.patch.set_facecolor("#f7f2e9")
    chart_style(ax)
    for offset, level in zip(offsets, levels):
        values = [int(row[level]) for row in table]
        bars = ax.bar([pos + offset for pos in x], values, width=width, label=level, color=colors[level], edgecolor="#4b3621", linewidth=0.7)
        for bar, value in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.2, str(value), ha="center", fontsize=10)
    ax.set_title("Распределение совместимости по 100 анализам", fontsize=17, fontweight="bold", pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels([row["Ось совместимости"] for row in table])
    ax.set_ylabel("Количество анализов")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(frameon=False)
    plt.tight_layout()
    fig.savefig(path, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def save_profile_quality_chart(path: Path, table: list[dict[str, Any]]) -> None:
    save_barh(
        path,
        "Средний quality score по профилям",
        [row["Профиль"] for row in table],
        [float(row["Средний quality"]) for row in table],
        "баллы",
        "#4d8451",
    )


def write_notes(rows: list[dict[str, Any]], tables: dict[str, list[dict[str, Any]]]) -> None:
    text = f"""Комплексная статистика демонстрационного прогона

Объем выборки: {len(rows)} анализов ({len({row['recipe'] for row in rows})} рецептов × {len({row['profile'] for row in rows})} профилей).

Ключевые показатели:
- средний quality score: {avg([float(row['quality_score']) for row in rows])};
- средний RAG context: {avg([float(row['rag_context']) for row in rows])};
- доля heuristic fallback ingredients: {tables['summary'][5]['Значение']};
- доля unresolved ingredients: {tables['summary'][7]['Значение']};
- средняя калорийность на порцию: {avg([float(row['calories_per_serving']) for row in rows])} ккал.

Материалы для вставки в диплом:
- `tables/summary.md` — общая сводка;
- `tables/by_profile.md` — качество и конфликты по профилям;
- `tables/by_recipe.md` — качество и нутриентная устойчивость по рецептам;
- `tables/compatibility.md` — распределение совместимости;
- `tables/top_issues.md` — наиболее частые проблемы;
- `charts/*.png` — графики для раздела с экспериментальной проверкой.
"""
    (REPORT_DIR / "README.md").write_text(text, encoding="utf-8")


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    table_dir = REPORT_DIR / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)

    analyses = read_analyses()
    rows = flatten(analyses)
    if not rows:
        raise SystemExit("No analyses found in backend/app.db")

    tables = {
        "summary": summary_table(rows),
        "by_profile": profile_table(rows),
        "by_recipe": recipe_table(rows),
        "compatibility": compatibility_table(rows),
        "top_issues": issue_table(rows),
    }

    write_json(REPORT_DIR / "analysis_metrics.json", rows)
    write_csv(REPORT_DIR / "analysis_metrics.csv", rows)
    for name, table in tables.items():
        write_csv(table_dir / f"{name}.csv", table)
        write_markdown_table(table_dir / f"{name}.md", table)

    recipe_rows = tables["by_recipe"]
    save_barh(
        CHART_DIR / "calories_per_serving_by_recipe.png",
        "Средняя калорийность на порцию по рецептам",
        [row["Рецепт"] for row in recipe_rows],
        [float(row["Ккал/порция"]) for row in recipe_rows],
        "ккал",
        "#bd5a3c",
    )
    save_barh(
        CHART_DIR / "quality_by_recipe.png",
        "Средний quality score по рецептам",
        [row["Рецепт"] for row in recipe_rows],
        [float(row["Средний quality"]) for row in recipe_rows],
        "баллы",
        "#4d8451",
    )
    save_profile_quality_chart(CHART_DIR / "quality_by_profile.png", tables["by_profile"])
    save_compatibility_chart(CHART_DIR / "compatibility_distribution.png", rows)
    write_notes(rows, tables)
    print(f"Generated thesis artifacts in: {REPORT_DIR}")


if __name__ == "__main__":
    main()
