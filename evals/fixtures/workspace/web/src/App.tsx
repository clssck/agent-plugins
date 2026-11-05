import { Toaster } from "sonner";
import { CommandMenu } from "./components/CommandMenu";
import { Dashboard } from "./pages/Dashboard";
import { Header } from "./components/Header";
import { Sidebar } from "./components/Sidebar";

export function App() {
  return (
    <>
      <Header />
      <Sidebar />
      <Dashboard />
      <CommandMenu />
      <Toaster position="top-left" />
    </>
  );
}
