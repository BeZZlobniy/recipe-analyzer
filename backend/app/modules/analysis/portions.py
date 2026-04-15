from __future__ import annotations

import re

from app.modules.structuring.schemas import StructuredRecipe


class PortionService:
    def estimate_servings(self, recipe: StructuredRecipe, profile: dict) -> int:
        if recipe.servings_declared:
            if re.search(r"[-–]", recipe.servings_declared):
                left, right = re.split(r"[-–]", recipe.servings_declared, maxsplit=1)
                return max(1, int((int(left) + int(right)) / 2))
            if recipe.servings_declared.isdigit():
                return max(1, int(recipe.servings_declared))
        return max(int(profile.get("servings") or 4), 1)


portion_service = PortionService()
