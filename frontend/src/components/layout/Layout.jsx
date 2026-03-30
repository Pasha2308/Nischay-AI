import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { ToastHost } from "../ui/Toast";

export function Layout({ usingDemo, toasts }) {
  const loc = useLocation();
  return (
    <div className="min-h-screen">
      <div className="flex">
        <Sidebar />
        <div className="flex-1 min-w-0">
          <TopBar path={loc.pathname} usingDemo={usingDemo} />
          <main className="px-4 md:px-6 py-6">
            <Outlet />
          </main>
        </div>
      </div>
      <ToastHost toasts={toasts} />
    </div>
  );
}

