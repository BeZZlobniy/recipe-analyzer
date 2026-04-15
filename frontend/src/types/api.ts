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
  structured_recipe: StructuredRecipe;
  matched_ingredients: Record<string, unknown>[];
  nutrition_total: Record<string, { value: number; target: number; percent_of_target: number }>;
  nutrition_per_serving: Record<string, { value: number; target: number; percent_of_target: number }>;
  detailed_ingredients: Record<string, unknown>[];
  rag_context: Record<string, unknown>[];
  summary: string;
  detected_issues: string[];
  recommendations: string[];
  warnings: string[];
  compatibility: Compatibility;
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
