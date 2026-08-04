export function ReportScreen() {
  async function loadReport() {
    return fetch("/api/reports");
  }
  return <button onClick={loadReport}>Report</button>;
}
