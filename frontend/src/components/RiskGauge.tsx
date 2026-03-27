import { PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer } from "recharts";

type Props = {
  score: number;
};

function colorForScore(score: number) {
  if (score > 200) return "#dc2626";
  if (score >= 100) return "#f59e0b";
  return "#16a34a";
}

export function RiskGauge({ score }: Props) {
  const bounded = Math.max(0, Math.min(300, score));
  const color = colorForScore(bounded);

  return (
    <div className="card gauge-card">
      <div className="card-title">Risk Score</div>
      <div className="gauge-wrap">
        <ResponsiveContainer width="100%" height={260}>
          <RadialBarChart innerRadius="65%" outerRadius="95%" data={[{ value: bounded }]} startAngle={210} endAngle={-30}>
            <PolarAngleAxis type="number" domain={[0, 300]} angleAxisId={0} tick={false} />
            <RadialBar dataKey="value" cornerRadius={10} fill={color} background />
          </RadialBarChart>
        </ResponsiveContainer>
        <div className="gauge-center">
          <div className="gauge-score">{bounded}</div>
          <div className="muted">0 - 300</div>
        </div>
      </div>
      <div className="legend">
        <span>Green &lt; 100</span>
        <span>Amber 100 - 200</span>
        <span>Red &gt; 200</span>
      </div>
    </div>
  );
}

