import type { ProjectTrustChoice } from "./gatewayProcess.js";

export function projectTrustChoice(response: number): ProjectTrustChoice {
  if (response === 1) return "once";
  if (response === 2) return "always";
  return "ignore";
}
