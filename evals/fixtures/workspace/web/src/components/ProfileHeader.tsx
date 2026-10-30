export function ProfileHeader({ name, title }: { name: string; title: string }) {
  return (
    <div className="profile-header">
      <h1>{name}</h1>
      <span>{title}</span>
    </div>
  );
}
