export function submitLead(lead) {
  queue.add("leads", lead);
  return { status: "queued" };
}
