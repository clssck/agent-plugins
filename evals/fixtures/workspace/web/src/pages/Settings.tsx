export function Settings() {
  return (
    <div className="settings-dialog">
      <h2>Settings</h2>
      <label>Store name <input /></label>
      <label>Currency <select><option>USD</option><option>EUR</option></select></label>
      <button>Save</button>
    </div>
  );
}
