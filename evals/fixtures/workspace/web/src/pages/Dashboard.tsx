import { Carousel } from "../components/Carousel";

export function Dashboard() {
  return (
    <main className="dashboard">
      <section className="stats"><div>Orders today: 412</div><div>Revenue: $18,240</div></section>
      <Carousel slides={["/promo-1.png", "/promo-2.png"]} />
    </main>
  );
}
