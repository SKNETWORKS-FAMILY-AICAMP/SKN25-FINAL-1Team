import Footer from "./components/layout/Footer";
import Header from "./components/layout/Header";
import ContactSection from "./sections/ContactSection";
import DashboardSection from "./sections/DashboardSection";
import HeroSection from "./sections/HeroSection";
import MarqueeSection from "./sections/MarqueeSection";
import ServiceSection from "./sections/ServiceSection";
import TeamSection from "./sections/TeamSection";
import WorkflowSection from "./sections/WorkflowSection";

function App() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-slate-50 text-slate-800">
      <Header />
      <main className="pt-16">
        <HeroSection />
        <MarqueeSection />
        <ServiceSection />
        <WorkflowSection />
        <DashboardSection />
        <TeamSection />
        <ContactSection />
      </main>
      <Footer />
    </div>
  );
}

export default App;
