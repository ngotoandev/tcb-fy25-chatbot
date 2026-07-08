import Chat from "./components/Chat";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-100 flex flex-col">
      <header className="bg-red-700 text-white px-6 py-4 shadow">
        <h1 className="text-lg font-semibold">Techcombank FY25 Results Assistant</h1>
        <p className="text-xs opacity-80">
          Grounded in the official FY25 press release (year ended 31 Dec 2025) — answers cite pages.
        </p>
      </header>
      <Chat />
    </div>
  );
}
