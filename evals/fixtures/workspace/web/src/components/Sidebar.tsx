export function Sidebar({ open = false }: { open?: boolean }) {
  return (
    <nav className={open ? "sidebar sidebar-open" : "sidebar"}>
      <a href="/orders">Orders</a>
      <a href="/customers">Customers</a>
      <a href="/settings">Settings</a>
    </nav>
  );
}
