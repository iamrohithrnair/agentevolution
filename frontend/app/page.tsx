import AtlasPingPanel from "@/components/AtlasPingPanel";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-100 px-4 py-16 text-slate-900 dark:bg-slate-950 dark:text-white">
      <main className="mx-auto flex max-w-3xl flex-col items-center gap-10">
        <header className="text-center">
          <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">Atlas connectivity</h1>
          <p className="mt-3 max-w-lg text-base leading-relaxed text-slate-600 dark:text-slate-400">
            Test your cluster from Next.js via the official database driver running on the server.
          </p>
        </header>
        <AtlasPingPanel />
      </main>
    </div>
  );
}
