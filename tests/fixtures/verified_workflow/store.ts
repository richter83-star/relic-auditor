export function getReport() {
  return prisma.report.findMany();
}
