export interface ApprovalRequest { id: string; status: "pending" | "approved"; }
export type ApprovalResult = { id: string; accepted: boolean };
