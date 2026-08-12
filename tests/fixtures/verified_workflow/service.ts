import { saveDocument } from "./db";
export function createPolicyAnalysis(document) {
  saveDocument(document);
  queue.add("analysis", document.id);
  return { status: "queued" };
}
