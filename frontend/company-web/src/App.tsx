import { Route, Routes } from "react-router-dom";

import MarketingPage from "./pages/MarketingPage";
import ApplyPage from "./pages/apply/ApplyPage";
import AdminApp from "./pages/admin/AdminApp";
import GuardianDemoPage from "./pages/demo/GuardianDemoPage";
import VetDemoPage from "./pages/demo/VetDemoPage";

function App() {
  return (
    <Routes>
      <Route path="/" element={<MarketingPage />} />
      <Route path="/apply" element={<ApplyPage />} />
      <Route path="/admin/*" element={<AdminApp />} />
      <Route path="/demo/guardian" element={<GuardianDemoPage />} />
      <Route path="/demo/vet" element={<VetDemoPage />} />
    </Routes>
  );
}

export default App;
