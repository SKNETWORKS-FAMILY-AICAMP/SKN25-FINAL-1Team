import { marqueeItems } from "../data/landing";

export default function MarqueeSection() {
  const repeated = [...marqueeItems, ...marqueeItems];

  return (
    <section className="border-y border-slate-200 bg-slate-950 py-5">
      <div className="flex overflow-hidden">
        <div className="marquee-track flex min-w-max items-center gap-4">
          {repeated.map((item, index) => (
            <div key={`${item}-${index}`} className="flex items-center gap-4 rounded-full border border-white/10 bg-white/5 px-5 py-3 text-sm font-black text-white">
              <span className="whitespace-nowrap">{item}</span>
              <span className="h-1.5 w-1.5 rounded-full bg-blue-300" />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
