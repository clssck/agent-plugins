import { useEffect, useState } from "react";

export function Carousel({ slides }: { slides: string[] }) {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setIndex((i) => (i + 1) % slides.length), 4000);
    return () => clearInterval(id);
  }, [slides.length]);
  return (
    <div className="carousel">
      <div className="track" style={{ left: `-${index * 100}%` }}>
        {slides.map((src) => <img key={src} src={src} alt="" />)}
      </div>
    </div>
  );
}
