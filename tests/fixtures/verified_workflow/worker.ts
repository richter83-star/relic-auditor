import { evaluatePolicy } from "./evaluator";
import { generateReport } from "./report";
import { saveReport } from "./db";
export function processAnalysis(document) {
  const findings = evaluatePolicy(document);
  const report = generateReport(findings);
  return saveReport(report);
}
export function startWorker() {
  return new Worker("analysis", processAnalysis);
}
