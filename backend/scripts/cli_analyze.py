from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
USER_PROFILES_DIR = ROOT_DIR / "user_profiles"
REPORTS_DIR = ROOT_DIR / "reports"
SAMPLE_PROFILE_NAME = "sample_user.json"


def maybe_fix_mojibake(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value
    if not text:
        return text
    markers = ("Р", "С", "вЂ", "Ñ", "Ð")
    if not any(m in text for m in markers):
        return text
    try:
        fixed = text.encode("cp1251").decode("utf-8")
    except Exception:
        return text
    return fixed if sum(ch.isalpha() for ch in fixed) >= sum(ch.isalpha() for ch in text) * 0.6 else text


def normalize_text(value: Any) -> str:
    fixed = maybe_fix_mojibake(value)
    return " ".join(str(fixed or "").strip().lower().split())


def read_recipe_from_stdin() -> str:
    print("Paste recipe text (multi-line). Finish with END on a separate line:", file=sys.stderr)
    lines: List[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def list_profiles() -> List[str]:
    USER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.name for p in USER_PROFILES_DIR.glob("*.json"))


def load_profile_file(filename: str) -> Dict[str, Any]:
    path = USER_PROFILES_DIR / filename
    if not path.exists():
        raise SystemExit(f"Profile file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        profile = json.load(f)
    if not isinstance(profile, dict):
        raise SystemExit("Profile JSON must be an object")
    return profile


def choose_profile_interactive() -> Dict[str, Any]:
    print("Choose profile mode:")
    print("1) Use sample profile")
    print("2) Load profile from user_profiles by file name")
    mode = input("Enter 1 or 2: ").strip()

    if mode == "1":
        return load_profile_file(SAMPLE_PROFILE_NAME)
    if mode == "2":
        existing = list_profiles()
        if existing:
            print("Available profile files:")
            for name in existing:
                print(f"- {name}")
        filename = input("Enter profile filename (e.g. sample_user.json): ").strip()
        return load_profile_file(filename)
    raise SystemExit("Invalid mode. Use 1 or 2.")


def split_restrictions(profile: Dict[str, Any], cli_restrictions: List[str]) -> tuple[Dict[str, Any], List[str]]:
    restrictions = [r.strip() for r in cli_restrictions if r and r.strip()]
    profile_copy = dict(profile)
    from_profile = profile_copy.pop("user_restrictions", [])
    if isinstance(from_profile, list):
        restrictions.extend(str(r).strip() for r in from_profile if str(r).strip())

    unique: List[str] = []
    seen = set()
    for item in restrictions:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return profile_copy, unique


def nutrient_line(name: str, key: str, payload: Dict[str, Any]) -> str:
    data = payload.get(key, {}) if isinstance(payload, dict) else {}
    value = data.get("value", 0)
    target = data.get("target", 0)
    pct = data.get("percent_of_target", 0)
    return f"- {name}: {value} (target: {target}, {pct}%)"


def deep_fix_mojibake(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: deep_fix_mojibake(v) for k, v in value.items()}
    if isinstance(value, list):
        return [deep_fix_mojibake(v) for v in value]
    if isinstance(value, str):
        return maybe_fix_mojibake(value)
    return value


def filter_report_ingredients(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bad_tokens = ("добавить", "варить", "тушить", "ингредиенты", "приготовление", "подача", "советы")
    out: List[Dict[str, Any]] = []
    for item in items:
        name = str(item.get("name", "")).strip()
        name_norm = normalize_text(name)
        if not name_norm:
            continue
        if any(token in name_norm for token in bad_tokens):
            continue
        if len(name_norm.split()) > 4:
            continue
        out.append(item)
    return out


def render_report_markdown(
    result: Dict[str, Any],
    user_profile: Dict[str, Any],
    restrictions: List[str],
    recipe_text: str,
) -> str:
    result = deep_fix_mojibake(result)
    user_profile = deep_fix_mojibake(user_profile)
    restrictions = [str(deep_fix_mojibake(x)) for x in restrictions]
    recipe_text = str(deep_fix_mojibake(recipe_text))

    summary = str(result.get("summary") or "-")
    servings = result.get("servings", "-")
    serving_reason = result.get("serving_estimation_reason") or "-"
    serving_confidence = result.get("serving_confidence") or "-"
    suggested_range = result.get("suggested_servings_range") or "-"
    portion_advice = result.get("portion_advice") or "-"

    detected_issues = result.get("detected_issues", []) or []
    recommendations = result.get("recommendations", []) or []
    warnings = result.get("warnings", []) or []
    notes = result.get("notes", []) or []
    ingredients = filter_report_ingredients(result.get("normalized_ingredients", []) or [])
    rag_context = result.get("rag_context", []) or []

    lines: List[str] = [
        "# Recipe Analysis Report",
        "",
        "## User Profile",
        f"- Profile: `{json.dumps(user_profile, ensure_ascii=False)}`",
        f"- Restrictions: {', '.join(restrictions) if restrictions else '-'}",
        "",
        "## Summary",
        f"- {summary}",
        f"- Compatibility: diet={result.get('diet_compatibility')}, restriction={result.get('restriction_compatibility')}, goal={result.get('goal_compatibility')}",
        "",
        "## Servings",
        f"- Estimated servings: {servings}",
        f"- Suggested range: {suggested_range}",
        f"- Confidence: {serving_confidence}",
        f"- Reason: {serving_reason}",
        f"- Portion advice: {portion_advice}",
        "",
        "## Nutrition Total",
        nutrient_line("Calories", "calories", result.get("nutrition_total", {})),
        nutrient_line("Protein", "protein", result.get("nutrition_total", {})),
        nutrient_line("Fat", "fat", result.get("nutrition_total", {})),
        nutrient_line("Carbs", "carbs", result.get("nutrition_total", {})),
        nutrient_line("Fiber", "fiber", result.get("nutrition_total", {})),
        nutrient_line("Sodium", "sodium", result.get("nutrition_total", {})),
        "",
        "## Nutrition Per Serving",
        nutrient_line("Calories", "calories", result.get("nutrition_per_serving", {})),
        nutrient_line("Protein", "protein", result.get("nutrition_per_serving", {})),
        nutrient_line("Fat", "fat", result.get("nutrition_per_serving", {})),
        nutrient_line("Carbs", "carbs", result.get("nutrition_per_serving", {})),
        nutrient_line("Fiber", "fiber", result.get("nutrition_per_serving", {})),
        nutrient_line("Sodium", "sodium", result.get("nutrition_per_serving", {})),
        "",
        "## Normalized Ingredients",
    ]

    if ingredients:
        for item in ingredients:
            name = item.get("name")
            amount = item.get("amount")
            unit = item.get("unit")
            lines.append(f"- {name}: {amount if amount is not None else '-'} {unit if unit else ''}".rstrip())
    else:
        lines.append("- -")

    lines.extend(["", "## Detected Issues"])
    lines.extend([f"- {x}" for x in detected_issues] if detected_issues else ["- -"])

    lines.extend(["", "## Recommendations"])
    lines.extend([f"- {x}" for x in recommendations] if recommendations else ["- -"])

    lines.extend(["", "## Warnings"])
    if warnings:
        for x in warnings[:12]:
            lines.append(f"- {x}")
        if len(warnings) > 12:
            lines.append(f"- ... and {len(warnings) - 12} more warnings")
    else:
        lines.append("- -")

    lines.extend(["", "## Notes"])
    lines.extend([f"- {x}" for x in notes] if notes else ["- -"])

    lines.extend(["", "## RAG Context (Top 5)"])
    if rag_context:
        for item in rag_context[:5]:
            source = item.get("source", "unknown")
            text = str(item.get("text", "")).strip()
            if len(text) > 240:
                text = text[:240] + "..."
            score = item.get("score")
            lines.append(f"- [{source}] ({score}) {text}")
    else:
        lines.append("- -")

    lines.extend(["", "## Original Recipe Text", recipe_text or "-", ""])
    return "\n".join(lines)


def markdown_to_plain(markdown: str) -> str:
    out: List[str] = []
    for line in markdown.splitlines():
        out.append(line.replace("# ", "").replace("## ", "").replace("`", ""))
    return "\n".join(out)


def save_human_report(
    result: Dict[str, Any],
    user_profile: Dict[str, Any],
    restrictions: List[str],
    recipe_text: str,
    report_format: str = "txt",
    filename: str | None = None,
) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    extension = "md" if report_format == "md" else "txt"
    if filename:
        report_name = filename if filename.lower().endswith(f".{extension}") else f"{filename}.{extension}"
    else:
        report_name = f"analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extension}"

    content = render_report_markdown(result, user_profile, restrictions, recipe_text)
    if extension == "txt":
        content = markdown_to_plain(content)

    report_path = REPORTS_DIR / report_name
    report_path.write_text(content, encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive CLI for /analyze")
    parser.add_argument("--url", default="http://localhost:8000/analyze")
    parser.add_argument("--timeout", type=int, default=600, help="HTTP timeout in seconds")
    parser.add_argument("-r", "--restriction", action="append", default=[])
    parser.add_argument("--profile-file", type=str, help="Profile JSON filename in user_profiles/")
    parser.add_argument("--save-report", action="store_true", help="Save human-readable report to backend/reports")
    parser.add_argument("--report-file", type=str, help="Custom report filename")
    parser.add_argument("--report-format", choices=["txt", "md"], default="txt")
    args = parser.parse_args()

    profile_raw = load_profile_file(args.profile_file) if args.profile_file else choose_profile_interactive()
    user_profile, restrictions = split_restrictions(profile_raw, args.restriction or [])

    recipe_text = read_recipe_from_stdin()
    if not recipe_text:
        raise SystemExit("Recipe text is empty.")

    payload = {
        "recipe_text": recipe_text,
        "user_restrictions": restrictions,
        "user_profile": user_profile,
    }

    try:
        resp = requests.post(args.url, json=payload, timeout=args.timeout)
        resp.raise_for_status()
        result = deep_fix_mojibake(resp.json())
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if args.save_report:
            path = save_human_report(
                result=result,
                user_profile=user_profile,
                restrictions=restrictions,
                recipe_text=recipe_text,
                report_format=args.report_format,
                filename=args.report_file,
            )
            print(f"\nReport saved: {path}")
    except requests.HTTPError:
        body = resp.text if "resp" in locals() else ""
        raise SystemExit(f"HTTP error: {body}")
    except requests.RequestException as exc:
        raise SystemExit(f"Request error: {exc}")


if __name__ == "__main__":
    main()
