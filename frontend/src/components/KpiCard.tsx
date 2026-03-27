type Props = {
  label: string;
  value: string | number;
};

export function KpiCard({ label, value }: Props) {
  return (
    <div className="card kpi">
      <div className="muted">{label}</div>
      <div className="kpi-value">{value}</div>
    </div>
  );
}

