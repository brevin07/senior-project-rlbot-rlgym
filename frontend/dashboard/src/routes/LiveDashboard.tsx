export default function LiveDashboard() {
  return (
    <section className="panel panel--embed">
      <div className="panel__header">
        <h2>Live Analysis</h2>
        <a className="ghost" href="/legacy/live/" target="_blank" rel="noreferrer">Open in new tab</a>
      </div>
      <div className="embed">
        <iframe title="Live Analysis" src="/legacy/live/" />
      </div>
    </section>
  );
}
