import { Route, Routes } from "react-router-dom";

import MarketingPage from "./pages/MarketingPage";
import ApplyPage from "./pages/apply/ApplyPage";
import AdminApp from "./pages/admin/AdminApp";

function App() {
  return (
    <Routes>
      <Route path="/" element={<MarketingPage />} />
      <Route path="/apply" element={<ApplyPage />} />
      <Route path="/admin/*" element={<AdminApp />} />
    </Routes>
  );
}

export default App;
