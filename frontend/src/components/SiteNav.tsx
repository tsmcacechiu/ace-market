import { NavLink } from "react-router-dom";
import { BOARDS } from "../api";

/** Top bar switching between the two boards. */
export function SiteNav() {
  return (
    <nav className="site-nav" aria-label="主選單">
      <div className="site-nav-inner">
        {Object.values(BOARDS).map((b) => (
          <NavLink key={b.path} to={b.path} end className="site-nav-link">
            {b.title}
          </NavLink>
        ))}
        <NavLink to="/strategy" className="site-nav-link">
          策略總覽
        </NavLink>
        <NavLink to="/signals" className="site-nav-link">
          訊號紀錄
        </NavLink>
      </div>
    </nav>
  );
}
