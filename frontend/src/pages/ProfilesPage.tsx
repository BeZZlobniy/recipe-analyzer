import { useEffect, useMemo, useState } from "react";
import { profilesApi } from "../api";
import type { Profile } from "../types/api";
import { useAuth } from "../features/auth/AuthContext";

type ProfileFormState = {
  name: string;
  sex: string;
  age: number;
  weight_kg: number;
  height_cm: number;
  diet_type: string;
  goal: string;
  allergies_text: string;
  diseases_text: string;
  preferences_text: string;
  restrictions_text: string;
};

const emptyProfile: ProfileFormState = {
  name: "",
  sex: "female",
  age: 30,
  weight_kg: 70,
  height_cm: 170,
  diet_type: "balanced",
  goal: "maintenance",
  allergies_text: "",
  diseases_text: "",
  preferences_text: "",
  restrictions_text: "",
};

export function ProfilesPage() {
  const { user, refresh } = useAuth();
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [form, setForm] = useState<ProfileFormState>(emptyProfile);
  const [editingId, setEditingId] = useState<number | null>(null);

  const loadProfiles = async () => {
    const result = await profilesApi.list();
    setProfiles(result);
  };

  useEffect(() => {
    void loadProfiles();
  }, []);

  const activeProfileId = user?.active_profile_id ?? null;
  const submitLabel = useMemo(() => (editingId ? "Сохранить профиль" : "Создать профиль"), [editingId]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const payload = {
      name: form.name,
      sex: form.sex,
      age: form.age,
      weight_kg: form.weight_kg,
      height_cm: form.height_cm,
      diet_type: form.diet_type,
      goal: form.goal,
      allergies_json: splitText(form.allergies_text),
      diseases_json: splitText(form.diseases_text),
      preferences_json: splitText(form.preferences_text),
      restrictions_text: form.restrictions_text,
    };

    if (editingId) {
      await profilesApi.update(editingId, payload);
    } else {
      await profilesApi.create(payload);
    }

    setForm(emptyProfile);
    setEditingId(null);
    await loadProfiles();
    await refresh();
  };

  const startEdit = (profile: Profile) => {
    setEditingId(profile.id);
    setForm({
      name: profile.name,
      sex: profile.sex ?? "female",
      age: profile.age ?? 30,
      weight_kg: profile.weight_kg ?? 70,
      height_cm: profile.height_cm ?? 170,
      diet_type: profile.diet_type ?? "balanced",
      goal: profile.goal ?? "maintenance",
      allergies_text: stringifyText(profile.allergies_json),
      diseases_text: stringifyText(profile.diseases_json),
      preferences_text: stringifyText(profile.preferences_json),
      restrictions_text: profile.restrictions_text ?? "",
    });
  };

  return (
    <div className="page">
      <h1>Профили</h1>
      <div className="grid twoCols">
        <div className="card">
          <h3>{editingId ? "Редактирование профиля" : "Создание профиля"}</h3>
          <form className="formGrid" onSubmit={handleSubmit}>
            <label>Название профиля<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label>
            <label>Пол<select value={form.sex} onChange={(event) => setForm({ ...form, sex: event.target.value })}><option value="female">Женский</option><option value="male">Мужской</option></select></label>
            <label>Возраст<input type="number" value={form.age} onChange={(event) => setForm({ ...form, age: Number(event.target.value) })} /></label>
            <label>Вес<input type="number" value={form.weight_kg} onChange={(event) => setForm({ ...form, weight_kg: Number(event.target.value) })} /></label>
            <label>Рост<input type="number" value={form.height_cm} onChange={(event) => setForm({ ...form, height_cm: Number(event.target.value) })} /></label>
            <label>Тип питания<input value={form.diet_type} onChange={(event) => setForm({ ...form, diet_type: event.target.value })} /></label>
            <label>Цель<input value={form.goal} onChange={(event) => setForm({ ...form, goal: event.target.value })} /></label>
            <label>Аллергии<textarea value={form.allergies_text} onChange={(event) => setForm({ ...form, allergies_text: event.target.value })} /></label>
            <label>Заболевания<textarea value={form.diseases_text} onChange={(event) => setForm({ ...form, diseases_text: event.target.value })} /></label>
            <label>Предпочтения<textarea value={form.preferences_text} onChange={(event) => setForm({ ...form, preferences_text: event.target.value })} /></label>
            <label className="fullWidth">Ограничения<textarea value={form.restrictions_text} onChange={(event) => setForm({ ...form, restrictions_text: event.target.value })} /></label>
            <button type="submit">{submitLabel}</button>
          </form>
        </div>

        <div className="card">
          <h3>Сохраненные профили</h3>
          <div className="list">
            {profiles.map((profile) => (
              <div key={profile.id} className="listCard">
                <div>
                  <strong>{profile.name}</strong>
                  {activeProfileId === profile.id ? <span className="pill good">активный</span> : null}
                </div>
                <div className="muted">{profile.diet_type ?? "тип питания не задан"} / {profile.goal ?? "цель не задана"}</div>
                <div className="actions">
                  <button className="ghostButton" onClick={() => void profilesApi.select(profile.id).then(refresh).then(loadProfiles)}>Выбрать</button>
                  <button className="ghostButton" onClick={() => startEdit(profile)}>Изменить</button>
                  <button className="ghostButton danger" onClick={() => void profilesApi.remove(profile.id).then(loadProfiles).then(refresh)}>Удалить</button>
                </div>
              </div>
            ))}
            {profiles.length === 0 ? <div className="muted">Профилей пока нет</div> : null}
          </div>
        </div>
      </div>
    </div>
  );
}

function splitText(value: string) {
  return value
    .split(/[,\n;]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function stringifyText(value: string[] | string) {
  return Array.isArray(value) ? value.join(", ") : value;
}
