export function Drawer({ open, children }: { open: boolean; children: React.ReactNode }) {
  return <aside className={open ? "drawer drawer-open" : "drawer"}>{children}</aside>;
}
