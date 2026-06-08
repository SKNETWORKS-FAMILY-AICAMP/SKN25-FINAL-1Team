import Footer from "./components/layout/Footer";
import Header from "./components/layout/Header";
import ContactSection from "./sections/ContactSection";
import DashboardSection from "./sections/DashboardSection";
import HeroSection from "./sections/HeroSection";
import MarqueeSection from "./sections/MarqueeSection";
import SafetySection from "./sections/SafetySection";
import ServiceSection from "./sections/ServiceSection";
import TeamSection from "./sections/TeamSection";
import WorkflowSection from "./sections/WorkflowSection";

function App() {
  return (
    <div className="min-h-screen overflow-hidden bg-slate-50 text-slate-800">
      <Header />
      <main>
        <HeroSection />
        <MarqueeSection />
        <ServiceSection />
        <WorkflowSection />
        <DashboardSection />
        <SafetySection />
        <TeamSection />
        <ContactSection />
      </main>
      <Footer />
    </div>
  );
}

export default App;
