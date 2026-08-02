export function PolicyForm() {
  async function submit() {
    return fetch("/api/policies", { method: "POST" });
  }
  return <button onClick={submit}>Upload</button>;
}
