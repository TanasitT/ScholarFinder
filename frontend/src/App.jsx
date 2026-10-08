import { NavLink, Route, Routes } from "react-router-dom";
import SearchPage from "./pages/SearchPage.jsx";
import PapersPage from "./pages/PapersPage.jsx";
import PaperDetailPage from "./pages/PaperDetailPage.jsx";
import ScholarDetailPage from "./pages/ScholarDetailPage.jsx";

export default function App() {
  return (
    <>
      <div className="topbar">
        <NavLink to="/" className="brand">
          <strong>ScholarFinder</strong>
          <span>reviewer search</span>
        </NavLink>
        <nav>
          <NavLink to="/" end className={({ isActive }) => (isActive ? "active" : "")}>
            New search
          </NavLink>
          <NavLink to="/papers" className={({ isActive }) => (isActive ? "active" : "")}>
            Past papers
          </NavLink>
        </nav>
      </div>

      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/papers" element={<PapersPage />} />
        <Route path="/papers/:paperId" element={<PaperDetailPage />} />
        <Route path="/scholars/:scholarId" element={<ScholarDetailPage />} />
      </Routes>
    </>
  );
}
