import { useState } from "react";

export function Header() {
  const [open, setOpen] = useState(false);
  return (
    <header className="header">
      <button onClick={() => setOpen((o) => !o)}>Account</button>
      {open && (
        <ul className="dropdown" role="menu">
          <li role="menuitem">Profile</li>
          <li role="menuitem">Billing</li>
          <li role="menuitem">Sign out</li>
        </ul>
      )}
    </header>
  );
}
