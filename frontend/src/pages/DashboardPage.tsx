import { useEffect, useState } from "react";
import { analysisApi, profilesApi } from "../api";
import { BarList, DonutGroup } from "../components/Charts";
import { StatCard } from "../components/StatCard";
import type { DashboardData, Profile } from "../types/api";
import { formatCompatibilityDimension } from "../utils/labels";

export function DashboardPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [profileId, setProfileId] = useState<number | undefined>(undefined);
  const [data, setData] = useState<DashboardData | null>(null);

  useEffect(() => {
    void profilesApi.list().then((result) => {
      setProfiles(result);
      if (result[0]) {
        setProfileId(result[0].id);
      }
    });
  }, []);

  useEffect(() => {
    void analysisApi.dashboard(profileId).then(setData).catch(() => setData(null));
  }, [profileId]);

  return (
    <div className="page">
      <div className="pageHeader">
        <div>
          <h1>Дашборд</h1>
          <p className="muted">Сводка по анализам и совместимости рецептов.</p>
        </div>
        <select value={profileId ?? ""} onChange={(event) => setProfileId(event.target.value ? Number(event.target.value) : undefined)}>
          <option value="">Все профили</option>
          {profiles.map((profile) => (
            <option key={profile.id} value={profile.id}>
              {profile.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid statsGrid">
        <StatCard label="Всего анализов" value={data?.total_analyses ?? 0} />
        <StatCard label="Среднее ккал / рецепт" value={data?.average_calories_per_recipe ?? 0} />
        <StatCard label="Среднее ккал / порцию" value={data?.average_calories_per_serving ?? 0} />
      </div>

      <div className="grid twoCols">
        <BarList items={(data?.top_issues ?? []).map((item) => ({ label: item.issue, value: item.count }))} />
        <div className="card compatibilityGrid">
          <DonutGroup
            title={formatCompatibilityDimension("diet")}
            values={data?.compatibility_distribution?.diet ?? { high: 0, medium: 0, low: 0 }}
          />
          <DonutGroup
            title={formatCompatibilityDimension("restriction")}
            values={data?.compatibility_distribution?.restriction ?? { high: 0, medium: 0, low: 0 }}
          />
          <DonutGroup
            title={formatCompatibilityDimension("goal")}
            values={data?.compatibility_distribution?.goal ?? { high: 0, medium: 0, low: 0 }}
          />
        </div>
      </div>

      <div className="card">
        <h3>Последние анализы</h3>
        <div className="list">
          {(data?.recent_analyses ?? []).map((item) => (
            <div key={item.id} className="listRow">
              <strong>{item.title}</strong>
              <span className="muted">{new Date(item.created_at).toLocaleString()}</span>
            </div>
          ))}
          {data?.recent_analyses?.length === 0 ? <div className="muted">Анализов пока нет</div> : null}
        </div>
      </div>
    </div>
  );
}
