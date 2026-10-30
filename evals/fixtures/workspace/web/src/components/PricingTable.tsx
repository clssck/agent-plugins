const plans = [
  { name: "Starter", price: 9, features: ["1 store", "Email support"] },
  { name: "Growth", price: 49, features: ["5 stores", "Priority support"] },
  { name: "Enterprise", price: 299, features: ["Unlimited stores", "SSO", "SLA"] },
];

export function PricingTable() {
  return (
    <div className="pricing">
      {plans.map((plan) => (
        <div className="plan" key={plan.name}>
          <h3>{plan.name}</h3>
          <strong>${plan.price}/mo</strong>
          <ul>{plan.features.map((f) => <li key={f}>{f}</li>)}</ul>
        </div>
      ))}
    </div>
  );
}
