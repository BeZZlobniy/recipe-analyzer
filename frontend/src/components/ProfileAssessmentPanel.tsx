import type { ProfileAssessment, ProfileAssessmentBlock } from "../types/api";
import { uniqueTextList } from "../utils/text";

const BLOCK_ORDER: (keyof ProfileAssessment)[] = [
  "goal_alignment",
  "allergy_issues",
  "disease_issues",
  "preference_alignment",
  "additional_restrictions",
];

const STATUS_LABELS: Record<string, string> = {
  ok: "Подходит",
  warning: "Есть нюансы",
  conflict: "Конфликт",
  not_applicable: "Не указано",
};

export function ProfileAssessmentPanel({ assessment }: { assessment: ProfileAssessment }) {
  const blocks = BLOCK_ORDER.map((key) => assessment[key]).filter(Boolean);

  return (
    <section className="card">
      <div className="rowBetween">
        <h3>Профильная оценка</h3>
        <span className="muted small">цель, аллергии, заболевания, предпочтения и ограничения</span>
      </div>
      <div className="assessmentGrid">
        {blocks.map((block) => (
          <AssessmentCard key={block.key} block={block} />
        ))}
      </div>
    </section>
  );
}

function AssessmentCard({ block }: { block: ProfileAssessmentBlock }) {
  const evidence = uniqueTextList(block.evidence).filter((item) => !block.summary.includes(item));
  const recommendations = uniqueTextList(block.recommendations);

  return (
    <article className={`assessmentCard ${block.status}`}>
      <div className="assessmentHeader">
        <h4>{block.title}</h4>
        <span className={`statusBadge ${block.status}`}>{STATUS_LABELS[block.status] ?? block.status}</span>
      </div>
      <p>{block.summary}</p>
      {evidence.length > 0 ? (
        <>
          <strong>Что найдено</strong>
          <ul>
            {evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
      {recommendations.length > 0 ? (
        <>
          <strong>Что сделать</strong>
          <ul>
            {recommendations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      ) : null}
    </article>
  );
}
