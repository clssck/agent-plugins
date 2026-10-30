export function Tooltip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="tooltip-anchor">
      {children}
      <span className="tooltip" role="tooltip">{label}</span>
    </span>
  );
}
