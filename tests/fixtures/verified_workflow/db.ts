export function saveDocument(document) {
  return prisma.document.create(document);
}
export function saveReport(report) {
  return prisma.report.create(report);
}
