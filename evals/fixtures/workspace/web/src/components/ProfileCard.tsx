export function ProfileCard({ user }: { user: { name: string; email: string; avatarUrl?: string; orders: number } }) {
  return (
    <div className="profile-card">
      <img src={user.avatarUrl} alt="" />
      <h3>{user.name}</h3>
      <p>{user.email}</p>
      <span className="badge">{user.orders} orders</span>
    </div>
  );
}
