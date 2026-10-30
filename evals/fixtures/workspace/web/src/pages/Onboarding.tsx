export function Onboarding({ step }: { step: number }) {
  return (
    <div className="onboarding">
      <p>Step {step} of 3</p>
      {step === 1 && <h2>Connect your store</h2>}
      {step === 2 && <h2>Import products</h2>}
      {step === 3 && <h2>You're all set</h2>}
    </div>
  );
}
