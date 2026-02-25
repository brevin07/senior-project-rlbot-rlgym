export default function ReplayDashboard() {
  return (
    <section className="panel panel--embed">
      <div className="panel__header">
        <h2>Replay Analysis</h2>
        <a className="ghost" href="/legacy/replay/" target="_blank" rel="noreferrer">Open in new tab</a>
      </div>
      <div className="embed">
        <iframe title="Replay Analysis" src="/legacy/replay/" />
      </div>
    </section>
  );
}
