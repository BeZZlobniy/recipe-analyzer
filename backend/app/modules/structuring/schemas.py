from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic import model_validator


class SimpleRecipeIngredient(BaseModel):
    name: str | None = None
    name_ru: str | None = None
    name_en: str | None = None
    quantity: str | None = None
    quantity_text: str | None = None
    quantity_value: float | None = None
    quantity_unit: str | None = None
    optional: bool = False
    llm_grams: float | None = None
    gram_confidence: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data):
        if not isinstance(data, dict):
            return data
        if not data.get("name") and data.get("name_ru"):
            data["name"] = data["name_ru"]
        if not data.get("name_ru") and data.get("name"):
            data["name_ru"] = data["name"]
        if not data.get("quantity") and data.get("quantity_text"):
            data["quantity"] = data["quantity_text"]
        if not data.get("quantity_text") and data.get("quantity"):
            data["quantity_text"] = data["quantity"]
        return data


class SimpleRecipePayload(BaseModel):
    title: str
    ingredients: list[SimpleRecipeIngredient] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class StructuredIngredient(BaseModel):
    name_raw: str
    name_canonical: str
    name_en: str | None = None
    amount_value: float | None = None
    amount_text: str | None = None
    unit: str | None = None
    llm_grams: float | None = None
    gram_confidence: str | None = None
    form: str | None = None
    prep_state: str | None = None
    source: str = "inferred"
    confidence: str = "medium"


class StructuredRecipe(BaseModel):
    title: str
    servings_declared: str | None = None
    ingredients: list[StructuredIngredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source_recipe_text: str | None = None
