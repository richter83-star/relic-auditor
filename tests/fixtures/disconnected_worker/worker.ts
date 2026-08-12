export function processLead(lead) { return enrichLead(lead); }
export function startWorker() { return new Worker("leads", processLead); }
