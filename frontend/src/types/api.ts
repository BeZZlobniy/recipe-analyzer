export type AuthUser = {
  id: number;
  username: string;
  active_profile_id: number | null;
};

export type AuthResponse = {
  user: AuthUser;
};

export type Profile = {
  id: number;
  user_id: number;
  name: string;
  sex: string | null;
  age: number | null;
  weight_kg: number | null;
  height_cm: number | null;
  diet_type: string | null;
  goal: string | null;
  allergies_json: string[];
  diseases_json: string[];
  preferences_json: string[];
  restrictions_text: string | null;
  created_at: string;
  updated_at: string;
};

export type Compatibility = {
  diet: "low" | "medium" | "high";
  restriction: "low" | "medium" | "high";
  goal: "low" | "medium" | "high";
};

export type ProfileAssessmentBlock = {
  key: string;
  title: string;
  status: "ok" | "warning" | "conflict" | "not_applicable" | string;
  compatibility: "low" | "medium" | "high";
  summary: string;
  evidence: string[];
  recommendations: string[];
};

export type ProfileAssessment = {
  goal_alignment: ProfileAssessmentBlock;
  allergy_issues: ProfileAssessmentBlock;
  disease_issues: ProfileAssessmentBlock;
  preference_alignment: ProfileAssessmentBlock;
  additional_restrictions: ProfileAssessmentBlock;
};

export type PortionGuidance = {
  estimated_recipe_servings: number;
  recommended_recipe_servings: number;
  calories_total: number;
  calories_per_recommended_serving: number;
  target_recipe_calories: number | null;
  summary: string | null;
};

export type NutrientMetric = {
  value: number;
  target: number;
  percent_of_target: number;
};

export type DetailedIngredient = {
  ingredient: StructuredIngredient;
  matched_name?: string | null;
  matched_source?: string | null;
  match_method?: string | null;
  match_confidence?: string | null;
  nutrition_source?: string | null;
  nutrition_confidence?: string | null;
  nutrition_resolution_status?: string | null;
  matched_product?: Record<string, unknown> | null;
  estimated_grams?: number | null;
  grams_reason?: string | null;
  used_fallback_grams?: boolean;
  selection_reason?: string | null;
  top_candidates?: Record<string, unknown>[];
  nutrients?: Record<string, number | null>;
};

export type StructuredIngredient = {
  name_raw: string;
  name_canonical: string;
  amount_value: number | null;
  amount_text: string | null;
  unit: string | null;
  form: string | null;
  prep_state: string | null;
  source: string;
  confidence: string;
};

export type StructuredRecipe = {
  title: string;
  servings_declared: string | null;
  ingredients: StructuredIngredient[];
  steps: string[];
  notes: string[];
};

export type AnalyzeResponse = {
  analysis_id: number;
  title: string;
  clean_recipe_text: string;
  structured_recipe: StructuredRecipe;
  matched_ingredients: Record<string, unknown>[];
  nutrition_total: Record<string, NutrientMetric>;
  nutrition_per_serving: Record<string, NutrientMetric>;
  detailed_ingredients: DetailedIngredient[];
  analysis_quality: Record<string, unknown>;
  resolution_stats: Record<string, unknown>;
  unresolved_ingredients: string[];
  rag_context: Record<string, unknown>[];
  summary: string;
  detected_issues: string[];
  recommendations: string[];
  warnings: string[];
  compatibility: Compatibility;
  profile_assessment: ProfileAssessment;
  servings?: number;
  target_recipe_calories?: number | null;
  portion_guidance?: PortionGuidance | null;
};

export type HistoryItem = {
  id: number;
  profile_id: number;
  title: string;
  summary: string | null;
  created_at: string;
  diet_compatibility: string | null;
  restriction_compatibility: string | null;
  goal_compatibility: string | null;
};

export type AnalysisDetail = {
  id: number;
  profile_id: number;
  title: string;
  recipe_text: string;
  structured_recipe: StructuredRecipe;
  analysis_result: AnalyzeResponse;
  summary: string | null;
  created_at: string;
};

export type DashboardData = {
  total_analyses: number;
  average_calories_per_recipe: number;
  average_calories_per_serving: number;
  top_issues: { issue: string; count: number }[];
  compatibility_distribution: Record<string, Record<string, number>>;
  recent_analyses: HistoryItem[];
};
